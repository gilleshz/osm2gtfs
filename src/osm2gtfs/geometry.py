"""Geometry operations: way stitching, geodesic distances, and stop-to-polyline projection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pyproj import Geod
from shapely.geometry import LineString, MultiLineString, Point, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import linemerge, unary_union

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


def load_clip_boundary(path: str) -> BaseGeometry:
    """Read a GeoJSON polygon from *path*, accepting a bare geometry, Feature or collection."""
    raw = json.loads(Path(path).read_text())
    if raw.get("type") == "FeatureCollection":
        parts = [shape(f["geometry"]) for f in raw["features"] if f.get("geometry")]
        if not parts:
            raise ValueError(f"no geometry in {path}")
        return unary_union(parts)
    if raw.get("type") == "Feature":
        return shape(raw["geometry"])
    return shape(raw)


def clip_to_boundary(
    polyline: LineString, boundary: BaseGeometry
) -> tuple[LineString | None, float]:
    """Keep the longest run of *polyline* that lies inside *boundary*.

    Returns the kept piece and the length of any *other* in-boundary pieces that
    had to be discarded, in degrees. A route that leaves the boundary and comes
    back yields several pieces and only the longest is kept, since joining them
    would draw track through the part that was deliberately excluded. Track
    outside the boundary is not counted as discarded: dropping it is the point.
    """
    clipped = polyline.intersection(boundary)
    if clipped.is_empty:
        return None, 0.0

    parts = [clipped] if isinstance(clipped, LineString) else list(getattr(clipped, "geoms", []))
    usable = [g for g in parts if isinstance(g, LineString) and g.length > 0]
    if not usable:
        return None, 0.0

    best = max(usable, key=lambda g: g.length)
    return best, sum(g.length for g in usable) - best.length


def _gap_to(prev: LineString, comp: LineString) -> tuple[float, LineString]:
    """Distance from the end of *prev* to the nearer end of *comp*.

    Returns *comp* reversed when its last point is the nearer one, so the caller
    can always join to ``comp.coords[0]``. Measuring one end but joining to the
    other draws a straight line the length of the component when it runs backwards.
    """
    tail = prev.coords[-1]
    _, _, to_head = WGS84.inv(tail[0], tail[1], comp.coords[0][0], comp.coords[0][1])
    _, _, to_tail = WGS84.inv(tail[0], tail[1], comp.coords[-1][0], comp.coords[-1][1])
    if to_tail < to_head:
        return to_tail, LineString(list(comp.coords)[::-1])
    return to_head, comp


def stitch_ways(
    members: list[dict[str, Any]],
    stop_roles: frozenset[str] = STOP_ROLES,
    max_gap_m: float = 100.0,
) -> LineString | None:
    """Stitch way members of an OSM relation into a single continuous polyline.

    Way members whose role is in *stop_roles* are excluded. Runs ``linemerge``
    on the collected ways. When the result is a ``MultiLineString``, components
    are chained while each consecutive gap stays within *max_gap_m*, and the
    longest chain wins. A wider gap ends the chain instead of being crossed,
    since concatenating over it invents track that does not exist.
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

    chains: list[list[LineString]] = [[ordered[0]]]
    for comp in ordered[1:]:
        prev = chains[-1][-1]
        gap, oriented = _gap_to(prev, comp)
        if gap > max_gap_m:
            chains.append([comp])
            continue
        if gap > 0:
            chains[-1].append(LineString([prev.coords[-1], oriented.coords[0]]))
        chains[-1].append(oriented)

    bridged = max(chains, key=lambda chain: sum(part.length for part in chain))

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
