"""The two ranking tables, built once and used twice.

The rankings page shows these tables and offers them as downloads. Building
each one twice -- once for the page, once for the file -- is how a download
comes to disagree with the table above it: a column added to the display and
forgotten in the export, or a rounding applied on one path only. So the
composition lives here, and both consumers call the same function.

**These return data, not presentation.** The frames carry raw column names and
real numeric types, with missing values left as NaN. The page then renames the
headers, turns `icao` into a link and substitutes an em dash for the blanks;
the export renames the headers and writes the numbers as they are. That split
is deliberate: an em dash is the right thing to show a reader and the wrong
thing to put in a spreadsheet cell, where it makes the whole column text.
"""

from pathlib import Path

import pandas as pd

from oac.labels import label, rating
from oac.page import SEC_PER_MIN

__all__ = ["MEASURED_COLS", "ALL_COLS", "with_movements",
           "measured_table", "all_aerodromes_table",
           "write_downloads", "download_stem"]

#: The measured ranking, in display order. `detection_pct` sits after the index
#: and its rating because it is demoted, not removed -- it is near 100% almost
#: everywhere, but its fleet minimum is 76% and it is the only measure the
#: estimated aerodromes can be ranked on.
MEASURED_COLS = ["rank", "icao", "name", "n_movements",
                 "coverage_index", "rating", "detection_pct", "tracking_err_pct"]

#: The all-aerodromes ranking, in display order.
ALL_COLS = ["rank", "icao", "name", "n_movements", "detection_pct", "measured",
            "off_s_p50", "land_s_p50", "dep_signal_p50"]


def with_movements(t: pd.DataFrame) -> pd.DataFrame:
    """Add `n_movements`: take-offs **plus** landings.

    `n_gt` is `max(n_gt_dep, n_gt_arr)`, and that is right for what it does --
    gate the 20-movement ranking floor on the side being ranked. It is wrong
    as a traffic figure, which is how a column headed "Movements" reads: it
    showed Istanbul 2,132 when the aerodrome saw 4,262 over the sample, and a
    reader checking that against the real ~1,400 a day concluded flights were
    missing. They were not; the landings were in a different column.

    A missing side counts as zero rather than voiding the total. 27 aerodromes
    have no recorded arrivals and 34 no departures, and for those the one-sided
    count is the honest number -- the tooltip says so.
    """
    t = t.copy()

    def side(name):
        # Absent, not merely empty: `DataFrame.get` returns None for a missing
        # column, and arithmetic on that fails far from here.
        if name not in t.columns:
            return pd.Series(0.0, index=t.index)
        return pd.to_numeric(t[name], errors="coerce").fillna(0)

    t["n_movements"] = (side("n_gt_dep") + side("n_gt_arr")).astype("Int64")
    return t


def measured_table(a: pd.DataFrame) -> pd.DataFrame:
    """The aerodromes whose milestones the airport operator recorded.

    `signal_p50` is deliberately absent: it correlates with `coverage_index` at
    r = 0.998 and lands in the same rating band for 86 of the 89 aerodromes, so
    showing both asked the reader to compare two columns that cannot disagree.
    The dep/arr split that *is* informative lives on each aerodrome's own page.
    """
    t = with_movements(a)
    t["rating"] = [rating(v) for v in t["coverage_index"]]
    # Fragmented and merged combined into one column. Both are tracking errors,
    # but only fragmented is a measured coverage loss; merged is a completeness
    # loss for the flight that does not survive. Which of the two it is matters
    # when diagnosing an aerodrome, and that breakdown is on its own page.
    t["tracking_err_pct"] = (t["fragmented_pct_dep"].fillna(0)
                             + t["merged_pct_dep"].fillna(0))
    t = t[[c for c in MEASURED_COLS if c in t.columns]].copy()
    t["detection_pct"] = t["detection_pct"].round(1)
    t["coverage_index"] = t["coverage_index"].round(3)
    t["tracking_err_pct"] = t["tracking_err_pct"].round(1)
    return t


def all_aerodromes_table(b: pd.DataFrame) -> pd.DataFrame:
    """Every ranked aerodrome, measured and estimated together.

    `dep_signal_p50` is carried for **every** aerodrome, Tier A included. It is
    the same count either way -- reports received over reports expected at 5 s
    -- but the taxi window it is counted over is not: measured off-block to
    measured take-off for Tier A, Network Manager's off-block plus predicted
    taxi for Tier B. Those windows are not equally trustworthy, so the row's
    tier has to travel with the number rather than be inferred from it, and
    `measured` is in `ALL_COLS` for that reason. The page marks Tier A rows
    with an asterisk; the export carries `measured` as its own column, which is
    what a spreadsheet can actually filter on.

    This column used to be blank for Tier A on the grounds that two windows in
    one column are not comparable. They still are not -- but a blank cell says
    nothing at all, and a reader looking at Brussels wants a number and a
    caveat, not an em dash they have to go and decode.
    """
    t = with_movements(b)
    t["dep_signal_p50"] = t["dep_signal_p50"].round(3)
    t = t[[c for c in ALL_COLS if c in t.columns]].copy()
    t["detection_pct"] = t["detection_pct"].round(1)
    # Minutes, because that is what the column is labelled and what every
    # other duration on the site now shows. The stored column keeps its
    # seconds and its `_s` name in `data/airport_stats_*.csv`; this converts
    # on the way to the page, and the download built from this same frame
    # shows the reader the units they just read on screen.
    for c in ("off_s_p50", "land_s_p50"):
        if c in t:
            # Coerced first: a column that is entirely missing arrives as
            # object dtype, and dividing that raises rather than yielding NaN.
            # An aerodrome with no measurable offset is a real case.
            t[c] = (pd.to_numeric(t[c], errors="coerce") / SEC_PER_MIN).round(1)
    return t


def download_stem(which: str, period: str) -> str:
    """File stem for a download, without extension.

    The period is in the name because the page shows one period at a time and a
    file called `coverage-measured.csv` in a downloads folder tells its owner
    nothing three months later.
    """
    return f"opensky-airport-coverage-{which}-{period}"


def write_downloads(a: pd.DataFrame, b: pd.DataFrame, period: str,
                    out_dir) -> list:
    """Write both rankings as CSV and XLSX. Returns the paths written.

    Headers are the display names the page shows, not the internal column
    names: someone opening the spreadsheet is the same person who read the
    table, and `n_gt` means nothing to them.

    Both formats, because neither alone serves this audience. CSV is universal
    and diff-able; XLSX survives a European Excel install, where a
    comma-separated file opens as a single column because the list separator is
    a semicolon.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for which, frame in (("measured", measured_table(a)),
                         ("all-aerodromes", all_aerodromes_table(b))):
        named = frame.rename(columns={c: label(c) for c in frame.columns})
        stem = download_stem(which, period)
        csv_path = out_dir / f"{stem}.csv"
        named.to_csv(csv_path, index=False)
        written.append(csv_path)
        xlsx_path = out_dir / f"{stem}.xlsx"
        # `openpyxl` is a declared dependency for exactly this line. Imported at
        # module scope by pandas' engine lookup, so a missing wheel fails the
        # build rather than one download.
        named.to_excel(xlsx_path, index=False, sheet_name=which[:31])
        written.append(xlsx_path)
    return written
