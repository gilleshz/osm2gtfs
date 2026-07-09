"""Configuration for osm2gtfs.

Build one from environment variables with ``Config.from_env()``, then overlay
CLI-supplied values with ``config.with_overrides(**kwargs)``.

Precedence: CLI flags > environment variables > defaults.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_str(name: str, default: str) -> str:
    raw = os.environ.get(name)
    return default if raw is None else raw


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes")


@dataclass(frozen=True)
class Config:
    """Immutable configuration for an osm2gtfs run.

    All distance values are in metres.
    """

    overpass_url: str = "https://overpass-api.de/api/interpreter"
    timeout: int = 120
    snap_distance_m: float = 35.0
    max_gap_m: float = 100.0
    agency_id: str = "OSM"
    agency_name: str = "OpenStreetMap"
    agency_url: str = "https://osm.org"
    agency_timezone: str = "Europe/Paris"
    calendar_start: str = "20200101"
    calendar_end: str = "20301231"
    default_route_type: int = 3
    output_zip: bool = False
    output: str = "gtfs"

    @classmethod
    def from_env(cls) -> Config:
        """Build a ``Config`` with ``OSM2GTFS_*`` environment variables overlaid on defaults."""
        return cls(
            overpass_url=_env_str("OSM2GTFS_OVERPASS_URL", cls.overpass_url),
            timeout=_env_int("OSM2GTFS_TIMEOUT", cls.timeout),
            snap_distance_m=_env_float("OSM2GTFS_SNAP_DISTANCE_M", cls.snap_distance_m),
            max_gap_m=_env_float("OSM2GTFS_MAX_GAP_M", cls.max_gap_m),
            agency_id=_env_str("OSM2GTFS_AGENCY_ID", cls.agency_id),
            agency_name=_env_str("OSM2GTFS_AGENCY_NAME", cls.agency_name),
            agency_url=_env_str("OSM2GTFS_AGENCY_URL", cls.agency_url),
            agency_timezone=_env_str("OSM2GTFS_AGENCY_TIMEZONE", cls.agency_timezone),
            calendar_start=_env_str("OSM2GTFS_CALENDAR_START", cls.calendar_start),
            calendar_end=_env_str("OSM2GTFS_CALENDAR_END", cls.calendar_end),
            default_route_type=_env_int("OSM2GTFS_DEFAULT_ROUTE_TYPE", cls.default_route_type),
            output_zip=_env_bool("OSM2GTFS_OUTPUT_ZIP", cls.output_zip),
            output=_env_str("OSM2GTFS_OUTPUT", cls.output),
        )

    def with_overrides(self, **kwargs: Any) -> Config:
        """Return a new ``Config`` with *kwargs* applied on top of current values.

        Only keys that exist on the dataclass and have non-``None`` values are overridden.
        """
        current = {f.name: getattr(self, f.name) for f in self.__dataclass_fields__.values()}
        for key, value in kwargs.items():
            if key in current and value is not None:
                current[key] = value
        return Config(**current)
