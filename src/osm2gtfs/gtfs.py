"""GTFS dataclasses and file-writing utilities."""

from __future__ import annotations

import csv
import sys
import tempfile
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Agency:
    agency_id: str
    agency_name: str
    agency_url: str
    agency_timezone: str

    REQUIRED_FIELDS = ["agency_id", "agency_name", "agency_url", "agency_timezone"]


@dataclass(frozen=True)
class Calendar:
    service_id: str
    monday: int
    tuesday: int
    wednesday: int
    thursday: int
    friday: int
    saturday: int
    sunday: int
    start_date: str
    end_date: str

    REQUIRED_FIELDS = [
        "service_id",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
        "start_date",
        "end_date",
    ]


@dataclass(frozen=True)
class Stop:
    stop_id: str
    stop_name: str
    stop_lat: float
    stop_lon: float

    REQUIRED_FIELDS = ["stop_id", "stop_name", "stop_lat", "stop_lon"]


@dataclass(frozen=True)
class Route:
    route_id: str
    agency_id: str
    route_short_name: str
    route_long_name: str
    route_type: int
    route_color: str
    route_text_color: str

    REQUIRED_FIELDS = [
        "route_id",
        "agency_id",
        "route_short_name",
        "route_long_name",
        "route_type",
        "route_color",
        "route_text_color",
    ]


@dataclass(frozen=True)
class Trip:
    route_id: str
    service_id: str
    trip_id: str
    shape_id: str

    REQUIRED_FIELDS = ["route_id", "service_id", "trip_id", "shape_id"]


@dataclass(frozen=True)
class StopTime:
    trip_id: str
    arrival_time: str
    departure_time: str
    stop_id: str
    stop_sequence: int
    shape_dist_traveled: float

    REQUIRED_FIELDS = [
        "trip_id",
        "arrival_time",
        "departure_time",
        "stop_id",
        "stop_sequence",
        "shape_dist_traveled",
    ]


@dataclass(frozen=True)
class ShapePoint:
    shape_id: str
    shape_pt_lat: float
    shape_pt_lon: float
    shape_pt_sequence: int
    shape_dist_traveled: float

    REQUIRED_FIELDS = [
        "shape_id",
        "shape_pt_lat",
        "shape_pt_lon",
        "shape_pt_sequence",
        "shape_dist_traveled",
    ]


@dataclass
class Feed:
    """Aggregate of all GTFS table rows. Call ``validate()`` before writing."""

    agencies: list[Agency] = field(default_factory=list)
    calendars: list[Calendar] = field(default_factory=list)
    stops: list[Stop] = field(default_factory=list)
    routes: list[Route] = field(default_factory=list)
    trips: list[Trip] = field(default_factory=list)
    stop_times: list[StopTime] = field(default_factory=list)
    shapes: list[ShapePoint] = field(default_factory=list)

    def validate(self) -> list[str]:
        """Run structural checks. Returns a list of issue descriptions (empty means valid)."""
        issues: list[str] = []

        if not self.agencies:
            issues.append("agency.txt: at least one agency is required")
        if not self.calendars:
            issues.append("calendar.txt: at least one service is required")
        if not self.stops:
            issues.append("stops.txt: at least one stop is required")
        if not self.routes:
            issues.append("routes.txt: at least one route is required")
        if not self.trips:
            issues.append("trips.txt: at least one trip is required")
        if not self.stop_times:
            issues.append("stop_times.txt: at least one stop_time is required")

        for agency in self.agencies:
            if not agency.agency_id or not agency.agency_name:
                issues.append("agency.txt: agency_id and agency_name must be non-empty")

        for route in self.routes:
            if not route.route_id:
                issues.append("routes.txt: route_id must be non-empty")
            if route.route_type < 0:
                issues.append(f"routes.txt: route_type must be >= 0 (got {route.route_type})")

        shape_dists: dict[str, float] = {}
        for sp in self.shapes:
            prev = shape_dists.get(sp.shape_id)
            if prev is not None and sp.shape_dist_traveled < prev:
                issues.append(
                    f"shapes.txt: shape_dist_traveled not monotonic for shape {sp.shape_id}"
                )
            shape_dists[sp.shape_id] = sp.shape_dist_traveled

        trip_seqs: dict[str, set[int]] = {}
        for st in self.stop_times:
            seqs = trip_seqs.setdefault(st.trip_id, set())
            if st.stop_sequence in seqs:
                issues.append(
                    f"stop_times.txt: duplicate stop_sequence "
                    f"{st.stop_sequence} in trip {st.trip_id}"
                )
            seqs.add(st.stop_sequence)

        shape_ranges: dict[str, tuple[float, float]] = {}
        for sp in self.shapes:
            lo, hi = shape_ranges.get(sp.shape_id, (float("inf"), float("-inf")))
            shape_ranges[sp.shape_id] = (
                min(lo, sp.shape_dist_traveled),
                max(hi, sp.shape_dist_traveled),
            )
        for st in self.stop_times:
            trip = _find_trip(self.trips, st.trip_id)
            if trip and trip.shape_id in shape_ranges:
                lo, hi = shape_ranges[trip.shape_id]
                if st.shape_dist_traveled < lo - 1.0 or st.shape_dist_traveled > hi + 1.0:
                    issues.append(
                        f"stop_times.txt: shape_dist_traveled {st.shape_dist_traveled} "
                        f"out of shape range [{lo:.1f}, {hi:.1f}] for trip {st.trip_id}"
                    )

        return issues


def _find_trip(trips: list[Trip], trip_id: str) -> Trip | None:
    for t in trips:
        if t.trip_id == trip_id:
            return t
    return None


def _write_csv(path: Path, header: list[str], rows: Sequence[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for row in rows:
            w.writerow(_row_values(row, header))


def _row_values(row: Any, header: list[str]) -> list[Any]:
    if hasattr(row, "__dataclass_fields__"):
        field_map = {f.name: getattr(row, f.name) for f in row.__dataclass_fields__.values()}
    elif isinstance(row, dict):
        field_map = row
    else:
        raise TypeError(f"unsupported row type: {type(row).__name__}")
    return [field_map.get(key, "") for key in header]


def write_gtfs_dir(feed: Feed, output_dir: str | Path) -> None:
    """Write all GTFS CSV files to *output_dir*."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    _write_csv(out / "agency.txt", Agency.REQUIRED_FIELDS, feed.agencies)
    _write_csv(out / "calendar.txt", Calendar.REQUIRED_FIELDS, feed.calendars)
    _write_csv(out / "stops.txt", Stop.REQUIRED_FIELDS, feed.stops)
    _write_csv(out / "routes.txt", Route.REQUIRED_FIELDS, feed.routes)
    _write_csv(out / "trips.txt", Trip.REQUIRED_FIELDS, feed.trips)
    _write_csv(out / "stop_times.txt", StopTime.REQUIRED_FIELDS, feed.stop_times)
    _write_csv(out / "shapes.txt", ShapePoint.REQUIRED_FIELDS, feed.shapes)

    sys.stderr.write(
        f"routes={len(feed.routes)} trips={len(feed.trips)} "
        f"stops={len(feed.stops)} shape_pts={len(feed.shapes)}\n"
    )


def write_gtfs_zip(feed: Feed, zip_path: str | Path) -> None:
    """Write all GTFS CSV files into a zip archive at *zip_path*."""
    zip_path = Path(zip_path)
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        write_gtfs_dir(feed, tmpdir)
        with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
            for csv_file in sorted(tmpdir.glob("*.txt")):
                zf.write(csv_file, csv_file.name)
    sys.stderr.write(f"wrote {zip_path}\n")
