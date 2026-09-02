"""What counts as a report, for every metric on this site.

**A state vector without a latitude and longitude is not a position report,
and nothing here counts it as one.**

The distinction is not pedantic. A state vector is a snapshot of whatever
OpenSky decoded for one aircraft in one second, and position is only one of
the things a transponder broadcasts -- callsign, velocity, vertical rate and
altitude arrive in separate message types. So a row can be correctly
attributed to that aircraft and that second and carry no position at all.

Counting those rows produced a contradiction the site could not explain.
Istanbul (LTFM) receives nothing whatever from its surface: 429 observed H3
cells, every one of them airborne, and not a single `on_ground` report in the
sample. Yet its median arrival scored `land_s` of **+225 s** -- "the track ran
on past landing, the good case" -- and its taxi-in signal came out at 0.299.
The best-observed arrival's last *positioned* report was at 1,575 ft, nine
kilometres short of the threshold, while its track ran on for a further ten
minutes. Those ten minutes were reports with no position: enough to move
`trk_end`, enough to fill occupancy bins, and impossible to draw on a map or
assign to a cell.

It was not confined to Istanbul. Five aerodromes with **zero** ground reports
scored `arr_signal_p50 = 1.000`, and 189 aerodromes never heard on the ground
had a positive median `land_s`.

The filter is applied **at read time**, before segmentation, so no
downstream step can disagree about the population. That has one consequence
worth stating: `assign_track_id` breaks tracks on time gaps, and a gap
previously bridged by position-less rows may now exceed the threshold and
split a track that is genuinely one trajectory. That is the honest trade --
a track whose continuity rests on reports that never said where the aircraft
was is not a continuity this site can evidence.
"""

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

#: The columns a report must have to be one.
POSITION_COLUMNS = ("lat", "lon")

__all__ = ["POSITION_COLUMNS", "positioned", "position_share"]


def positioned(sv: DataFrame) -> DataFrame:
    """Rows carrying a usable position. Apply immediately after the read.

    Raises rather than passing the frame through when the columns are absent:
    a silent no-op here would restore the old behaviour everywhere at once,
    and every number on the site would move with nothing to say why.
    """
    missing = [c for c in POSITION_COLUMNS if c not in sv.columns]
    if missing:
        raise ValueError(
            f"cannot filter to positioned reports: frame lacks {missing}")
    return sv.filter(F.col("lat").isNotNull() & F.col("lon").isNotNull())


def position_share(sv: DataFrame) -> dict:
    """`{rows, positioned, dropped, share}` -- what the filter removes.

    Reported by the extraction scripts rather than inferred. How much of the
    feed carries no position is itself a finding about the receiver network,
    and it is the number that says how far the published figures moved when
    this filter went in.
    """
    row = sv.agg(
        F.count(F.lit(1)).alias("rows"),
        F.sum(F.when(F.col("lat").isNotNull() & F.col("lon").isNotNull(), 1)
              .otherwise(0)).alias("positioned"),
    ).collect()[0]
    rows, pos = int(row["rows"]), int(row["positioned"] or 0)
    return {"rows": rows, "positioned": pos, "dropped": rows - pos,
            "share": (pos / rows) if rows else float("nan")}
