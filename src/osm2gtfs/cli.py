"""Command-line entry point for osm2gtfs."""

from __future__ import annotations

import argparse
import sys
from typing import Any

from osm2gtfs import build_gtfs
from osm2gtfs.config import Config
from osm2gtfs.fetch import BboxFilter, RawQuery, RelationIds, Selection


def _parse_relation_ids(value: str) -> RelationIds:
    ids = [int(x.strip()) for x in value.split(",") if x.strip()]
    return RelationIds(ids=ids)


def _parse_bbox(value: str) -> tuple[float, float, float, float]:
    parts = [float(x.strip()) for x in value.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError(
            "bbox must be four comma-separated numbers: south,west,north,east"
        )
    south, west, north, east = parts
    BboxFilter(south=south, west=west, north=north, east=east)  # validate
    return (south, west, north, east)


def _parse_modes(value: str) -> list[str]:
    return [m.strip() for m in value.split(",") if m.strip()]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="osm2gtfs",
        description=(
            "Convert OpenStreetMap route relations into a GTFS feed with real-geometry shapes."
        ),
    )
    parser.add_argument("--version", action="version", version="osm2gtfs 0.1.0")

    # Input selection (mutually exclusive).
    inp = parser.add_argument_group("input selection (choose one)")
    inp_ex = inp.add_mutually_exclusive_group(required=True)
    inp_ex.add_argument(
        "--relation-ids",
        type=_parse_relation_ids,
        help="comma-separated OSM relation ids (e.g. 123,456)",
    )
    inp_ex.add_argument(
        "--bbox",
        type=_parse_bbox,
        help="bounding box: south,west,north,east (e.g. 48.5,7.7,48.6,7.8)",
    )
    inp_ex.add_argument(
        "--query",
        type=str,
        help="raw Overpass QL query (advanced)",
    )

    parser.add_argument(
        "--route-modes",
        type=_parse_modes,
        help="comma-separated OSM route modes for --bbox (e.g. tram,bus); omit for all",
    )

    # Output.
    out = parser.add_argument_group("output")
    out.add_argument(
        "--output",
        type=str,
        default=None,
        help="output directory for GTFS files",
    )
    out.add_argument(
        "--zip",
        action="store_true",
        dest="output_zip",
        default=None,
        help="also produce a GTFS zip archive",
    )

    # Overpass.
    net = parser.add_argument_group("network")
    net.add_argument(
        "--overpass-urls",
        type=str,
        default=None,
        help="comma-separated Overpass API mirrors (tried in order)",
    )
    net.add_argument("--timeout", type=int, default=None, help="request timeout in seconds")

    # Agency.
    ag = parser.add_argument_group("agency")
    ag.add_argument("--agency-name", type=str, default=None, help="agency name")
    ag.add_argument("--agency-url", type=str, default=None, help="agency URL")
    ag.add_argument("--agency-timezone", type=str, default=None, help="agency timezone")

    # Distance knobs.
    geo = parser.add_argument_group("geometry")
    geo.add_argument(
        "--snap-distance",
        type=float,
        default=None,
        help="stop deduplication snap distance in metres (default 35)",
    )
    geo.add_argument(
        "--max-gap",
        type=float,
        default=None,
        help="maximum bridgeable gap between way components in metres (default 100)",
    )
    geo.add_argument(
        "--max-stop-offset",
        type=float,
        default=None,
        help="drop a stop sitting further than this many metres from its shape (default 500)",
    )
    geo.add_argument(
        "--clip",
        type=str,
        default=None,
        help="path to a GeoJSON polygon; geometry and stops outside it are dropped",
    )

    return parser


def main(argv: list[str] | None = None) -> None:
    """Parse command-line arguments and run the conversion.

    Exits with code 1 on error, printing the message to stderr.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Build selection.
    selection: Selection
    if args.relation_ids is not None:
        selection = args.relation_ids
    elif args.bbox is not None:
        south, west, north, east = args.bbox
        modes = args.route_modes
        selection = BboxFilter(south=south, west=west, north=north, east=east, modes=modes)
    elif args.query is not None:
        selection = RawQuery(query=args.query)
    else:
        parser.error("no input selection provided")

    # Build config: defaults -> env -> CLI.
    cli_overrides: dict[str, Any] = {}
    cli_key_map = {
        "overpass_urls": (
            [u.strip() for u in args.overpass_urls.split(",") if u.strip()]
            if args.overpass_urls
            else None
        ),
        "timeout": args.timeout,
        "snap_distance_m": args.snap_distance,
        "max_gap_m": args.max_gap,
        "agency_name": args.agency_name,
        "agency_url": args.agency_url,
        "agency_timezone": args.agency_timezone,
        "output_zip": args.output_zip,
        "output": args.output,
        "clip": args.clip,
        "max_stop_offset_m": args.max_stop_offset,
    }
    for key, value in cli_key_map.items():
        if value is not None:
            cli_overrides[key] = value

    config = Config.from_env().with_overrides(**cli_overrides)

    # Bbox modes override via CLI.
    if isinstance(selection, BboxFilter) and not selection.modes and args.route_modes:
        selection = BboxFilter(
            south=selection.south,
            west=selection.west,
            north=selection.north,
            east=selection.east,
            modes=args.route_modes,
        )

    try:
        summary = build_gtfs(selection, config)
        sys.stderr.write(
            f"done: {summary['routes']} routes, {summary['trips']} trips, "
            f"{summary['stops']} stops, {summary['shape_points']} shape points\n"
        )
    except Exception as exc:
        sys.stderr.write(f"error: {exc}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
