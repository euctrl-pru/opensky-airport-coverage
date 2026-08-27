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

__all__ = ["MIN_N", "PCTS", "FULL_CAPTURE", "capture", "by_airport", "airport_table"]


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
    # off_s = trk_start - t_off, so the seconds of taxi seen is -off_s.
    dep = (-out["off_s"]) / out["taxi_out_s"]
    arr = out["land_s"] / out["taxi_in_s"]
    out["dep_capture"] = np.where(valid_out & det, dep.clip(0, 1), np.nan)
    out["arr_capture"] = np.where(valid_in & det, arr.clip(0, 1), np.nan)
    return out


def _pcts(s: pd.Series, stem: str) -> dict:
    """`stem`_p10..p90 over the non-null values of `s`, NaN when empty."""
    s = s.dropna()
    if s.empty:
        return {f"{stem}_p{q}": np.nan for q in PCTS}
    qs = s.quantile([q / 100 for q in PCTS])
    return {f"{stem}_p{q}": float(qs.loc[q / 100]) for q in PCTS}


def _side_stats(g: pd.DataFrame, side: str) -> pd.Series:
    """Every statistic for one aerodrome, one side."""
    is_dep = side == "dep"
    off_col = "off_s" if is_dep else "land_s"
    cap_col = f"{side}_capture"
    taxi_col = "taxi_out_s" if is_dep else "taxi_in_s"

    det = g[g["detected"].fillna(False).astype(bool)]
    n_gt = len(g)
    n_det = len(det)

    row = {
        # n_gt counts every ground-truth movement; the percentiles below are
        # over detected flights only. That asymmetry is the point of the
        # detection column and must not be smoothed away: an undetected flight
        # has no offset, and inventing one would be the only way to include it.
        "n_gt": n_gt,
        "n_detected": n_det,
        "detection_pct": 100.0 * n_det / n_gt if n_gt else np.nan,
        # Bad reference data on THIS side only. A Tier B flight has no AIBT and
        # is not bad data, so it is not counted here -- it simply has no
        # arrival capture.
        # Bad reference data only: a measured endpoint whose ground phase is
        # non-positive. An *unmeasured* endpoint is not bad data -- it simply
        # has no capture -- and counting it here would report Tier B
        # aerodromes as riddled with reference errors.
        "n_capture_excluded": int(
            (g[f"{side}_measured"].fillna(False).astype(bool)
             & ~g[f"capture_valid_{side}"] & g[taxi_col].notna()).sum()
        ),
        # The share of this side's own movements with measured milestones.
        # This -- not the flight-level t_source -- is what decides the tier.
        "measured_pct": 100.0 * g[f"{side}_measured"].fillna(False).astype(bool).mean()
        if n_gt else np.nan,
        f"taxi_{'out' if is_dep else 'in'}_median_s": float(g[taxi_col].median())
        if g[taxi_col].notna().any() else np.nan,
    }
    row.update(_pcts(det[off_col], off_col))
    row.update(_pcts(det[cap_col], cap_col))
    # Absolute percentiles, kept only so the numbers stay comparable with the
    # V1 study's published table. They are NOT a coverage reading: they merge
    # a track that started early with one that started late.
    abs_stem = "off_abs" if is_dep else "land_abs"
    a = det[off_col].abs().dropna()
    row[f"{abs_stem}_p50"] = float(a.quantile(0.5)) if not a.empty else np.nan
    row[f"{abs_stem}_p90"] = float(a.quantile(0.9)) if not a.empty else np.nan

    if is_dep and n_det:
        # trk_start >= ATOT is off_s >= 0: never heard on the ground at all.
        row["dep_no_ground_pct"] = 100.0 * (det["off_s"] >= 0).sum() / n_det
        cap = det["dep_capture"].dropna()
        row["dep_full_capture_pct"] = (
            100.0 * (cap >= FULL_CAPTURE).sum() / len(cap) if len(cap) else np.nan
        )
    elif not is_dep and n_det:
        row["arr_no_ground_pct"] = 100.0 * (det["land_s"] <= 0).sum() / n_det
        cap = det["arr_capture"].dropna()
        row["arr_full_capture_pct"] = (
            100.0 * (cap >= FULL_CAPTURE).sum() / len(cap) if len(cap) else np.nan
        )

    for cls in ("clean", "fragmented", "merged"):
        row[f"{cls}_pct"] = 100.0 * (g["match_class"] == cls).sum() / n_gt if n_gt \
            else np.nan
    return pd.Series(row)


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
    if "dep_capture" not in df.columns:
        raise ValueError("call capture() before by_airport()")
    out = (
        df.groupby(key, dropna=True)
        .apply(_side_stats, side=side, include_groups=False)
        .reset_index()
        .rename(columns={key: "icao"})
    )
    return out


def airport_table(df: pd.DataFrame) -> pd.DataFrame:
    """Departures and arrivals merged, one row per aerodrome.

    An **outer** merge: an aerodrome with departures but no arrivals in the
    sample keeps its row rather than vanishing. Side-specific columns are
    suffixed `_dep` / `_arr` where they collide.
    """
    c = df if "dep_capture" in df.columns else capture(df)
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
    return tbl
