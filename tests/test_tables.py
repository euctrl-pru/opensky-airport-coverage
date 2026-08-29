"""The ranking tables, and the downloads that must not drift from them.

The page and the download are built by one function each precisely so they
cannot disagree. These tests assert that they don't -- on columns, on row
count, and on the one place the two paths are *meant* to differ.
"""

from pathlib import Path

import pandas as pd
import pytest

from oac.labels import label
from oac.tables import (ALL_COLS, MEASURED_COLS, all_aerodromes_table,
                        download_stem, measured_table, write_downloads)

DATA = Path(__file__).resolve().parent.parent / "data"


def _latest():
    files = sorted(DATA.glob("ranking_tier_a_*.csv"))
    if not files:
        pytest.skip("no rankings generated yet")
    return files[-1].stem.replace("ranking_tier_a_", "")


@pytest.fixture(scope="module")
def rankings():
    period = _latest()
    a = pd.read_csv(DATA / f"ranking_tier_a_{period}.csv")
    b = pd.read_csv(DATA / f"ranking_tier_b_{period}.csv")
    return period, a, b


def test_measured_table_carries_the_index_and_keeps_detection(rankings):
    """Remark 4 removed `signal_p50`; remark 7 demoted detection but kept it.

    Both halves asserted here rather than by grepping the page, because the
    composition now lives in one function and a behavioural check cannot be
    satisfied by a comment that happens to mention the column name.
    """
    _, a, _ = rankings
    t = measured_table(a)
    assert "coverage_index" in t.columns, "the table must still rank on the index"
    assert "detection_pct" in t.columns, "detection was removed, not demoted"
    assert "signal_p50" not in t.columns, (
        "signal_p50 is back; it duplicates coverage_index at r = 0.998"
    )
    # Demoted means it comes after the index and its rating.
    order = list(t.columns)
    assert order.index("detection_pct") > order.index("coverage_index")


def test_all_aerodromes_table_leaves_the_estimated_column_numeric(rankings):
    """The em dash is a display concern and must not reach the data.

    An em dash in a spreadsheet turns the whole column to text, so the export
    needs a real NaN. The page substitutes the dash itself.
    """
    _, _, b = rankings
    t = all_aerodromes_table(b)
    est = t["dep_signal_est"]
    assert est.isna().any(), "the blanks must survive as NaN, not as a string"
    assert "—" not in set(est.dropna().astype(str)), "em dash leaked into the data"
    assert pd.api.types.is_numeric_dtype(est), f"expected numeric, got {est.dtype}"


def test_the_estimated_figure_is_withheld_where_a_measured_one_exists(rankings):
    """Blank for measured aerodromes is the point, not missing data.

    Their real figure is in the measured table; an estimated one computed over
    Network Manager's predicted window would be a different, worse quantity in
    the same column.
    """
    _, _, b = rankings
    t = all_aerodromes_table(b)
    measured = b["measured"] == "yes"
    assert t.loc[measured.values, "dep_signal_est"].isna().all()
    assert t.loc[~measured.values, "dep_signal_est"].notna().any()


def test_downloads_match_the_tables_exactly(tmp_path, rankings):
    """The whole reason the composition was extracted.

    A column added to the page and forgotten in the export is the failure this
    guards; it is invisible until someone opens the file.
    """
    period, a, b = rankings
    written = write_downloads(a, b, period, tmp_path)
    assert len(written) == 4, [p.name for p in written]
    assert all(p.is_file() and p.stat().st_size > 0 for p in written)

    for which, frame in (("measured", measured_table(a)),
                         ("all-aerodromes", all_aerodromes_table(b))):
        stem = download_stem(which, period)
        csv = pd.read_csv(tmp_path / f"{stem}.csv")
        assert len(csv) == len(frame), f"{which}: row count differs"
        assert list(csv.columns) == [label(c) for c in frame.columns], (
            f"{which}: the download's columns are not the table's columns"
        )


def test_the_download_headers_are_the_names_the_reader_saw(tmp_path, rankings):
    """`n_gt` means nothing to someone who read a column called Movements."""
    period, a, b = rankings
    write_downloads(a, b, period, tmp_path)
    csv = pd.read_csv(tmp_path / f"{download_stem('measured', period)}.csv")
    assert "Movements" in csv.columns
    assert "n_gt" not in csv.columns


def test_the_xlsx_opens_and_holds_the_same_rows(tmp_path, rankings):
    """Written through openpyxl, which is a declared dependency for this."""
    period, a, b = rankings
    write_downloads(a, b, period, tmp_path)
    stem = download_stem("all-aerodromes", period)
    xlsx = pd.read_excel(tmp_path / f"{stem}.xlsx")
    csv = pd.read_csv(tmp_path / f"{stem}.csv")
    assert len(xlsx) == len(csv)
    assert list(xlsx.columns) == list(csv.columns)


def test_column_order_constants_match_what_the_builders_emit(rankings):
    """The page prints `explain_block(MEASURED_COLS)` above the table.

    If the constant and the frame disagree, the reader gets definitions for
    columns that are not there, or none for columns that are.
    """
    period, a, b = rankings
    assert list(measured_table(a).columns) == [
        c for c in MEASURED_COLS if c in measured_table(a).columns]
    assert list(all_aerodromes_table(b).columns) == [
        c for c in ALL_COLS if c in all_aerodromes_table(b).columns]
