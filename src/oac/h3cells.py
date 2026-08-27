"""Which parts of an aerodrome surface are actually seen.

The ranking says *how much* of a taxi was observed. This says *where*: state
vectors aggregated to H3 cells over the aerodrome, so a reader can see whether
reception covers the runway, the taxiways, the apron, or only the approach.

Two layers, and the split is what makes the map readable:

* ``ground`` -- ``on_ground = true``. Apron, taxiway and runway surface.
* ``low`` -- airborne below :data:`LOW_ALT_FT`. Approach and initial climb.

Anything above that is excluded. A single cruise track passing over the
aerodrome carries hundreds of samples through a handful of cells and would
dominate the density entirely: the map would show the airway, not the taxiways.

Resolution 11 by default -- 28.7 m edge, 2,150 m2. A runway is 45-60 m wide, so
about two cells across it. Resolution 12 (10.8 m) triples the row count to
resolve detail below the position accuracy of the data.
"""

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

#: Ceiling for the airborne layer, feet above the standard datum.
LOW_ALT_FT = 1500.0

#: Metres to feet. The same factor the pipeline publishes altitudes with.
FT_PER_M = 3.28084

#: Radius band identifying "at this aerodrome". The same 5 NM band
#: `track_methods.attach_airport_context` uses, so the map and the ranking
#: cannot disagree about which samples belong where.
ZONE_RADIUS_NM = 5.0

DEFAULT_RES = 11

__all__ = ["LOW_ALT_FT", "ZONE_RADIUS_NM", "DEFAULT_RES", "airport_cells"]


def airport_cells(sv: DataFrame, zones: DataFrame,
                  res: int = DEFAULT_RES) -> DataFrame:
    """`icao, h3, layer, n` -- observed cells per aerodrome, per layer.

    Only cells that were actually observed appear; the table is sparse, which
    is what keeps it small enough to commit.

    `zones` is the aerodrome zone table, which carries **one row per radius
    band**. It is de-duplicated to the innermost band first: joining it as-is
    multiplies every sample by the number of bands an aerodrome has, inflating
    the whole map by a constant factor that looks entirely plausible.
    """
    import h3_pyspark

    z = (
        zones.filter(F.col("apt_max_c_radius_nm") <= ZONE_RADIUS_NM)
        .select(
            F.col("apt_hex_id").alias("h3_res_7"),
            F.col("apt_ident").alias("icao"),
        )
        .dropDuplicates(["h3_res_7", "icao"])
    )

    alt_ft = F.col("baro_altitude_c") * F.lit(FT_PER_M)
    layer = (
        F.when(F.col("on_ground"), F.lit("ground"))
        .when(alt_ft <= F.lit(LOW_ALT_FT), F.lit("low"))
        .otherwise(F.lit(None))
    )

    j = (
        sv.join(z, "h3_res_7", "inner")
        .withColumn("layer", layer)
        # Cruise and anything without a usable altitude are dropped rather
        # than bucketed into "low": an unknown altitude is not a low one.
        .filter(F.col("layer").isNotNull())
    )

    # H3 parents are not string prefixes of their children, so the rollup goes
    # through the library rather than through substring().
    j = j.withColumn("h3", h3_pyspark.h3_to_parent(F.col("h3_res_12"), F.lit(res)))

    return (
        j.filter(F.col("h3").isNotNull())
        .groupBy("icao", "h3", "layer")
        .agg(F.count(F.lit(1)).alias("n"))
    )
