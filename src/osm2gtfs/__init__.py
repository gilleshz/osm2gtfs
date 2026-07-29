"""osm2gtfs - Convert OpenStreetMap route relations into GTFS feeds with real-geometry shapes."""

from __future__ import annotations

import sys
from pathlib import Path

from shapely.geometry import Point as ShapelyPoint

from osm2gtfs.config import Config
from osm2gtfs.fetch import Selection, fetch_elements, fetch_node_tags
from osm2gtfs.geometry import (
    STOP_ROLES,
    clip_to_boundary,
    cumulative_geodesic_distances,
    load_clip_boundary,
    project_and_order,
    stitch_ways,
)
from osm2gtfs.gtfs import (
    Agency,
    Calendar,
    Feed,
    Route,
    ShapePoint,
    Stop,
    StopTime,
    Trip,
    write_gtfs_dir,
    write_gtfs_zip,
)
from osm2gtfs.mapping import extract_route_attrs, make_route_id
from osm2gtfs.stops import StopRegistry, resolve_stop_names

__all__ = [
    "Config",
    "Feed",
    "Selection",
    "StopRegistry",
    "build_gtfs",
    "cumulative_geodesic_distances",
    "extract_route_attrs",
    "fetch_elements",
    "fetch_node_tags",
    "project_and_order",
    "resolve_stop_names",
    "route_type",
    "stitch_ways",
    "write_gtfs_dir",
    "write_gtfs_zip",
]


def build_gtfs(selection: Selection, config: Config) -> dict[str, int]:
    """Convert OSM route relations into a GTFS feed.

    This is the main entry point. It fetches relations from Overpass, stitches
    way geometry into polylines, projects stops along each polyline, deduplicates
    stops across relations, and writes CSV files.

    Returns a summary dict with keys ``routes``, ``trips``, ``stops``, and
    ``shape_points``.
    """
    elements = fetch_elements(selection, config.overpass_urls, config.timeout)
    relations = [el for el in elements if el.get("type") == "relation"]

    # Collect stop/platform node ids for the name-resolution pass.
    all_node_ids: set[int] = set()
    for rel in relations:
        for member in rel.get("members", []):
            if member.get("type") == "node" and member.get("role", "") in STOP_ROLES:
                ref = member.get("ref")
                if ref is not None:
                    all_node_ids.add(ref)

    node_tags = fetch_node_tags(list(all_node_ids), config.overpass_urls, config.timeout)

    clip_boundary = load_clip_boundary(config.clip) if config.clip else None

    stop_registry = StopRegistry(snap_distance_m=config.snap_distance_m)
    stop_node_registry: list[tuple[int, str]] = []  # (node_id, stop_id)

    agencies: list[Agency] = [
        Agency(
            agency_id=config.agency_id,
            agency_name=config.agency_name,
            agency_url=config.agency_url,
            agency_timezone=config.agency_timezone,
        )
    ]
    calendars: list[Calendar] = [
        Calendar(
            service_id="WEEK",
            monday=1,
            tuesday=1,
            wednesday=1,
            thursday=1,
            friday=1,
            saturday=1,
            sunday=1,
            start_date=config.calendar_start,
            end_date=config.calendar_end,
        )
    ]
    routes: dict[str, Route] = {}
    trips: list[Trip] = []
    stop_times: list[StopTime] = []
    shapes: list[ShapePoint] = []

    for rel in sorted(relations, key=lambda r: r.get("id", 0)):
        rel_id = str(rel.get("id", ""))
        members = rel.get("members", [])
        tags: dict[str, str] = rel.get("tags", {})

        route_id = make_route_id(tags)
        if route_id not in routes:
            attrs = extract_route_attrs(tags, config.default_route_type)
            routes[route_id] = Route(
                route_id=route_id,
                agency_id=config.agency_id,
                route_short_name=attrs.route_short_name,
                route_long_name=attrs.route_long_name,
                route_type=attrs.route_type,
                route_color=attrs.route_color,
                route_text_color=attrs.route_text_color,
            )

        polyline = stitch_ways(members, STOP_ROLES, config.max_gap_m)
        if polyline is None or polyline.is_empty:
            sys.stderr.write(f"warning: relation {rel_id}: no usable geometry, skipping\n")
            continue

        if clip_boundary is not None:
            polyline, dropped = clip_to_boundary(polyline, clip_boundary)
            if polyline is None:
                sys.stderr.write(f"warning: relation {rel_id}: outside the clip boundary\n")
                continue
            if dropped > 0:
                sys.stderr.write(
                    f"warning: relation {rel_id}: route re-enters the boundary, "
                    f"dropped a disconnected in-boundary piece\n"
                )

        shape_id = f"sh_{rel_id}"
        coords = list(polyline.coords)
        geodesic_dists = cumulative_geodesic_distances(coords)
        for seq, ((lon, lat), dist_m) in enumerate(zip(coords, geodesic_dists, strict=True)):
            shapes.append(
                ShapePoint(
                    shape_id=shape_id,
                    shape_pt_lat=round(lat, 7),
                    shape_pt_lon=round(lon, 7),
                    shape_pt_sequence=seq,
                    shape_dist_traveled=round(dist_m, 2),
                )
            )

        # Collect stop coordinates and their node refs.
        stop_infos: list[tuple[float, float, int | None]] = []
        for member in members:
            if member.get("role", "") not in STOP_ROLES:
                continue
            if member.get("type") == "node" and "lon" in member and "lat" in member:
                stop_infos.append((member["lon"], member["lat"], member.get("ref")))
            elif member.get("type") == "way":
                # Platform modeled as a way: use its centroid.
                geom = member.get("geometry")
                if geom and len(geom) >= 2:
                    lons = [p["lon"] for p in geom if "lon" in p]
                    lats = [p["lat"] for p in geom if "lat" in p]
                    if lons and lats:
                        stop_infos.append(
                            (sum(lons) / len(lons), sum(lats) / len(lats), member.get("ref"))
                        )

        if clip_boundary is not None:
            stop_infos = [s for s in stop_infos if clip_boundary.covers(ShapelyPoint(s[0], s[1]))]

        if len(stop_infos) < 2:
            sys.stderr.write(f"warning: relation {rel_id}: fewer than 2 stops, skipping\n")
            continue

        stop_coords = [(lon, lat) for lon, lat, _ in stop_infos]
        projected = project_and_order(polyline, stop_coords)

        if len(projected) < 2:
            sys.stderr.write(
                f"warning: relation {rel_id}: fewer than 2 projected stops, skipping\n"
            )
            continue

        trip_id = f"t_{rel_id}"
        trips.append(Trip(route_id=route_id, service_id="WEEK", trip_id=trip_id, shape_id=shape_id))

        for seq, (dist_deg, lon, lat) in enumerate(projected):
            stop_dist_m = _interpolate_geodesic_distance(coords, geodesic_dists, lon, lat, dist_deg)
            node_ref = _find_node_ref(stop_infos, lon, lat)
            stop_id = stop_registry.id_for(lon, lat)
            if node_ref is not None:
                stop_node_registry.append((node_ref, stop_id))
            mm, ss = divmod(seq * 60, 60)
            hh, mm = divmod(mm, 60)
            hh += 8
            time_str = f"{hh:02d}:{mm:02d}:{ss:02d}"
            stop_times.append(
                StopTime(
                    trip_id=trip_id,
                    arrival_time=time_str,
                    departure_time=time_str,
                    stop_id=stop_id,
                    stop_sequence=seq + 1,
                    shape_dist_traveled=round(stop_dist_m, 2),
                )
            )

    resolve_stop_names(stop_registry, node_tags, stop_node_registry)

    stop_rows = [
        Stop(
            stop_id=e.stop_id,
            stop_name=e.stop_name or e.stop_id,
            stop_lat=e.stop_lat,
            stop_lon=e.stop_lon,
        )
        for e in stop_registry.entries
    ]

    feed = Feed(
        agencies=agencies,
        calendars=calendars,
        stops=stop_rows,
        routes=list(routes.values()),
        trips=trips,
        stop_times=stop_times,
        shapes=shapes,
    )

    issues = feed.validate()
    if issues:
        for issue in issues:
            sys.stderr.write(f"validation: {issue}\n")

    write_gtfs_dir(feed, config.output)
    if config.output_zip:
        zip_path = Path(config.output).parent / f"{Path(config.output).name}.zip"
        write_gtfs_zip(feed, zip_path)

    return {
        "routes": len(feed.routes),
        "trips": len(feed.trips),
        "stops": len(feed.stops),
        "shape_points": len(feed.shapes),
    }


