"""Stop deduplication by geodesic proximity."""

from __future__ import annotations

import math
from dataclasses import dataclass

from osm2gtfs.geometry import geodesic_distance_m

EARTH_RADIUS_M = 6378137.0
MIN_COS_LAT = math.cos(math.radians(85.0))


@dataclass
class StopEntry:
    stop_id: str
    stop_name: str
    stop_lat: float
    stop_lon: float


class StopRegistry:
    """Register of physical stops with geodesic-proximity deduplication.

    Two stops within ``snap_distance_m`` metres of each other share one ``stop_id``.

    Entries are bucketed into a grid of square degree cells one snap distance tall,
    so a lookup only measures against the cells that can hold a stop in range
    rather than the whole register. A country-sized feed spends most of its time in
    this lookup otherwise. Cells are square in degrees while a degree of longitude
    shrinks with latitude, so the column span widens away from the equator.
    """

    def __init__(self, snap_distance_m: float = 35.0) -> None:
        self._snap_m = snap_distance_m
        self._entries: list[StopEntry] = []
        self._by_id: dict[str, StopEntry] = {}
        self._step = math.degrees(snap_distance_m / EARTH_RADIUS_M)
        self._grid: dict[tuple[int, int], list[int]] = {}

    def _cell(self, lon: float, lat: float) -> tuple[int, int]:
        return (math.floor(lat / self._step), math.floor(lon / self._step))

    def _neighbourhood(self, lon: float, lat: float) -> list[int]:
        row, col = self._cell(lon, lat)
        span = math.ceil(1.0 / max(math.cos(math.radians(lat)), MIN_COS_LAT)) + 1
        found: list[int] = []
        for drow in (-1, 0, 1):
            for dcol in range(-span, span + 1):
                found.extend(self._grid.get((row + drow, col + dcol), ()))
        return sorted(found)

    def id_for(self, lon: float, lat: float, name: str = "") -> str:
        """Return the ``stop_id`` for a stop at (*lon*, *lat*).

        Reuses an existing id if a stop is already registered within the snap
        distance, otherwise creates a new deterministic id.
        """
        for index in self._neighbourhood(lon, lat):
            entry = self._entries[index]
            if geodesic_distance_m(lon, lat, entry.stop_lon, entry.stop_lat) <= self._snap_m:
                if not entry.stop_name and name:
                    entry.stop_name = name
                return entry.stop_id
        sid = f"S{len(self._entries)}"
        entry = StopEntry(stop_id=sid, stop_name=name, stop_lat=lat, stop_lon=lon)
        self._grid.setdefault(self._cell(lon, lat), []).append(len(self._entries))
        self._entries.append(entry)
        self._by_id[sid] = entry
        return sid

    def update_name(self, stop_id: str, name: str) -> None:
        """Set the name for a stop if it currently has none."""
        entry = self._by_id.get(stop_id)
        if entry is not None and not entry.stop_name and name:
            entry.stop_name = name

    @property
    def entries(self) -> list[StopEntry]:
        return list(self._entries)

    def __len__(self) -> int:
        return len(self._entries)


def resolve_stop_names(
    registry: StopRegistry,
    node_tags: dict[int, dict[str, str]],
    stop_nodes: list[tuple[int, str]],
) -> None:
    """Resolve stop names from fetched OSM node tags.

    *stop_nodes* is a list of ``(node_id, stop_id)`` pairs. Each node's
    ``name`` tag (falling back to ``ref``) is applied to the corresponding
    stop in *registry*.
    """
    for node_id, stop_id in stop_nodes:
        if node_id not in node_tags:
            continue
        tags = node_tags[node_id]
        name = tags.get("name") or tags.get("ref") or tags.get("operator") or f"Stop {node_id}"
        registry.update_name(stop_id, name)
