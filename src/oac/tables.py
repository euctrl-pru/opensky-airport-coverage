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

__all__ = ["MEASURED_COLS", "ALL_COLS", "measured_table", "all_aerodromes_table",
           "write_downloads", "download_stem"]

#: The measured ranking, in display order. `detection_pct` sits after the index
#: and its rating because it is demoted, not removed -- it is near 100% almost
#: everywhere, but its fleet minimum is 76% and it is the only measure the
#: estimated aerodromes can be ranked on.
MEASURED_COLS = ["rank", "icao", "name", "n_gt",
                 "coverage_index", "rating", "detection_pct", "tracking_err_pct"]

#: The all-aerodromes ranking, in display order.
ALL_COLS = ["rank", "icao", "name", "n_gt", "detection_pct", "measured",
            "off_s_p50", "land_s_p50", "dep_signal_est"]


def measured_table(a: pd.DataFrame) -> pd.DataFrame:
    """The aerodromes whose milestones the airport operator recorded.

    `signal_p50` is deliberately absent: it correlates with `coverage_index` at
    r = 0.998 and lands in the same rating band for 86 of the 89 aerodromes, so
    showing both asked the reader to compare two columns that cannot disagree.
    The dep/arr split that *is* informative lives on each aerodrome's own page.
    """
    t = a.copy()
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
    t["n_gt"] = t["n_gt"].astype("Int64")
    return t


def all_aerodromes_table(b: pd.DataFrame) -> pd.DataFrame:
    """Every ranked aerodrome, measured and estimated together.

    `dep_signal_est` is carried **only** where there is no measured figure, so
    the column cannot be read as a second opinion on an aerodrome that already
    has the real one -- the two are computed against different windows and are
    not comparable side by side. It is left as NaN elsewhere; the page renders
    those as an em dash, the export leaves the cell empty.
    """
    t = b.copy()
    t["dep_signal_est"] = t["dep_signal_p50"].where(t["measured"] == "no").round(3)
    t = t[[c for c in ALL_COLS if c in t.columns]].copy()
    t["detection_pct"] = t["detection_pct"].round(1)
    for c in ("off_s_p50", "land_s_p50"):
        if c in t:
            t[c] = t[c].round(0).astype("Int64")
    t["n_gt"] = t["n_gt"].astype("Int64")
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
