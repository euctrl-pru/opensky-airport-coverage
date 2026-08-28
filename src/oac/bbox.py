"""The ingestion bounding box, and the test for being inside it.

Split out of `oac.truth` because the *site* needs the box and nothing else.
`truth` imports `pyspark` at module level -- it builds Spark DataFrames -- so
`from oac.truth import BBOX` dragged pyspark into the Quarto render, which
runs in GitHub Actions where `pip install -e .` never installs it. The
constant itself is four floats; it has no business requiring a cluster.

Nothing here may import pyspark, opdi, or anything outside the main
dependency list. `tests/test_imports.py` enforces that.
"""

#: The ingestion bounding box, copied from `benchmarks/osn_sample.py:BBOX`.
#: min_lon, min_lat, max_lon, max_lat.
#:
#: Duplicated rather than imported on purpose: importing it would make every
#: consumer of this module depend on `osn_sample`, which opens a Spark session
#: and reads `.env` at import time. `test_bbox_matches_osn_sample` asserts the
#: two are equal, so the copy cannot drift silently.
BBOX = (-25.86653, 26.74617, 49.65699, 70.25976)

__all__ = ["BBOX", "in_bbox"]


def in_bbox(lon, lat):
    """Is this position inside the ingested area.

    Written in operators only, so it is a Spark column expression when handed
    Columns and a plain boolean when handed numbers -- which is why this can
    live in a module that never imports pyspark.
    """
    min_lon, min_lat, max_lon, max_lat = BBOX
    return (lon >= min_lon) & (lon <= max_lon) & (lat >= min_lat) & (lat <= max_lat)
