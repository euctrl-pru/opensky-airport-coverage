"""Per-aerodrome statistics from the committed per-flight table.

Pure pandas, deliberately. The cluster produces one small table; everything
after it -- percentiles, capture, tiers, the index -- is a laptop edit rather
than a two-hour re-run. This module must import neither `pyspark` nor `opdi`,
because the site renders in GitHub Actions where neither exists;
`tests/test_imports.py` asserts it in a clean subprocess.

Sign convention, stated once: `off_s = trk_start - ATOT` (**negative is good**,
the track began before wheels-off) and `land_s = trk_end - ALDT` (**positive is
good**, it ran on past touchdown).
"""

import numpy as np
import pandas as pd

#: An aerodrome qualifies for a ranking table when `n_gt >= MIN_N` on the side
#: being ranked. Stated once here; never re-chosen per table.
MIN_N = 20

#: The percentiles every distribution is summarised at.
PCTS = (10, 25, 50, 75, 90)

#: A capture at or above this counts as having seen the whole ground phase.
FULL_CAPTURE = 0.95

#: Seconds between position reports the feed is expected to deliver. The
#: ingestion decimates to 5 s, so a fully observed ground phase should yield
#: one report every 5 s -- six per 30 s bin.
#:
#: Verified rather than assumed: on the 2026 sample, the 6,360 departures whose
#: every 30 s bin was occupied have an observed/expected ratio with median
#: **1.00** and p10 0.97. Full bin occupancy really does mean a full message
#: rate, so the denominator below is the right one.
EXPECTED_INTERVAL_S = 5.0

__all__ = ["MIN_N", "PCTS", "FULL_CAPTURE", "capture", "by_airport",
           "airport_table"]


