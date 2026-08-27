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

    valid_out = (out["taxi_out_s"] > 0) & dep_ok
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
    dep = (-out["off_s"]) / out["taxi_out_s"]
    arr = out["land_s"] / out["taxi_in_s"]
    out["dep_reach"] = np.where(valid_out & det, dep.clip(0, 1), np.nan)
    out["arr_reach"] = np.where(valid_in & det, arr.clip(0, 1), np.nan)

    # CONTINUITY -- how much of the ground phase was actually observed.
    #
    # Reach is kept beside it, never replaced. Reach high with continuity low
    # is the exact signature of one sample at the stand and nothing after it,
    # which is the defect continuity exists to expose; deleting reach would
    # hide the evidence that it happened.
    for side, valid in (("dep", valid_out), ("arr", valid_in)):
        total = out.get(f"{side}_bins_total")
        seen = out.get(f"{side}_bins_seen")
        if total is None or seen is None:
            out[f"{side}_continuity"] = np.nan
            continue
        out[f"{side}_continuity"] = np.where(
            valid & det & total.notna() & total.gt(0),
            seen / total, np.nan,
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
        cap = det[f"{side}_continuity"].dropna()
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
    if "dep_reach" not in df.columns or "dep_continuity" not in df.columns:
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
    c = df if "dep_continuity" in df.columns else capture(df)
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
