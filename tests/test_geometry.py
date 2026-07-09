"""Tests for geometry: way stitching, geodesic distances, stop projection."""

from shapely.geometry import LineString

from osm2gtfs.geometry import (
    cumulative_geodesic_distances,
    geodesic_distance_m,
    project_and_order,
    stitch_ways,
)


def _way(ref, role, coords):
    return {
        "type": "way",
        "ref": ref,
        "role": role,
        "geometry": [{"lon": x, "lat": y} for x, y in coords],
    }


def _node(ref, role, lon, lat):
    return {"type": "node", "ref": ref, "role": role, "lon": lon, "lat": lat}


class TestStitchWays:
    def test_contiguous_ways(self):
        members = [
            _way(1, "", [(0, 0), (1, 1)]),
            _way(2, "", [(1, 1), (2, 2)]),
        ]
        result = stitch_ways(members)
        assert result is not None
        assert len(list(result.coords)) == 3  # merged: 2 segments -> 3 points

    def test_reversed_way(self):
        members = [
            _way(1, "", [(0, 0), (1, 1)]),
            _way(2, "", [(2, 2), (1, 1)]),  # reversed
        ]
        result = stitch_ways(members)
        assert result is not None
        # linemerge should connect 0,0->1,1 and 1,1->2,2
        coords = list(result.coords)
        assert len(coords) >= 3

    def test_out_of_order_ways(self):
        members = [
            _way(2, "", [(1, 1), (2, 2)]),
            _way(1, "", [(0, 0), (1, 1)]),
        ]
        result = stitch_ways(members)
        assert result is not None

    def test_multi_component_bridging(self):
        members = [
            _way(1, "", [(0, 0), (1, 1)]),
            _way(2, "", [(1.05, 1.05), (2, 2)]),
        ]
        result = stitch_ways(members, max_gap_m=20000)
        assert result is not None
        coords = list(result.coords)
        assert coords[0] == (0, 0)
        assert coords[-1] == (2, 2)

    def test_excludes_stop_roles(self):
        members = [
            _way(1, "", [(0, 0), (1, 1)]),
            _way(2, "stop", [(1, 1), (2, 2)]),
            _way(3, "platform", [(2, 2), (3, 3)]),
        ]
        result = stitch_ways(members)
        assert result is not None
        coords = list(result.coords)
        assert coords[-1] == (1, 1)

    def test_empty_members_returns_none(self):
        assert stitch_ways([]) is None

    def test_single_way(self):
        members = [_way(1, "", [(0, 0), (1, 1)])]
        result = stitch_ways(members)
        assert result is not None
        assert len(list(result.coords)) == 2

    def test_insufficient_points(self):
        members = [_way(1, "", [(0, 0)])]
        assert stitch_ways(members) is None


class TestCumulativeGeodesicDistances:
    def test_two_points(self):
        dists = cumulative_geodesic_distances([(7.75, 48.58), (7.76, 48.58)])
        assert len(dists) == 2
        assert dists[0] == 0.0
        assert dists[1] > 0

    def test_monotonically_increasing(self):
        coords = [(7.75, 48.58), (7.76, 48.59), (7.77, 48.60)]
        dists = cumulative_geodesic_distances(coords)
        assert dists == sorted(dists)
        for i in range(len(dists) - 1):
            assert dists[i + 1] > dists[i]

    def test_single_point(self):
        assert cumulative_geodesic_distances([(7.75, 48.58)]) == [0.0]

    def test_empty(self):
        assert cumulative_geodesic_distances([]) == []

    def test_shape_dist_consistency(self):
        """Values are positive and the total is reasonable."""
        coords = [(7.75, 48.58), (7.76, 48.58), (7.77, 48.58)]
        dists = cumulative_geodesic_distances(coords)
        total = dists[-1]
        assert 1000 < total < 10000  # ~1-10 km at this latitude


class TestProjectAndOrder:
    def test_orders_stops_along_line(self):
        polyline = LineString([(0, 0), (10, 0)])
        stops = [(8, 0), (2, 0), (5, 0)]
        result = project_and_order(polyline, stops)
        assert [r[1] for r in result] == [2, 5, 8]

    def test_stop_off_track_projects(self):
        polyline = LineString([(0, 0), (10, 0)])
        stops = [(5, 1)]
        result = project_and_order(polyline, stops)
        assert len(result) == 1
        # The stop projects to x~5 on the line
        assert 4.9 < result[0][1] < 5.1

    def test_duplicate_stops_deduplicated(self):
        polyline = LineString([(0, 0), (10, 0)])
        stops = [(5, 0), (5, 0)]
        result = project_and_order(polyline, stops)
        assert len(result) == 1


class TestGeodesicDistanceM:
    def test_zero_distance(self):
        assert geodesic_distance_m(7.75, 48.58, 7.75, 48.58) == 0.0

    def test_positive_distance(self):
        d = geodesic_distance_m(7.75, 48.58, 7.76, 48.58)
        assert d > 0
        assert 500 < d < 2000  # ~1 km at this latitude

    def test_symmetry(self):
        d1 = geodesic_distance_m(7.75, 48.58, 7.76, 48.59)
        d2 = geodesic_distance_m(7.76, 48.59, 7.75, 48.58)
        assert abs(d1 - d2) < 0.01
