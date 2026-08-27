"""Ground truth for the coverage study: the ingestion bounding box.

Everything about *what a flight is* comes from `opdi`'s `track_truth`, which
this module imports rather than reimplements -- including the block times,
which were added there because APDF's `SRC_PHASE` discrimination already lived
there and a second copy of it would be a second way to get it wrong.

What is added here is the one thing a per-aerodrome cut needs and a
Europe-wide study did not: the bounding-box filter that keeps an un-ingested
aerodrome out of the ranking.
"""

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

#: The ingestion bounding box, copied from `benchmarks/osn_sample.py:BBOX`.
#: min_lon, min_lat, max_lon, max_lat.
#:
#: Duplicated rather than imported on purpose: importing it would make every
#: consumer of this module depend on `osn_sample`, which opens a Spark session
#: and reads `.env` at import time. `test_bbox_matches_osn_sample` asserts the
#: two are equal, so the copy cannot drift silently.
BBOX = (-25.86653, 26.74617, 49.65699, 70.25976)

__all__ = ["BBOX", "in_bbox", "airports_in_bbox"]


def in_bbox(lon, lat):
    """Column expression: is this position inside the ingested area."""
    min_lon, min_lat, max_lon, max_lat = BBOX
    return (lon >= min_lon) & (lon <= max_lon) & (lat >= min_lat) & (lat <= max_lat)


def airports_in_bbox(spark: SparkSession, airports_path: str) -> DataFrame:
    """OurAirports aerodromes inside the ingestion bbox: `icao, name, lat, lon`.

    An aerodrome outside it appears in the NM flight table -- a Dubai-to-
    Frankfurt flight has ADEP OMDB -- but its departure was never ingested, so
    a detection rate computed for it measures the bounding box rather than the
    receiver network.

    Excluding them is the difference between "no coverage" and "not in scope",
    and **nothing in the resulting number distinguishes the two**: both are a
    detection rate near zero. An aerodrome that is genuinely unreceived is the
    study's most important finding; one that was never sampled is noise that
    would sit at the bottom of the ranking looking exactly like a finding.
    """
    return (
        spark.read.parquet(airports_path)
        .select(
            F.col("ident").alias("icao"),
            F.col("name").alias("name"),
            F.col("latitude_deg").cast("double").alias("lat"),
            F.col("longitude_deg").cast("double").alias("lon"),
        )
        .filter(F.col("icao").isNotNull())
        .filter(in_bbox(F.col("lon"), F.col("lat")))
        .dropDuplicates(["icao"])
    )