def _interpolate_geodesic_distance(
    coords: list[tuple[float, ...]],
    geodesic_dists: list[float],
    lon: float,
    lat: float,
    dist_deg: float,
) -> float:
    """Map a degree-distance along the polyline to the geodesic distance scale."""
    if len(coords) < 2:
        return 0.0

    deg_dists = [0.0]
    for i in range(len(coords) - 1):
        dx = coords[i + 1][0] - coords[i][0]
        dy = coords[i + 1][1] - coords[i][1]
        deg_dists.append(deg_dists[-1] + (dx**2 + dy**2) ** 0.5)

    if dist_deg <= 0:
        return 0.0
    if dist_deg >= deg_dists[-1]:
        return geodesic_dists[-1]

    for i in range(len(deg_dists) - 1):
        if deg_dists[i] <= dist_deg <= deg_dists[i + 1]:
            seg_len = deg_dists[i + 1] - deg_dists[i]
            seg_frac = (dist_deg - deg_dists[i]) / seg_len if seg_len != 0 else 0.0
            return geodesic_dists[i] + seg_frac * (geodesic_dists[i + 1] - geodesic_dists[i])

    return 0.0


def _find_node_ref(
    stop_infos: list[tuple[float, float, int | None]],
    lon: float,
    lat: float,
) -> int | None:
    for slon, slat, ref in stop_infos:
        if abs(slon - lon) < 1e-7 and abs(slat - lat) < 1e-7:
            return ref
    return None
