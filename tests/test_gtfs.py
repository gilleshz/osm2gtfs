"""Tests for GTFS dataclasses, feed validation, and CSV writing."""

import csv

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


def _sample_feed():
    return Feed(
        agencies=[Agency("OSM", "OpenStreetMap", "https://osm.org", "Europe/Paris")],
        calendars=[Calendar("WEEK", 1, 1, 1, 1, 1, 1, 1, "20200101", "20301231")],
        stops=[
            Stop("S0", "Central", 48.58, 7.75),
            Stop("S1", "Universite", 48.584, 7.754),
        ],
        routes=[Route("tram|CTS|A", "OSM", "A", "Tram A", 0, "FF0000", "FFFFFF")],
        trips=[Trip("tram|CTS|A", "WEEK", "t_1001", "sh_1001")],
        stop_times=[
            StopTime("t_1001", "08:00:00", "08:00:00", "S0", 1, 0.0),
            StopTime("t_1001", "08:01:00", "08:01:00", "S1", 2, 100.0),
        ],
        shapes=[
            ShapePoint("sh_1001", 48.58, 7.75, 0, 0.0),
            ShapePoint("sh_1001", 48.581, 7.751, 1, 50.0),
            ShapePoint("sh_1001", 48.584, 7.754, 2, 100.0),
        ],
    )


class TestFeedValidate:
    def test_valid_feed_no_issues(self):
        feed = _sample_feed()
        assert feed.validate() == []

    def test_empty_feed_reports_issues(self):
        feed = Feed()
        issues = feed.validate()
        assert len(issues) >= 4  # multiple missing required files

    def test_duplicate_stop_sequence(self):
        feed = _sample_feed()
        feed.stop_times.append(StopTime("t_1001", "08:01:00", "08:01:00", "S1", 2, 100.0))
        issues = feed.validate()
        assert any("duplicate stop_sequence" in i for i in issues)

    def test_non_monotonic_shape_dist(self):
        feed = _sample_feed()
        feed.shapes = [
            ShapePoint("sh_1001", 48.58, 7.75, 0, 100.0),
            ShapePoint("sh_1001", 48.581, 7.751, 1, 50.0),  # decreasing!
        ]
        issues = feed.validate()
        assert any("not monotonic" in i for i in issues)

    def test_route_type_negative(self):
        feed = _sample_feed()
        feed.routes = [Route("bad", "OSM", "X", "X", -1, "FF0000", "FFFFFF")]
        issues = feed.validate()
        assert any("route_type" in i for i in issues)

    def test_missing_agency(self):
        feed = _sample_feed()
        feed.agencies = []
        issues = feed.validate()
        assert any("agency" in i for i in issues)

    def test_missing_trips(self):
        feed = _sample_feed()
        feed.trips = []
        issues = feed.validate()
        assert any("trips" in i for i in issues)


class TestWriteGtfsDir:
    def test_all_files_created(self, tmp_path):
        feed = _sample_feed()
        out = tmp_path / "gtfs"
        write_gtfs_dir(feed, out)
        expected_files = [
            "agency.txt",
            "calendar.txt",
            "stops.txt",
            "routes.txt",
            "trips.txt",
            "stop_times.txt",
            "shapes.txt",
        ]
        for fname in expected_files:
            assert (out / fname).is_file()

    def test_csv_headers(self, tmp_path):
        feed = _sample_feed()
        out = tmp_path / "gtfs"
        write_gtfs_dir(feed, out)
        with open(out / "routes.txt", newline="") as f:
            reader = csv.reader(f)
            header = next(reader)
            assert "route_id" in header
            assert "route_type" in header

    def test_csv_content(self, tmp_path):
        feed = _sample_feed()
        out = tmp_path / "gtfs"
        write_gtfs_dir(feed, out)
        with open(out / "stops.txt", newline="") as f:
            reader = csv.reader(f)
            next(reader)  # skip header
            rows = list(reader)
            assert len(rows) == 2  # S0 and S1


class TestWriteGtfsZip:
    def test_zip_created(self, tmp_path):
        feed = _sample_feed()
        zip_path = tmp_path / "gtfs.zip"
        write_gtfs_zip(feed, zip_path)
        assert zip_path.is_file()
        import zipfile

        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            assert "agency.txt" in names
            assert "stops.txt" in names