def capture(df: pd.DataFrame) -> pd.DataFrame:
    """Add the normalised ground-phase capture fractions.

        dep_capture = clip((ATOT - trk_start) / (ATOT - AOBT), 0, 1)
        arr_capture = clip((trk_end  - ALDT) / (AIBT  - ALDT), 0, 1)

    Raw seconds are not comparable between aerodromes: -180 s is complete
    coverage at a field with a three-minute taxi and about 15% of it at a hub
    with a twenty-minute one, and the two are indistinguishable once the
    denominator is dropped.

    **A non-positive ground phase is excluded, not clipped.** `AOBT >= ATOT` or
    `AIBT <= ALDT` is bad reference data; clipping would score the flight 0 or 1
    and silently move the aerodrome's median. `capture_valid` marks them and
    `by_airport` counts them into `n_capture_excluded`.

    Tier B has no `aibt` at all, so `arr_capture` is NaN there by construction
    rather than by exclusion -- `taxi_in_s` is NaN, which is not `> 0`.
    """
    out = df.copy()
    out["taxi_out_s"] = (out["t_off"] - out["aobt"]).dt.total_seconds()
    out["taxi_in_s"] = (out["aibt"] - out["t_land"]).dt.total_seconds()

    # **Capture is computed only from measured milestones.** Outside APDF the
    # denominator would be `TAXI_TIME_3` -- NM's *predicted* taxi -- so the
    # fraction would measure the prediction as much as the reception, and
    # mixing predicted and measured denominators inside one column makes the
    # aerodrome ranking incomparable with itself.
    #
    # Gated on the per-endpoint flags, never on `t_source`: `t_source` is
    # "apdf" only when both ends are measured, and an aerodrome's arrivals can
    # be fully measured while most of its traffic arrives from aerodromes APDF
    # does not cover.
    dep_ok = out.get("dep_measured")
    arr_ok = out.get("arr_measured")
    if dep_ok is None or arr_ok is None:
        raise ValueError(
            "capture() needs dep_measured/arr_measured. Re-run "
            "scripts/run_offsets.py -- this table predates the per-endpoint "
            "provenance flags, and tiering it on t_source mis-classifies "
            "aerodromes whose own side is measured."
        )
    dep_ok = dep_ok.fillna(False).astype(bool)
    arr_ok = arr_ok.fillna(False).astype(bool)

    # The departure window exists for every flight -- NM supplies an off-block
    # time and a taxi duration even where APDF never saw the movement -- so
    # departure coverage is computed everywhere. `dep_measured` still travels
    # with every row so the two populations are never mixed in a table.
    #
    # The arrival window does not: it ends at the in-block time, which exists
    # only in APDF.
    valid_out = out["taxi_out_s"] > 0
    valid_in = (out["taxi_in_s"] > 0) & arr_ok
    # "Valid" means the flight can contribute to *either* capture. A Tier B
    # flight has no taxi_in_s and is not therefore bad data, so it must not be
    # counted as excluded; n_capture_excluded is computed against the side.
    out["capture_valid_dep"] = valid_out
    out["capture_valid_arr"] = valid_in
    out["capture_valid"] = valid_out & valid_in

    det = out["detected"].fillna(False).astype(bool)

    # REACH -- how far into the ground phase the outermost sample lies.
    # off_s = trk_start - t_off, so the seconds of taxi spanned is -off_s.
    #
    # **Not clipped.** An earlier version clipped to [0, 1], which flattened
    # 63% of all values onto the two endpoints: on the 2026 sample 52.2% of
    # measured departures were below 0 and 11.2% above 1, so the pile-up at 0
    # and 1 was mostly an artefact of the clip rather than a property of the
    # data.
    #
    # Both tails are meaningful and neither is an error:
    #
    # * **> 1** -- the track began *before* off-block. Real: an aircraft may
    #   broadcast at the stand before it pushes, and AOBT carries its own
    #   imprecision, so demanding reach <= 1 asserts a precision the reference
    #   data does not have.
    # * **< 0** -- the track began after wheels-off, i.e. part of the departure
    #   was missed outright. Clipping that to 0 made "just barely missed it"
    #   and "picked up ten minutes into the climb" the same number.
    #
    # Percentiles are what the site reports, so the long tail (max 72, a merged
    # track) moves nothing. A mean over this column would be meaningless and
    # none is computed.
    out["dep_reach"] = np.where(valid_out & det,
                                (-out["off_s"]) / out["taxi_out_s"], np.nan)
    out["arr_reach"] = np.where(valid_in & det,
                                out["land_s"] / out["taxi_in_s"], np.nan)

    # SIGNAL -- the share of expected position reports actually received.
    #
    #     signal = observed reports / (ground phase seconds / 5)
    #
    # This is the headline measure. An earlier version used bin occupancy
    # alone, which asks only whether *anything* arrived in each 30 s slice and
    # so scores one report out of an expected six as a full slice.
    #
    # CONTINUITY -- the share of 30 s bins containing any report at all -- is
    # kept beside it, because the two answer different questions and their
    # disagreement is informative: high continuity with low signal is a thin
    # but unbroken stream, while high signal with low continuity is a dense
    # burst around a hole. Neither is visible in the other.
    #
    # Neither is clipped. Signal above 1 means the feed delivered more than the
    # nominal cadence, which happens on 1.9% of departures and is a fact about
    # the feed rather than an error to be squashed.
    #
    # Reach is kept as well, for the same reason it always was: reach high with
    # signal low is the signature of one report at the stand and nothing after.
    for side, valid, taxi in (("dep", valid_out, "taxi_out_s"),
                              ("arr", valid_in, "taxi_in_s")):
        total = out.get(f"{side}_bins_total")
        seen = out.get(f"{side}_bins_seen")
        n_obs = out.get(f"{side}_n_samples")
        if total is None or seen is None or n_obs is None:
            out[f"{side}_continuity"] = np.nan
            out[f"{side}_signal"] = np.nan
            continue
        ok = valid & det & total.notna() & total.gt(0)
        out[f"{side}_continuity"] = np.where(ok, seen / total, np.nan)
        expected = out[taxi] / EXPECTED_INTERVAL_S
        out[f"{side}_signal"] = np.where(
            ok & expected.gt(0), n_obs / expected, np.nan
        )
    return out


def _pcts(s: pd.Series, stem: str) -> dict:
    """`stem`_p10..p90 over the non-null values of `s`, NaN when empty."""
    s = s.dropna()
    if s.empty:
        return {f"{stem}_p{q}": np.nan for q in PCTS}
    qs = s.quantile([q / 100 for q in PCTS])
    return {f"{stem}_p{q}": float(qs.loc[q / 100]) for q in PCTS}


