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

# `BBOX` and `in_bbox` live in `oac.bbox`, which imports nothing, and are
# re-exported here so the cluster scripts keep their single import. The site
# must take them from `oac.bbox` instead: reaching them through this module
# pulls pyspark into a render that has none.
from oac.bbox import BBOX, in_bbox

__all__ = ["BBOX", "in_bbox", "airports_in_bbox"]


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
