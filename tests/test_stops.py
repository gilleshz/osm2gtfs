"""Tests for stop deduplication and name resolution."""

from osm2gtfs.stops import StopRegistry, resolve_stop_names


class TestStopRegistry:
    def test_same_location_same_id(self):
        reg = StopRegistry(snap_distance_m=50)
        sid1 = reg.id_for(7.75, 48.58, "Stop A")
        sid2 = reg.id_for(7.75, 48.58, "Stop A")
        assert sid1 == sid2

    def test_nearby_stops_merge(self):
        reg = StopRegistry(snap_distance_m=500)
        # Two stops ~100 m apart should merge with a 500 m snap radius.
        sid1 = reg.id_for(7.750, 48.580)
        sid2 = reg.id_for(7.751, 48.580)
        assert sid1 == sid2

    def test_distant_stops_dont_merge(self):
        reg = StopRegistry(snap_distance_m=50)
        sid1 = reg.id_for(7.75, 48.58)
        sid2 = reg.id_for(7.76, 48.59)
        assert sid1 != sid2

    def test_name_filled_if_empty(self):
        reg = StopRegistry()
        reg.id_for(7.75, 48.58)
        reg.id_for(7.75, 48.58, "Central")
        assert reg.entries[0].stop_name == "Central"

    def test_name_not_overwritten(self):
        reg = StopRegistry()
        reg.id_for(7.75, 48.58, "First")
        reg.id_for(7.75, 48.58, "Second")
        assert reg.entries[0].stop_name == "First"

    def test_deterministic_ids(self):
        reg = StopRegistry()
        ids1 = [reg.id_for(lon / 100, lat / 100) for lon, lat in [(775, 4858), (776, 4859)]]
        reg2 = StopRegistry()
        ids2 = [reg2.id_for(lon / 100, lat / 100) for lon, lat in [(775, 4858), (776, 4859)]]
        assert ids1 == ids2

    def test_update_name(self):
        reg = StopRegistry()
        sid = reg.id_for(7.75, 48.58)
        reg.update_name(sid, "Central")
        assert reg.entries[0].stop_name == "Central"

    def test_update_name_does_not_overwrite(self):
        reg = StopRegistry()
        sid = reg.id_for(7.75, 48.58, "First")
        reg.update_name(sid, "Second")
        assert reg.entries[0].stop_name == "First"

    def test_update_name_ignores_unknown_id(self):
        reg = StopRegistry()
        reg.id_for(7.75, 48.58)
        reg.update_name("S999", "Central")
        assert reg.entries[0].stop_name == ""

    def test_merges_across_a_cell_boundary(self):
        reg = StopRegistry(snap_distance_m=35)
        step = 35 / 6378137 * 180 / 3.141592653589793
        # Straddle a grid boundary so the pair only merges if neighbours are searched.
        base = step * 1000
        sid1 = reg.id_for(base - 1e-7, 48.58)
        sid2 = reg.id_for(base + 1e-7, 48.58)
        assert sid1 == sid2

    def test_merges_at_far_eastern_longitude(self):
        reg = StopRegistry(snap_distance_m=50)
        sid1 = reg.id_for(179.9990, 60.0)
        sid2 = reg.id_for(179.9994, 60.0)
        assert sid1 == sid2

    def test_first_registered_wins_when_several_are_in_range(self):
        reg = StopRegistry(snap_distance_m=500)
        first = reg.id_for(7.7500, 48.58, "First")
        reg.id_for(7.7505, 48.58, "Second")
        assert reg.id_for(7.7502, 48.58) == first

    def test_distant_stops_dont_merge_at_high_latitude(self):
        reg = StopRegistry(snap_distance_m=35)
        sid1 = reg.id_for(20.0, 70.0)
        sid2 = reg.id_for(20.01, 70.0)
        assert sid1 != sid2


class TestResolveStopNames:
    def test_resolves_names_from_tags(self):
        reg = StopRegistry()
        sid = reg.id_for(7.75, 48.58)
        node_tags = {3001: {"name": "Gare Centrale"}}
        resolve_stop_names(reg, node_tags, [(3001, sid)])
        assert reg.entries[0].stop_name == "Gare Centrale"

    def test_falls_back_to_ref(self):
        reg = StopRegistry()
        sid = reg.id_for(7.75, 48.58)
        node_tags = {3001: {"ref": "GC"}}
        resolve_stop_names(reg, node_tags, [(3001, sid)])
        assert reg.entries[0].stop_name == "GC"

    def test_missing_node_id_skipped(self):
        reg = StopRegistry()
        sid = reg.id_for(7.75, 48.58)
        node_tags = {}
        resolve_stop_names(reg, node_tags, [(3001, sid)])
        assert reg.entries[0].stop_name == ""

    def test_falls_back_to_synthetic_name(self):
        reg = StopRegistry()
        sid = reg.id_for(7.75, 48.58)
        node_tags = {3001: {}}
        resolve_stop_names(reg, node_tags, [(3001, sid)])
        assert "3001" in reg.entries[0].stop_name