def _side_keys(side: str) -> list:
    """Every key `_side_stats` emits, in order.

    **Fixed, and not conditional on the data.** An earlier version omitted the
    no-ground and full-capture keys for an aerodrome with no detected flights,
    which made `groupby.apply` receive ragged Series: pandas then falls back to
    a positional frame with integer column names, and the failure surfaces much
    later as a `KeyError` on a column that exists for most aerodromes. Every
    aerodrome now returns the same keys, absent ones as NaN.
    """
    is_dep = side == "dep"
    off_col = "off_s" if is_dep else "land_s"
    abs_stem = "off_abs" if is_dep else "land_abs"
    keys = ["n_gt", "n_detected", "detection_pct", "n_capture_excluded",
            "measured_pct", f"taxi_{'out' if is_dep else 'in'}_median_s",
            f"{side}_max_gap_median_s"]
    keys += [f"{off_col}_p{q}" for q in PCTS]
    keys += [f"{side}_reach_p{q}" for q in PCTS]
    keys += [f"{side}_continuity_p{q}" for q in PCTS]
    keys += [f"{side}_signal_p{q}" for q in PCTS]
    keys += [f"{abs_stem}_p50", f"{abs_stem}_p90"]
    keys += [f"{side}_no_ground_pct", f"{side}_full_capture_pct"]
    keys += ["clean_pct", "fragmented_pct", "merged_pct"]
    return keys


def _side_stats(g: pd.DataFrame, side: str) -> pd.Series:
    """Every statistic for one aerodrome, one side. Fixed key set."""
    is_dep = side == "dep"
    off_col = "off_s" if is_dep else "land_s"
    taxi_col = "taxi_out_s" if is_dep else "taxi_in_s"
    abs_stem = "off_abs" if is_dep else "land_abs"

    det = g[g["detected"].fillna(False).astype(bool)]
    n_gt = len(g)
    n_det = len(det)
    measured = g[f"{side}_measured"].fillna(False).astype(bool)

    row = {k: np.nan for k in _side_keys(side)}
    row["n_gt"] = n_gt
    row["n_detected"] = n_det
    row["detection_pct"] = 100.0 * n_det / n_gt if n_gt else np.nan
    # Bad reference data only: a *measured* endpoint whose ground phase is
    # non-positive. An unmeasured endpoint is not bad data -- it simply has no
    # capture -- and counting it here would report every Tier B aerodrome as
    # riddled with reference errors.
    row["n_capture_excluded"] = int(
        (measured & ~g[f"capture_valid_{side}"] & g[taxi_col].notna()).sum()
    )
    # The share of this side's own movements with measured milestones. This --
    # not the flight-level t_source -- is what decides the tier.
    row["measured_pct"] = 100.0 * measured.mean() if n_gt else np.nan
    tk = f"taxi_{'out' if is_dep else 'in'}_median_s"
    row[tk] = float(g[taxi_col].median()) if g[taxi_col].notna().any() else np.nan

    # n_gt counts every ground-truth movement; the percentiles are over
    # detected flights only. That asymmetry is the point of the detection
    # column: an undetected flight has no offset, and the only way to include
    # it in a percentile would be to invent one.
    row.update(_pcts(det[off_col], off_col))
    row.update(_pcts(det[f"{side}_reach"], f"{side}_reach"))
    row.update(_pcts(det[f"{side}_continuity"], f"{side}_continuity"))
    row.update(_pcts(det[f"{side}_signal"], f"{side}_signal"))
    gap = det.get(f"{side}_max_gap_s")
    if gap is not None and gap.notna().any():
        row[f"{side}_max_gap_median_s"] = float(gap.median())

    # Absolute percentiles, kept only for comparability with the V1 study's
    # published table. NOT a coverage reading: they merge a track that started
    # early with one that started late.
    a = det[off_col].abs().dropna()
    if not a.empty:
        row[f"{abs_stem}_p50"] = float(a.quantile(0.5))
        row[f"{abs_stem}_p90"] = float(a.quantile(0.9))

    if n_det:
        # off_s >= 0 is trk_start >= ATOT: never heard on the ground at all.
        # land_s <= 0 is the arrival mirror: lost at or before touchdown.
        lost = (det[off_col] >= 0) if is_dep else (det[off_col] <= 0)
        row[f"{side}_no_ground_pct"] = 100.0 * lost.sum() / n_det
        # "Fully captured" now means continuously observed, not merely
        # spanned -- the same word measuring a different and stricter thing.
        cap = det[f"{side}_signal"].dropna()
        if len(cap):
            row[f"{side}_full_capture_pct"] = (
                100.0 * (cap >= FULL_CAPTURE).sum() / len(cap)
            )

    if n_gt:
        for cls in ("clean", "fragmented", "merged"):
            row[f"{cls}_pct"] = 100.0 * (g["match_class"] == cls).sum() / n_gt

    return pd.Series(row, index=_side_keys(side))


