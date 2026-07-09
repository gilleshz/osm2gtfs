"""Stop deduplication by geodesic proximity."""

from __future__ import annotations

from dataclasses import dataclass

from osm2gtfs.geometry import geodesic_distance_m


@dataclass
class StopEntry:
    stop_id: str
    stop_name: str
    stop_lat: float
    stop_lon: float


class StopRegistry:
    """Register of physical stops with geodesic-proximity deduplication.

    Two stops within ``snap_distance_m`` metres of each other share one ``stop_id``.
    """

    def __init__(self, snap_distance_m: float = 35.0) -> None:
        self._snap_m = snap_distance_m
        self._entries: list[StopEntry] = []

    def id_for(self, lon: float, lat: float, name: str = "") -> str:
        """Return the ``stop_id`` for a stop at (*lon*, *lat*).

        Reuses an existing id if a stop is already registered within the snap
        distance, otherwise creates a new deterministic id.
        """
        for entry in self._entries:
            if geodesic_distance_m(lon, lat, entry.stop_lon, entry.stop_lat) <= self._snap_m:
                if not entry.stop_name and name:
                    entry.stop_name = name
                return entry.stop_id
        sid = f"S{len(self._entries)}"
        self._entries.append(StopEntry(stop_id=sid, stop_name=name, stop_lat=lat, stop_lon=lon))
        return sid

    def update_name(self, stop_id: str, name: str) -> None:
        """Set the name for a stop if it currently has none."""
        for entry in self._entries:
            if entry.stop_id == stop_id and not entry.stop_name and name:
                entry.stop_name = name
                return

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
