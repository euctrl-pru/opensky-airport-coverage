"""Render one aerodrome page.

Every generated page under `airports/` is three lines that call `render()`.
The logic lives here so a change to the page layout is one edit rather than
five hundred, and so the generated files stay small enough that a diff over
them is readable.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from IPython.display import Markdown, display

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _charts  # noqa: E402
import _data  # noqa: E402

PCTS = [10, 25, 50, 75, 90]


def _fmt_s(v):
    return "—" if pd.isna(v) else f"{v:+,.0f}"


def _fmt_f(v):
    return "—" if pd.isna(v) else f"{v:.3f}"


def _fmt_p(v):
    return "—" if pd.isna(v) else f"{v:.1f}%"


def _stats_for(icao):
    """`period -> row` from each period's airport_stats, newest first."""
    out = {}
    for p in _data.periods_available():
        try:
            s = _data.load_stats(p)
        except FileNotFoundError:
            continue
        hit = s[s.icao == icao]
        if len(hit):
            out[p] = hit.iloc[0]
    return out


def _tier(row):
    return "A" if row.get("t_source") == "apdf" else "B"


def header(icao, stats):
    if not stats:
        display(Markdown(f"No statistics for **{icao}**."))
        return None
    latest = _data.latest()
    row = stats.get(latest, list(stats.values())[0])
    tier = _tier(row)
    name = row.get("name")
    name = "" if pd.isna(name) else str(name)

    lines = [f"**{icao}**" + (f" — {name}" if name else ""), ""]
    if tier == "A":
        lines.append(
            "Tier **A**: all four milestones measured from APDF, so ground "
            "capture is computable."
        )
    else:
        lines.append(
            "Tier **B**: take-off inferred as `AOBT_3 + TAXI_TIME_3`, landing "
            "from `ARVT_3`. **NM-inferred** — there is no in-block time outside "
            "APDF, so no capture fraction and no coverage index exist here."
        )
    display(Markdown("\n".join(lines)))

    head = []
    for p, r in stats.items():
        head.append({
            "period": p,
            "departures": int(r["n_gt_dep"]) if not pd.isna(r.get("n_gt_dep")) else 0,
            "arrivals": int(r["n_gt_arr"]) if not pd.isna(r.get("n_gt_arr")) else 0,
            "detection (dep)": _fmt_p(r.get("detection_pct_dep")),
            "detection (arr)": _fmt_p(r.get("detection_pct_arr")),
            "coverage_index": _fmt_f(r.get("coverage_index")),
        })
    display(pd.DataFrame(head))
    return tier


def _offsets_for(icao, side):
    """`period -> per-flight frame` for one side of one aerodrome.

    Reads the aerodrome's own precomputed slice, written by
    `scripts/gen_pages.py`. Reading the full per-flight table here instead --
    which an earlier version did, once per period per side -- made the render
    quadratic in aerodrome count.
    """
    sl = _data.load_slice(icao)
    sl = sl[(sl["_side"] == side) & sl["detected"].fillna(False).astype(bool)]
    out = {}
    for p in _data.periods_available():
        sub = sl[sl["period"] == p]
        if len(sub):
            out[p] = sub
    return out


def _percentile_table(frames, col, label, scale=None):
    rows = []
    for p, d in frames.items():
        s = d[col].dropna()
        if s.empty:
            continue
        r = {"period": p, "n": len(s)}
        for q in PCTS:
            v = s.quantile(q / 100)
            r[f"p{q}"] = f"{v:.3f}" if scale == "frac" else f"{v:+,.0f}"
        rows.append(r)
    if not rows:
        display(Markdown(f"*No {label} available.*"))
        return
    t = pd.DataFrame(rows)
    # The delta between the two newest periods, which is the whole reason both
    # are on the page.
    if len(t) >= 2 and scale != "frac":
        d = {"period": f"Δ {t.period.iloc[0]}−{t.period.iloc[1]}", "n": ""}
        for q in PCTS:
            a = float(t[f"p{q}"].iloc[0].replace(",", ""))
            b = float(t[f"p{q}"].iloc[1].replace(",", ""))
            d[f"p{q}"] = f"{a - b:+,.0f}"
        t = pd.concat([t, pd.DataFrame([d])], ignore_index=True)
    display(Markdown(f"**{label}**"))
    display(t)