def by_airport(df: pd.DataFrame, side: str) -> pd.DataFrame:
    """Per-aerodrome statistics for one side.

    `side` is `"dep"` (grouped on `gt_adep`) or `"arr"` (on `gt_ades`). Both
    sides appear on every aerodrome page: an aerodrome can have good arrival
    coverage and poor departure coverage, and that asymmetry is itself a
    finding -- an arriving aircraft is powered and broadcasting to the stand
    while a departing one may not transmit until it lines up.
    """
    if side not in ("dep", "arr"):
        raise ValueError(f"side must be 'dep' or 'arr', not {side!r}")
    key = "gt_adep" if side == "dep" else "gt_ades"
    if "dep_reach" not in df.columns or "dep_signal" not in df.columns:
        raise ValueError("call capture() before by_airport()")
    out = (
        df.groupby(key, dropna=True)
        .apply(_side_stats, side=side, include_groups=False)
        .reset_index()
        .rename(columns={key: "icao"})
    )
    missing = set(_side_keys(side)) - set(out.columns)
    if missing:
        raise AssertionError(
            f"by_airport({side!r}) lost columns {sorted(missing)} -- "
            "_side_stats returned a ragged Series."
        )
    return out


def airport_table(df: pd.DataFrame) -> pd.DataFrame:
    """Departures and arrivals merged, one row per aerodrome.

    An **outer** merge: an aerodrome with departures but no arrivals in the
    sample keeps its row rather than vanishing. Side-specific columns are
    suffixed `_dep` / `_arr` where they collide.
    """
    c = df if "dep_signal" in df.columns else capture(df)
    dep = by_airport(c, "dep")
    arr = by_airport(c, "arr")
    tbl = dep.merge(arr, on="icao", how="outer", suffixes=("_dep", "_arr"))

    # **The tier is derived from the aerodrome's own measured share, not from
    # the flight-level `t_source`.** An aerodrome is Tier A when at least half
    # the movements on either of its sides carry measured milestones.
    #
    # Using modal `t_source` instead put 26 aerodromes with 20+ movements into
    # the wrong tier on the 2025 sample -- Helsinki, Stuttgart, Keflavik and
    # Charleroi among them, all with 99-100% measured arrivals -- because
    # `t_source` is "apdf" only when *both* ends of a flight are covered, and
    # most of their traffic arrives from aerodromes APDF does not cover. They
    # would have been ranked on detection alone with every capture metric
    # silently blank.
    m = tbl[["measured_pct_dep", "measured_pct_arr"]].max(axis=1)
    tbl["measured_pct"] = m
    tbl["t_source"] = np.where(m >= 50.0, "apdf", "nm_inferred")


    # n_gt for ranking is the side being ranked; a single n_gt would mean
    # different things in the two tables. Keep both and derive the max, which
    # is what MIN_N is applied to when an aerodrome is considered at all.
    tbl["n_gt"] = tbl[["n_gt_dep", "n_gt_arr"]].max(axis=1)
    tbl["detection_pct"] = tbl[["detection_pct_dep", "detection_pct_arr"]].mean(axis=1)

    # The index is computed here, not only in `rank_tiers`, and only once
    # `detection_pct` exists -- it is one of its two terms. It is the headline
    # number on every aerodrome page, and computing it solely at ranking time
    # left it out of `airport_stats_*.csv`, so each page rendered its own
    # headline as an em dash. Imported rather than reimplemented, so the page
    # and the ranking cannot disagree about it.
    from oac.rank import coverage_index

    tbl["coverage_index"] = tbl.apply(coverage_index, axis=1)
    return tbl
