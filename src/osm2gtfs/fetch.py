"""Overpass API query building and HTTP fetching.

Three input-selection modes: relation IDs, bounding box with mode filters, or a
raw Overpass query. All produce a list of OSM element dicts.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class RelationIds:
    """Select relations by explicit OSM ids."""

    ids: list[int]

    def __post_init__(self) -> None:
        if not self.ids:
            raise ValueError("at least one relation id is required")
        for i in self.ids:
            if i <= 0:
                raise ValueError(f"relation ids must be positive (got {i})")


@dataclass(frozen=True)
class BboxFilter:
    """Select route relations within a bounding box, optionally filtered by mode.

    *bbox* is ``(south, west, north, east)`` in decimal degrees.
    *modes* is a list of OSM ``route`` tag values (e.g. ``["tram", "bus"]``).
    An empty or ``None`` *modes* list selects all route relations.
    """

    south: float
    west: float
    north: float
    east: float
    modes: list[str] | None = None

    def __post_init__(self) -> None:
        if not (-90.0 <= self.south <= 90.0):
            raise ValueError(f"south latitude out of range: {self.south}")
        if not (-90.0 <= self.north <= 90.0):
            raise ValueError(f"north latitude out of range: {self.north}")
        if not (-180.0 <= self.west <= 180.0):
            raise ValueError(f"west longitude out of range: {self.west}")
        if not (-180.0 <= self.east <= 180.0):
            raise ValueError(f"east longitude out of range: {self.east}")
        if self.south >= self.north:
            raise ValueError(f"south ({self.south}) must be less than north ({self.north})")
        if self.west >= self.east:
            raise ValueError(f"west ({self.west}) must be less than east ({self.east})")


@dataclass(frozen=True)
class RawQuery:
    """Pass a raw Overpass QL query through. ``[out:json]`` is prepended if missing."""

    query: str

    def __post_init__(self) -> None:
        if not self.query.strip():
            raise ValueError("query must not be empty")


Selection = RelationIds | BboxFilter | RawQuery


def _build_overpass_query(selection: Selection, timeout: int) -> str:
    if isinstance(selection, RelationIds):
        ids_csv = ",".join(str(i) for i in selection.ids)
        return f"[out:json][timeout:{timeout}];relation(id:{ids_csv});out geom;"

    if isinstance(selection, BboxFilter):
        bbox = f"{selection.south},{selection.west},{selection.north},{selection.east}"
        if selection.modes:
            pattern = "|".join(selection.modes)
            filter_clause = f'[route~"^({pattern})$"]'
        else:
            filter_clause = "[route]"
        return f"[out:json][timeout:{timeout}];relation{filter_clause}({bbox});out geom;"

    if isinstance(selection, RawQuery):
        q = selection.query.strip()
        if not q.startswith("[out:json]"):
            q = f"[out:json];{q}"
        return q

    raise TypeError(f"unknown selection type: {type(selection).__name__}")


def fetch_elements(
    selection: Selection,
    overpass_url: str = "https://overpass-api.de/api/interpreter",
    timeout: int = 120,
) -> list[dict[str, Any]]:
    """Fetch OSM elements from the Overpass API for the given *selection*.

    Raises ``httpx.HTTPError`` on network or HTTP errors.
    """
    query = _build_overpass_query(selection, timeout)
    sys.stderr.write(f"fetching from {overpass_url} ...\n")

    resp = httpx.post(
        overpass_url,
        data={"data": query},
        timeout=float(timeout + 30),
    )
    resp.raise_for_status()
    data = resp.json()
    if "elements" not in data:
        raise ValueError(f"unexpected Overpass response (missing 'elements'): {list(data.keys())}")
    return list(data["elements"])


def fetch_node_tags(
    node_ids: list[int],
    overpass_url: str = "https://overpass-api.de/api/interpreter",
    timeout: int = 120,
) -> dict[int, dict[str, str]]:
    """Fetch tags for the given OSM node ids.

    Returns a mapping from node id to its ``tags`` dict.
    """
    if not node_ids:
        return {}

    ids_csv = ",".join(str(n) for n in node_ids)
    query = f"[out:json][timeout:{timeout}];node(id:{ids_csv});out;"

    resp = httpx.post(
        overpass_url,
        data={"data": query},
        timeout=float(timeout + 30),
    )
    resp.raise_for_status()
    data = resp.json()

    result: dict[int, dict[str, str]] = {}
    for element in data.get("elements", []):
        if element.get("type") == "node":
            nid = element.get("id")
            tags = element.get("tags", {})
            if nid is not None and tags:
                result[nid] = tags
    return result
