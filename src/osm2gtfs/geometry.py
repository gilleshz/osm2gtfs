"""Geometry operations: way stitching, geodesic distances, and stop-to-polyline projection."""

from __future__ import annotations

from typing import Any

from pyproj import Geod
from shapely.geometry import LineString, MultiLineString, Point
from shapely.ops import linemerge

STOP_ROLES = frozenset(
    {
        "stop",
        "stop_entry_only",
        "stop_exit_only",
        "platform",
        "platform_entry_only",
        "platform_exit_only",
    }
)

WGS84 = Geod(ellps="WGS84")


def stitch_ways(
    members: list[dict[str, Any]],
    stop_roles: frozenset[str] = STOP_ROLES,
    max_gap_m: float = 100.0,
) -> LineString | None:
    """Stitch way members of an OSM relation into a single continuous polyline.

    Way members whose role is in *stop_roles* are excluded. Runs ``linemerge``
    on the collected ways. When the result is a ``MultiLineString``, bridges
    components with straight segments where gaps are within *max_gap_m*.
    Returns ``None`` if there is no usable geometry.
    """
    lines: list[LineString] = []
    for member in members:
        if member.get("type") != "way":
            continue
        if member.get("role", "") in stop_roles:
            continue
        geom = member.get("geometry")
        if not geom:
            continue
        pts = [(p["lon"], p["lat"]) for p in geom if "lon" in p and "lat" in p]
        if len(pts) >= 2:
            lines.append(LineString(pts))

    if not lines:
        return None

    merged = linemerge(MultiLineString(lines)) if len(lines) > 1 else lines[0]

    if isinstance(merged, LineString):
        return merged if merged.length > 0 else None

    components: list[LineString] = list(merged.geoms)

    if len(components) == 1:
        return components[0] if components[0].length > 0 else None

    main = max(components, key=lambda g: g.length)
    ordered = sorted(components, key=lambda g: main.project(g.centroid))

    bridged = [ordered[0]]
    for comp in ordered[1:]:
        prev = bridged[-1]
        gap_end_prev = (prev.coords[-1][0], prev.coords[-1][1])
        gap_start_comp = (comp.coords[0][0], comp.coords[0][1])
        gap_alt_start = (comp.coords[-1][0], comp.coords[-1][1])
        _, _, dist_a = WGS84.inv(
            gap_end_prev[0],
            gap_end_prev[1],
            gap_start_comp[0],
            gap_start_comp[1],
        )
        _, _, dist_b = WGS84.inv(
            gap_end_prev[0],
            gap_end_prev[1],
            gap_alt_start[0],
            gap_alt_start[1],
        )
        dist = min(dist_a, dist_b)
        if dist <= max_gap_m:
            connector = LineString([gap_end_prev, gap_start_comp])
            bridged.append(connector)
        bridged.append(comp)

    if len(bridged) > 1:
        merged2 = linemerge(MultiLineString(bridged))
        if isinstance(merged2, LineString):
            return merged2 if merged2.length > 0 else None

    result_coords: list[tuple[float, ...]] = []
    for i, comp in enumerate(bridged):
        coords = list(comp.coords)
        if i > 0 and result_coords:
            result_coords.append(coords[0])
        result_coords.extend(coords)

    if len(result_coords) < 2:
        return None
    return LineString(result_coords)


def cumulative_geodesic_distances(
    coords: list[tuple[float, ...]],
) -> list[float]:
    """Return cumulative geodesic distance (metres) along a list of (lon, lat) points.

    The first entry is always ``0.0``.
    """
    if len(coords) < 2:
        return [0.0] * len(coords)
    distances = [0.0]
    for i in range(len(coords) - 1):
        lon1, lat1 = coords[i]
        lon2, lat2 = coords[i + 1]
        _, _, dist = WGS84.inv(lon1, lat1, lon2, lat2)
        distances.append(distances[-1] + dist)
    return distances


def project_and_order(
    polyline: LineString,
    stops: list[tuple[float, float]],
) -> list[tuple[float, float, float]]:
    """Project *stops* onto *polyline* and return them ordered by distance along it.

    Each element of *stops* is ``(lon, lat)``. Returns ``(distance_degrees, lon, lat)``
    tuples sorted by distance. The degree-distance is for ordering only; use
    ``cumulative_geodesic_distances`` for ``shape_dist_traveled`` values.
    """
    projected: list[tuple[float, float, float]] = []
    seen: set[tuple[float, float, float]] = set()
    for lon, lat in stops:
        pt = Point(lon, lat)
        dist_deg = polyline.project(pt)
        key = (round(dist_deg, 6), lon, lat)
        if key not in seen:
            seen.add(key)
            projected.append(key)
    projected.sort(key=lambda x: x[0])
    return projected


def geodesic_distance_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Return the geodesic distance in metres between two (lon, lat) points."""
    _, _, dist = WGS84.inv(lon1, lat1, lon2, lat2)
    return float(dist)
