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


def _overpass_post(
    urls: list[str],
    data: dict[str, str],
    timeout: float,
) -> dict[str, Any]:
    """POST *data* to Overpass, trying each URL in order.

    Returns the parsed JSON response from the first mirror that responds
    successfully. Raises ``httpx.HTTPError`` if all mirrors fail.
    """
    last_error: Exception | None = None
    for url in urls:
        sys.stderr.write(f"trying overpass: {url}\n")
        try:
            resp = httpx.post(url, data=data, timeout=timeout)
            resp.raise_for_status()
            result: dict[str, Any] = resp.json()
            return result
        except httpx.HTTPError as exc:
            last_error = exc
            sys.stderr.write(f"overpass mirror failed: {url} ({exc})\n")
    raise httpx.HTTPError(f"all {len(urls)} overpass mirrors failed") from last_error


def fetch_elements(
    selection: Selection,
    overpass_urls: list[str] | None = None,
    timeout: int = 120,
) -> list[dict[str, Any]]:
    """Fetch OSM elements from the Overpass API for the given *selection*.

    Tries each URL in *overpass_urls* in order. Raises ``httpx.HTTPError``
    if all mirrors fail.
    """
    if overpass_urls is None:
        overpass_urls = ["https://overpass-api.de/api/interpreter"]
    query = _build_overpass_query(selection, timeout)
    data = _overpass_post(overpass_urls, {"data": query}, float(timeout + 30))
    if "elements" not in data:
        raise ValueError(f"unexpected Overpass response (missing 'elements'): {list(data.keys())}")
    return list(data["elements"])


def fetch_node_tags(
    node_ids: list[int],
    overpass_urls: list[str] | None = None,
    timeout: int = 120,
) -> dict[int, dict[str, str]]:
    """Fetch tags for the given OSM node ids.

    Tries each URL in *overpass_urls* in order. Returns a mapping from node
    id to its ``tags`` dict.
    """
    if not node_ids:
        return {}
    if overpass_urls is None:
        overpass_urls = ["https://overpass-api.de/api/interpreter"]

    ids_csv = ",".join(str(n) for n in node_ids)
    query = f"[out:json][timeout:{timeout}];node(id:{ids_csv});out;"
    data = _overpass_post(overpass_urls, {"data": query}, float(timeout + 30))

    result: dict[int, dict[str, str]] = {}
    for element in data.get("elements", []):
        if element.get("type") == "node":
            nid = element.get("id")
            tags = element.get("tags", {})
            if nid is not None and tags:
                result[nid] = tags
    return result
