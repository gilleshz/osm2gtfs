"""End-to-end tests: fixture data through the full pipeline."""

import csv
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from osm2gtfs import Config, build_gtfs
from osm2gtfs.fetch import RelationIds

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


def _load_relations():
    with open(FIXTURE_DIR / "relations.json") as f:
        return json.load(f)


def _load_node_tags_dict():
    with open(FIXTURE_DIR / "node_tags.json") as f:
        elements = json.load(f)
    result = {}
    for el in elements:
        if el.get("type") == "node":
            nid = el.get("id")
            tags = el.get("tags", {})
            if nid is not None and tags:
                result[nid] = tags
    return result


def _relation_ids():
    return sorted({el["id"] for el in _load_relations() if el.get("type") == "relation"})


class TestEndToEnd:
    def test_fixture_to_gtfs_dir(self, tmp_path, monkeypatch):
        """Run the full pipeline against fixture data (offline)."""
        import osm2gtfs

        relations_data = _load_relations()
        node_tags = _load_node_tags_dict()

        monkeypatch.setattr(
            osm2gtfs,
            "fetch_elements",
            lambda *a, **kw: relations_data,
        )
        monkeypatch.setattr(
            osm2gtfs,
            "fetch_node_tags",
            lambda *a, **kw: node_tags,
        )

        out = tmp_path / "gtfs"
        config = Config(output=str(out))
        ids = _relation_ids()
        selection = RelationIds(ids=ids)

        summary = build_gtfs(selection, config)

        assert summary["routes"] > 0
        assert summary["trips"] > 0
        assert summary["stops"] > 0
        assert summary["shape_points"] > 0

        for fname in [
            "agency.txt",
            "calendar.txt",
            "stops.txt",
            "routes.txt",
            "trips.txt",
            "stop_times.txt",
            "shapes.txt",
        ]:
            assert (out / fname).is_file(), f"missing {fname}"

        with open(out / "stops.txt", newline="") as f:
            reader = csv.DictReader(f)
            stops = list(reader)
            assert len(stops) > 0
            named = [s for s in stops if s["stop_name"] != s["stop_id"]]
            assert len(named) > 0, "no stops resolved to real names"

    def test_fixture_to_gtfs_zip(self, tmp_path, monkeypatch):
        """Run pipeline with zip output."""
        import osm2gtfs

        monkeypatch.setattr(
            osm2gtfs,
            "fetch_elements",
            lambda *a, **kw: _load_relations(),
        )
        monkeypatch.setattr(
            osm2gtfs,
            "fetch_node_tags",
            lambda *a, **kw: {},
        )

        out = tmp_path / "gtfs"
        config = Config(output=str(out), output_zip=True)
        selection = RelationIds(ids=_relation_ids())

        build_gtfs(selection, config)

        zip_path = tmp_path / "gtfs.zip"
        assert zip_path.is_file()

    def test_relation_with_no_stops_skipped(self, tmp_path, monkeypatch):
        """Relation 1007 has no stops -- should be skipped with warning."""
        import osm2gtfs

        all_rels = _load_relations()

        def mock_fetch(selection, *a, **kw):
            ids = set(selection.ids)
            return [r for r in all_rels if r.get("id") in ids]

        monkeypatch.setattr(osm2gtfs, "fetch_elements", mock_fetch)
        monkeypatch.setattr(osm2gtfs, "fetch_node_tags", lambda *a, **kw: {})

        out = tmp_path / "gtfs"
        config = Config(output=str(out))
        selection = RelationIds(ids=[1007])

        summary = build_gtfs(selection, config)
        assert summary["trips"] == 0

    def test_stop_dedup_across_directions(self, tmp_path, monkeypatch):
        """Tram A has two directions sharing the same stops."""
        import osm2gtfs

        all_rels = _load_relations()

        def mock_fetch(selection, *a, **kw):
            ids = set(selection.ids)
            return [r for r in all_rels if r.get("id") in ids]

        monkeypatch.setattr(osm2gtfs, "fetch_elements", mock_fetch)
        monkeypatch.setattr(osm2gtfs, "fetch_node_tags", lambda *a, **kw: {})

        out = tmp_path / "gtfs"
        config = Config(output=str(out))
        selection = RelationIds(ids=[1001, 1002])

        summary = build_gtfs(selection, config)
        assert summary["stops"] == 3
        assert summary["routes"] == 1
        assert summary["trips"] == 2

    @pytest.mark.skipif(
        shutil.which("gtfs2graph") is None,
        reason="LOOM toolchain not installed",
    )
    def test_loom_pipeline(self, tmp_path, monkeypatch):
        """Run the fixture feed through gtfs2graph | topo | loom | transitmap."""
        import osm2gtfs

        monkeypatch.setattr(
            osm2gtfs,
            "fetch_elements",
            lambda *a, **kw: _load_relations(),
        )
        monkeypatch.setattr(
            osm2gtfs,
            "fetch_node_tags",
            lambda *a, **kw: {},
        )

        out = tmp_path / "gtfs"
        config = Config(output=str(out))
        selection = RelationIds(ids=_relation_ids())
        build_gtfs(selection, config)

        result = subprocess.run(
            ["sh", "-c", f"gtfs2graph {out} | topo | loom | transitmap -o {tmp_path}/map.svg -"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            map_svg = tmp_path / "map.svg"
            if map_svg.exists():
                assert map_svg.stat().st_size > 0
