"""Shared fixtures for osm2gtfs tests."""

import json
from pathlib import Path

import pytest

from osm2gtfs.config import Config

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def relations_data():
    """Load the recorded Overpass relations response."""
    with open(FIXTURE_DIR / "relations.json") as f:
        return json.load(f)


@pytest.fixture
def node_tags_data():
    """Load the recorded Overpass node tags response."""
    with open(FIXTURE_DIR / "node_tags.json") as f:
        return json.load(f)


@pytest.fixture
def sample_config(tmp_path):
    """A Config suitable for offline tests."""
    return Config(output=str(tmp_path / "gtfs"))


@pytest.fixture
def node_tags_map(node_tags_data):
    """Node tags as a dict keyed by node id."""
    result = {}
    for el in node_tags_data:
        if el.get("type") == "node":
            nid = el.get("id")
            tags = el.get("tags", {})
            if nid is not None and tags:
                result[nid] = tags
    return result
