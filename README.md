# osm2gtfs

Convert OpenStreetMap public-transport route relations into a valid
[GTFS](https://gtfs.org/) feed. The output includes a `shapes.txt` derived
from the OSM way geometry so routes follow the real track or road instead of
straight lines between stops.

The tool produces a standard feed usable by any GTFS consumer: routing engines,
validators, viewers, and transit-map renderers.

## Installation

```bash
pip install git+https://github.com/gilleshz/osm2gtfs.git
```

Or from a local checkout:

```bash
git clone https://github.com/gilleshz/osm2gtfs.git
cd osm2gtfs
pip install -e .
```

## Quick start

Convert a set of OSM route relations by their ids:

```bash
osm2gtfs --relation-ids 123,456,789 --output gtfs_output
```

Convert all tram and bus routes within a bounding box:

```bash
osm2gtfs --bbox 48.5,7.7,48.6,7.8 --route-modes tram,bus --output gtfs_output
```

Pass a raw Overpass query:

```bash
osm2gtfs --query 'relation[route=tram](48.5,7.7,48.6,7.8);out geom;' --output gtfs_output
```

### Options

| Flag | Description |
|---|---|
| `--relation-ids IDS` | Comma-separated OSM relation ids |
| `--bbox S,W,N,E` | Bounding box in decimal degrees |
| `--route-modes MODES` | Filter by OSM route tag (for use with `--bbox`) |
| `--query QUERY` | Raw Overpass QL query |
| `--output DIR` | Output directory for GTFS files |
| `--zip` | Also produce a GTFS zip archive |
| `--overpass-urls URLS` | Comma-separated Overpass API mirrors, tried in order |
| `--timeout SEC` | Request timeout in seconds (default 120) |
| `--snap-distance M` | Stop deduplication radius in metres (default 35) |
| `--max-gap M` | Maximum bridgeable gap between way segments in metres (default 100) |
| `--agency-name NAME` | Agency name (default "OpenStreetMap") |
| `--agency-url URL` | Agency URL |
| `--agency-timezone TZ` | Agency timezone (default "Europe/Paris") |

Environment variables are also supported. Every `--foo-bar` flag has a
corresponding `OSM2GTFS_FOO_BAR` variable. CLI flags take precedence over
environment variables, which take precedence over defaults.

### Library usage

```python
from osm2gtfs import build_gtfs, Config
from osm2gtfs.fetch import RelationIds

config = Config.from_env().with_overrides(output="/tmp/gtfs")
build_gtfs(RelationIds(ids=[123, 456]), config)
```

## How it works

For each selected OSM route relation, the tool:

1. Fetches the relation from an Overpass endpoint with inline geometry.
2. Stitches the member ways into a single polyline, bridging small gaps.
3. Projects stop and platform nodes onto the polyline to order them.
4. Writes the polyline as a `shapes.txt` shape with geodesic
   `shape_dist_traveled` values.
5. Emits one trip per relation referencing that shape, with `stop_times` rows
   whose `shape_dist_traveled` matches the shape.
6. Deduplicates stops that are physically close across lines and directions,
   so they share one `stop_id`.

The `shapes.txt` file is what makes the output follow real geometry rather than
straight lines between stops, which is useful for transit-map rendering.

### LOOM pipeline

The [LOOM](https://github.com/ad-freiburg/loom) transit-map toolchain
(`gtfs2graph | topo | loom | transitmap`) consumes GTFS and uses `shapes.txt`
for geometry. The two tools work well together:

```bash
osm2gtfs --relation-ids 123,456 --output gtfs
gtfs2graph gtfs | topo | loom | transitmap -o map.svg -
```

## Development

```bash
pip install -e ".[dev]"
ruff format src/ tests/
ruff check src/ tests/
mypy src/
pytest
```

## License

MIT
