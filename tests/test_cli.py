"""Tests for CLI argument parsing and env var handling."""

import os

import pytest

from osm2gtfs.cli import _build_parser
from osm2gtfs.config import Config


class TestParser:
    def test_relation_ids(self):
        parser = _build_parser()
        args = parser.parse_args(["--relation-ids", "123,456", "--output", "out"])
        assert args.relation_ids.ids == [123, 456]

    def test_bbox(self):
        parser = _build_parser()
        args = parser.parse_args(["--bbox", "48.5,7.7,48.6,7.8", "--output", "out"])
        assert args.bbox == (48.5, 7.7, 48.6, 7.8)

    def test_bbox_with_modes(self):
        parser = _build_parser()
        args = parser.parse_args(
            ["--bbox", "48.5,7.7,48.6,7.8", "--route-modes", "tram,bus", "--output", "out"]
        )
        assert args.route_modes == ["tram", "bus"]

    def test_raw_query(self):
        parser = _build_parser()
        args = parser.parse_args(
            ["--query", "relation[route=tram](48.5,7.7,48.6,7.8);out geom;", "--output", "out"]
        )
        assert "tram" in args.query

    def test_mutually_exclusive(self):
        parser = _build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--relation-ids", "1", "--bbox", "48,7,49,8"])

    def test_no_input_selection(self):
        parser = _build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--output", "out"])

    def test_snap_distance(self):
        parser = _build_parser()
        args = parser.parse_args(
            ["--relation-ids", "1", "--snap-distance", "75", "--output", "out"]
        )
        assert args.snap_distance == 75.0

    def test_max_gap(self):
        parser = _build_parser()
        args = parser.parse_args(["--relation-ids", "1", "--max-gap", "200", "--output", "out"])
        assert args.max_gap == 200.0

    def test_agency_flags(self):
        parser = _build_parser()
        args = parser.parse_args(
            [
                "--relation-ids",
                "1",
                "--output",
                "out",
                "--agency-name",
                "Test",
                "--agency-url",
                "https://example.com",
                "--agency-timezone",
                "UTC",
            ]
        )
        assert args.agency_name == "Test"

    def test_overpass_flags(self):
        parser = _build_parser()
        args = parser.parse_args(
            [
                "--relation-ids",
                "1",
                "--output",
                "out",
                "--overpass-url",
                "https://overpass.example.com/api/interpreter",
                "--timeout",
                "60",
            ]
        )
        assert args.overpass_url == "https://overpass.example.com/api/interpreter"
        assert args.timeout == 60

    def test_zip_flag(self):
        parser = _build_parser()
        args = parser.parse_args(["--relation-ids", "1", "--output", "out", "--zip"])
        assert args.output_zip is True


class TestConfigEnv:
    def test_env_overrides_defaults(self):
        os.environ["OSM2GTFS_AGENCY_NAME"] = "EnvAgency"
        try:
            config = Config.from_env()
            assert config.agency_name == "EnvAgency"
        finally:
            del os.environ["OSM2GTFS_AGENCY_NAME"]

    def test_env_int_parsing(self):
        os.environ["OSM2GTFS_TIMEOUT"] = "60"
        try:
            config = Config.from_env()
            assert config.timeout == 60
        finally:
            del os.environ["OSM2GTFS_TIMEOUT"]

    def test_env_bool_parsing(self):
        os.environ["OSM2GTFS_OUTPUT_ZIP"] = "true"
        try:
            config = Config.from_env()
            assert config.output_zip is True
        finally:
            del os.environ["OSM2GTFS_OUTPUT_ZIP"]

    def test_env_bool_false(self):
        os.environ["OSM2GTFS_OUTPUT_ZIP"] = "0"
        try:
            config = Config.from_env()
            assert config.output_zip is False
        finally:
            del os.environ["OSM2GTFS_OUTPUT_ZIP"]

    def test_with_overrides(self):
        config = Config(agency_name="Default")
        updated = config.with_overrides(agency_name="Override")
        assert updated.agency_name == "Override"

    def test_with_overrides_ignores_none(self):
        config = Config(agency_name="Default")
        updated = config.with_overrides(agency_name=None)
        assert updated.agency_name == "Default"

    def test_with_overrides_unknown_key_ignored(self):
        config = Config()
        updated = config.with_overrides(nonexistent="value")
        assert updated == config
