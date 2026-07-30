"""Tests for geometry: way stitching, geodesic distances, stop projection."""

import json

from shapely.geometry import LineString, Polygon

from osm2gtfs.geometry import (
    clip_to_boundary,
    cumulative_geodesic_distances,
    geodesic_distance_m,
    load_clip_boundary,
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

    def test_does_not_cross_a_gap_wider_than_max_gap(self):
        members = [
            _way(1, "", [(7.50, 47.00), (7.70, 47.00)]),
            _way(2, "", [(9.00, 47.00), (9.05, 47.00)]),
        ]
        result = stitch_ways(members, max_gap_m=100)
        assert result is not None
        assert list(result.coords) == [(7.50, 47.00), (7.70, 47.00)]

    def test_keeps_the_longest_chain_when_a_gap_splits_the_relation(self):
        members = [
            _way(1, "", [(7.00, 47.00), (7.01, 47.00)]),
            _way(2, "", [(8.00, 47.00), (8.20, 47.00)]),
            _way(3, "", [(8.2001, 47.00), (8.40, 47.00)]),
        ]
        result = stitch_ways(members, max_gap_m=100)
        assert result is not None
        coords = list(result.coords)
        assert coords[0] == (8.00, 47.00)
        assert coords[-1] == (8.40, 47.00)

    def test_bridges_to_the_nearer_end_of_a_backwards_component(self):
        members = [
            _way(1, "", [(7.000, 47.00), (7.010, 47.00)]),
            _way(
                2,
                "",
                [
                    (7.030, 47.00),
                    (7.025, 47.00),
                    (7.020, 47.00),
                    (7.015, 47.00),
                    (7.0101, 47.00),
                ],
            ),
        ]
        result = stitch_ways(members, max_gap_m=100)
        assert result is not None
        coords = list(result.coords)
        assert {coords[0], coords[-1]} == {(7.000, 47.00), (7.030, 47.00)}
        longest = max(
            geodesic_distance_m(a[0], a[1], b[0], b[1])
            for a, b in zip(coords, coords[1:], strict=False)
        )
        assert longest < 1000


class TestProjectAndOrderOffset:
    LINE = LineString([(7.0, 47.0), (7.1, 47.0)])

    def test_keeps_a_stop_beside_the_line(self):
        out = project_and_order(self.LINE, [(7.05, 47.0005)], max_offset_m=500)
        assert len(out) == 1

    def test_drops_a_stop_far_from_the_line(self):
        out = project_and_order(self.LINE, [(7.05, 47.5)], max_offset_m=500)
        assert out == []

    def test_drops_a_stop_beyond_the_end_of_the_line(self):
        out = project_and_order(self.LINE, [(8.0, 47.0)], max_offset_m=500)
        assert out == []

    def test_keeps_everything_when_no_limit_is_given(self):
        out = project_and_order(self.LINE, [(7.05, 47.5), (8.0, 47.0)])
        assert len(out) == 2

    def test_reports_original_coordinates_not_the_projection(self):
        out = project_and_order(self.LINE, [(7.05, 47.0005)], max_offset_m=500)
        assert out[0][1] == 7.05
        assert out[0][2] == 47.0005


class TestClipToBoundary:
    BOX = Polygon([(7.0, 47.0), (8.0, 47.0), (8.0, 48.0), (7.0, 48.0)])

    def test_keeps_a_line_fully_inside(self):
        line = LineString([(7.2, 47.2), (7.8, 47.8)])
        kept, dropped = clip_to_boundary(line, self.BOX)
        assert kept is not None
        assert dropped == 0.0
        assert kept.length == line.length

    def test_trims_a_line_that_leaves_the_boundary(self):
        line = LineString([(7.5, 47.5), (9.5, 47.5)])
        kept, dropped = clip_to_boundary(line, self.BOX)
        assert kept is not None
        assert dropped == 0.0
        assert max(x for x, _ in kept.coords) <= 8.0 + 1e-9

    def test_returns_none_for_a_line_entirely_outside(self):
        line = LineString([(9.0, 47.5), (9.5, 47.5)])
        kept, dropped = clip_to_boundary(line, self.BOX)
        assert kept is None
        assert dropped == 0.0

    def test_keeps_only_the_longest_piece_when_the_line_re_enters(self):
        line = LineString([(7.1, 47.5), (7.2, 47.5), (8.5, 47.5), (7.4, 47.6), (7.9, 47.6)])
        kept, dropped = clip_to_boundary(line, self.BOX)
        assert kept is not None
        assert dropped > 0
        pieces = line.intersection(self.BOX)
        assert kept.length == max(g.length for g in pieces.geoms)


class TestLoadClipBoundary:
    def test_reads_a_bare_polygon(self, tmp_path):
        p = tmp_path / "b.geojson"
        p.write_text(
            json.dumps({"type": "Polygon", "coordinates": [[[7, 47], [8, 47], [8, 48], [7, 47]]]})
        )
        assert load_clip_boundary(str(p)).is_valid

    def test_reads_a_feature_collection(self, tmp_path):
        p = tmp_path / "b.geojson"
        p.write_text(
            json.dumps(
                {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {},
                            "geometry": {
                                "type": "Polygon",
                                "coordinates": [[[7, 47], [8, 47], [8, 48], [7, 47]]],
                            },
                        }
                    ],
                }
            )
        )
        assert load_clip_boundary(str(p)).is_valid


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
