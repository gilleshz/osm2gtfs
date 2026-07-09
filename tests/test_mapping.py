"""Tests for OSM tag -> GTFS attribute mapping."""

from osm2gtfs.mapping import (
    ROUTE_TYPE_MAP,
    extract_route_attrs,
    make_route_id,
    route_type,
)


class TestRouteType:
    def test_known_modes(self):
        assert route_type("tram") == 0
        assert route_type("subway") == 1
        assert route_type("metro") == 1
        assert route_type("train") == 2
        assert route_type("rail") == 2
        assert route_type("bus") == 3
        assert route_type("ferry") == 4
        assert route_type("aerialway") == 6
        assert route_type("cable_car") == 6
        assert route_type("gondola") == 6
        assert route_type("funicular") == 7
        assert route_type("trolleybus") == 11
        assert route_type("monorail") == 12

    def test_high_speed_rail(self):
        assert route_type("high_speed_train") == 101
        assert route_type("long_distance_train") == 102
        assert route_type("intercity_train") == 102

    def test_unknown_mode_defaults(self):
        assert route_type("unknown_mode") == 3  # default bus
        assert route_type("") == 3

    def test_custom_default(self):
        assert route_type("unknown", default=0) == 0

    def test_all_entries_are_valid_integers(self):
        for _tag, value in ROUTE_TYPE_MAP.items():
            assert isinstance(value, int)
            assert value >= 0


class TestExtractRouteAttrs:
    def test_extracts_ref_as_short_name(self):
        attrs = extract_route_attrs({"route": "tram", "ref": "A", "name": "Line A"})
        assert attrs.route_short_name == "A"
        assert attrs.route_long_name == "Line A"

    def test_falls_back_to_name(self):
        attrs = extract_route_attrs({"route": "bus", "name": "Bus 42"})
        assert attrs.route_short_name == "Bus 42"

    def test_colour_parsing_with_hash(self):
        attrs = extract_route_attrs({"route": "tram", "ref": "A", "colour": "#FF0000"})
        assert attrs.route_color == "FF0000"

    def test_colour_parsing_without_hash(self):
        attrs = extract_route_attrs({"route": "tram", "ref": "A", "colour": "00FF00"})
        assert attrs.route_color == "00FF00"

    def test_missing_colour_defaults(self):
        attrs = extract_route_attrs({"route": "tram", "ref": "A"})
        assert attrs.route_color == "888888"

    def test_invalid_colour_defaults(self):
        attrs = extract_route_attrs({"route": "tram", "ref": "A", "colour": "zzz"})
        assert attrs.route_color == "888888"

    def test_text_colour_dark_bg(self):
        attrs = extract_route_attrs({"route": "tram", "ref": "A", "colour": "#000000"})
        assert attrs.route_text_color == "FFFFFF"

    def test_text_colour_light_bg(self):
        attrs = extract_route_attrs({"route": "tram", "ref": "A", "colour": "#FFFFFF"})
        assert attrs.route_text_color == "000000"

    def test_network_and_operator(self):
        attrs = extract_route_attrs(
            {"route": "tram", "ref": "A", "network": "CTS", "operator": "CTS"}
        )
        assert attrs.network == "CTS"
        assert attrs.operator == "CTS"

    def test_route_type_from_tags(self):
        attrs = extract_route_attrs({"route": "subway", "ref": "M"})
        assert attrs.route_type == 1


class TestMakeRouteId:
    def test_same_line_different_directions(self):
        tags1 = {"route": "tram", "network": "CTS", "ref": "A"}
        tags2 = {"route": "tram", "network": "CTS", "ref": "A"}
        assert make_route_id(tags1) == make_route_id(tags2)

    def test_different_lines(self):
        tags_a = {"route": "tram", "network": "CTS", "ref": "A"}
        tags_b = {"route": "tram", "network": "CTS", "ref": "B"}
        assert make_route_id(tags_a) != make_route_id(tags_b)

    def test_missing_network(self):
        rid = make_route_id({"route": "tram", "ref": "A"})
        assert rid == "tram||A"

    def test_falls_back_to_name(self):
        rid = make_route_id({"route": "bus", "name": "Bus 42"})
        assert rid == "bus||Bus 42"
