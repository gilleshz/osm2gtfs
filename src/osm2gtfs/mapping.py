"""Mapping from OSM route-relation tags to GTFS fields."""

from __future__ import annotations

from dataclasses import dataclass

# OSM ``route`` tag values to GTFS ``route_type`` integers.
# See https://gtfs.org/schedule/reference/#routestxt
ROUTE_TYPE_MAP: dict[str, int] = {
    "tram": 0,
    "light_rail": 0,
    "subway": 1,
    "metro": 1,
    "train": 2,
    "rail": 2,
    "high_speed_train": 101,
    "long_distance_train": 102,
    "intercity_train": 102,
    "monorail": 12,
    "funicular": 7,
    "bus": 3,
    "trolleybus": 11,
    "share_taxi": 705,
    "ferry": 4,
    "aerialway": 6,
    "cable_car": 6,
    "gondola": 6,
    "chair_lift": 6,
    "drag_lift": 6,
    "taxi": 1500,
}


@dataclass(frozen=True)
class RouteAttrs:
    """GTFS-relevant attributes extracted from an OSM route-relation's tags."""

    route_short_name: str
    route_long_name: str
    route_type: int
    route_color: str
    route_text_color: str
    network: str
    operator: str


def route_type(route_tag: str, default: int = 3) -> int:
    """Map an OSM ``route`` tag value to a GTFS ``route_type`` integer.

    Returns *default* for unrecognised values (defaults to 3, bus).
    """
    return ROUTE_TYPE_MAP.get(route_tag, default)


def _sanitise_colour(raw: str) -> str:
    c = (raw or "").strip().lstrip("#")
    if len(c) == 6 and all(ch in "0123456789abcdefABCDEF" for ch in c):
        return c.upper()
    return "888888"


def _contrast_text_colour(hex6: str) -> str:
    try:
        r = int(hex6[0:2], 16)
        g = int(hex6[2:4], 16)
        b = int(hex6[4:6], 16)
    except (ValueError, IndexError):
        return "FFFFFF"
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return "000000" if luminance > 150 else "FFFFFF"


def extract_route_attrs(tags: dict[str, str], default_route_type: int = 3) -> RouteAttrs:
    """Extract GTFS route attributes from an OSM relation's *tags* dict."""
    ref = (tags.get("ref") or "").strip()
    name = (tags.get("name") or "").strip()
    colour = _sanitise_colour(tags.get("colour", ""))
    return RouteAttrs(
        route_short_name=ref or name,
        route_long_name=name or ref,
        route_type=route_type(tags.get("route", ""), default_route_type),
        route_color=colour,
        route_text_color=_contrast_text_colour(colour),
        network=(tags.get("network") or "").strip(),
        operator=(tags.get("operator") or "").strip(),
    )


def make_route_id(tags: dict[str, str]) -> str:
    """Build a deterministic ``route_id`` from relation tags.

    Both directions of a line produce the same id so downstream tools can merge them.
    """
    route = (tags.get("route") or "unknown").strip()
    network = (tags.get("network") or "").strip()
    ref = (tags.get("ref") or tags.get("name") or "").strip()
    return f"{route}|{network}|{ref}"