def _side(icao, side, stats, tier):
    is_dep = side == "dep"
    word = "Departures" if is_dep else "Arrivals"
    off_col = "off_s" if is_dep else "land_s"
    cap_col = "dep_capture" if is_dep else "arr_capture"
    good = ("negative — the track began before wheels-off" if is_dep
            else "positive — the track ran on past touchdown")

    display(Markdown(f"## {word}"))
    frames = _offsets_for(icao, side)
    if not frames:
        display(Markdown(f"*No detected {word.lower()} in any period.*"))
        return

    display(Markdown(f"`{off_col}` is good when **{good}**."))

    fig, overflow = _charts.signed_histogram(
        {p: d[off_col].values for p, d in frames.items()},
        xlabel=f"{off_col} (s)",
        zero_label="wheels-off" if is_dep else "touchdown",
    )
    display(fig)
    total_out = sum(a + b for a, b in overflow.values())
    if total_out:
        parts = ", ".join(f"{p}: {a} below / {b} above"
                          for p, (a, b) in overflow.items() if a or b)
        display(Markdown(
            f"*{total_out} movement(s) fall outside ±1800 s and are excluded "
            f"from the plot — {parts}. They are included in every percentile "
            f"below.*"
        ))

    _percentile_table(frames, off_col, f"{off_col} percentiles (seconds, signed)")

    if tier == "A":
        cap = {p: d[cap_col].dropna().values for p, d in frames.items()}
        cap = {p: v for p, v in cap.items() if len(v)}
        if cap:
            # The fleet reference answers the question a bare number cannot:
            # whether this aerodrome's capture is good *for this fleet*.
            # Precomputed once for the whole site, not recomputed per page.
            ref = _data.load_fleet()[cap_col].dropna().values
            fig = _charts.ecdf(cap, reference=ref,
                               xlabel=f"{cap_col} (fraction of ground phase seen)")
            display(fig)
            _percentile_table(frames, cap_col, f"{cap_col} percentiles",
                              scale="frac")

    # Hour of day: where a receiver outage or a night-movement effect lives,
    # and where a single daily median hides both.
    hourly = {}
    for p, d in frames.items():
        t = d.dropna(subset=[off_col]).copy()
        if t.empty:
            continue
        anchor = "t_off" if is_dep else "t_land"
        t["hour"] = pd.to_datetime(t[anchor]).dt.hour
        g = t.groupby("hour")[off_col].median()
        if len(g) > 1:
            hourly[p] = g
    if hourly:
        fig = _charts.by_hour(hourly, ylabel=f"median {off_col} (s)")
        display(fig)


def _context(icao, stats, tier):
    """This aerodrome against the fleet, for every ranking column."""
    display(Markdown("## Against the fleet"))
    latest = _data.latest()
    if latest not in stats:
        display(Markdown("*Not present in the latest period.*"))
        return
    row = stats[latest]
    try:
        rank = _data.load_ranking("a" if tier == "A" else "b", latest)
    except FileNotFoundError:
        display(Markdown("*No ranking table.*"))
        return

    cols = ([("coverage_index", _fmt_f), ("detection_pct_dep", _fmt_p),
             ("detection_pct_arr", _fmt_p), ("dep_capture_p50", _fmt_f),
             ("arr_capture_p50", _fmt_f), ("dep_no_ground_pct", _fmt_p),
             ("off_s_p50", _fmt_s), ("land_s_p50", _fmt_s)]
            if tier == "A" else
            [("detection_pct_dep", _fmt_p), ("detection_pct_arr", _fmt_p),
             ("off_s_p50", _fmt_s), ("land_s_p50", _fmt_s)])

    rows = []
    for col, fmt in cols:
        if col not in rank.columns or col not in row.index:
            continue
        v = row[col]
        fleet = rank[col].dropna()
        if pd.isna(v) or fleet.empty:
            continue
        pct_rank = 100.0 * (fleet < v).sum() / len(fleet)
        rows.append({
            "column": col,
            "this aerodrome": fmt(v),
            "fleet median": fmt(fleet.median()),
            "percentile in tier": f"{pct_rank:.0f}",
        })
    if rows:
        display(pd.DataFrame(rows))
        display(Markdown(
            "*Percentile is within this aerodrome's own tier. For "
            "`off_s_p50` a **low** percentile is better — the track starts "
            "earlier.*"
        ))


def _quality(icao, stats):
    display(Markdown("## Segmentation quality"))
    rows = []
    for p, r in stats.items():
        rows.append({
            "period": p,
            "clean (dep)": _fmt_p(r.get("clean_pct_dep")),
            "fragmented (dep)": _fmt_p(r.get("fragmented_pct_dep")),
            "merged (dep)": _fmt_p(r.get("merged_pct_dep")),
            "clean (arr)": _fmt_p(r.get("clean_pct_arr")),
            "fragmented (arr)": _fmt_p(r.get("fragmented_pct_arr")),
            "merged (arr)": _fmt_p(r.get("merged_pct_arr")),
        })
    display(pd.DataFrame(rows))
    display(Markdown(
        "Present so a poor coverage number can be attributed to reception or "
        "to the segmentation. A merged flight is unrecoverable downstream; a "
        "fragmented one is at least present in pieces."
    ))


def _counts(icao, stats):
    display(Markdown("## Counts"))
    rows = []
    for p, r in stats.items():
        rows.append({
            "period": p,
            "n_gt_dep": int(r["n_gt_dep"]) if not pd.isna(r.get("n_gt_dep")) else 0,
            "n_detected_dep": int(r["n_detected_dep"])
            if not pd.isna(r.get("n_detected_dep")) else 0,
            "n_gt_arr": int(r["n_gt_arr"]) if not pd.isna(r.get("n_gt_arr")) else 0,
            "n_detected_arr": int(r["n_detected_arr"])
            if not pd.isna(r.get("n_detected_arr")) else 0,
            "n_capture_excluded_dep": int(r["n_capture_excluded_dep"])
            if not pd.isna(r.get("n_capture_excluded_dep")) else 0,
            "taxi_out_median_s": _fmt_s(r.get("taxi_out_median_s")),
            "taxi_in_median_s": _fmt_s(r.get("taxi_in_median_s")),
        })
    display(pd.DataFrame(rows))


def render(icao: str) -> None:
    """The whole page for one aerodrome."""
    stats = _stats_for(icao)
    tier = header(icao, stats)
    if tier is None:
        return
    _side(icao, "dep", stats, tier)
    _side(icao, "arr", stats, tier)
    _context(icao, stats, tier)
    _quality(icao, stats)
    _counts(icao, stats)
