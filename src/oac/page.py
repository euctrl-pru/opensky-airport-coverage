"""Build one aerodrome page as **static markdown**, with figures pre-rendered.

The airport pages carry no executable code, and that is a performance decision
with a measured cause. Quarto's ``execute: daemon`` reuses a kernel across
re-renders of *one* file, not across many, so a project of 424 executable pages
pays a fresh Python kernel each time -- about 10 s a page, over an hour for the
site, and nearly all of it startup rather than work. Emitting markdown and SVG
here, where the data is already loaded, turns the site render into pandoc over
static files.

The four top-level pages (``index``, ``pipeline``, ``metrics``, ``about``) stay
executable: there are four of them, and they read ``_manifest.json`` at render
time so a stale figure cannot be presented as fact.
"""

import pandas as pd

from oac.labels import explain_block, label

#: Percentiles every distribution is summarised at.
PCTS = (10, 25, 50, 75, 90)

#: Signed-offset histograms are bounded here; values outside are excluded from
#: the plot and counted in the caption.
CLIP_S = 1800

__all__ = ["build_page", "PCTS", "CLIP_S"]


def _s(v, plus=True):
    if v is None or pd.isna(v):
        return "—"
    return f"{v:+,.0f}" if plus else f"{v:,.0f}"


def _f(v):
    return "—" if v is None or pd.isna(v) else f"{v:.3f}"


def _p(v):
    return "—" if v is None or pd.isna(v) else f"{v:.1f}%"


def _i(v):
    return "—" if v is None or pd.isna(v) else f"{int(v):,}"


def _table(rows, cols) -> str:
    """A markdown table. Empty input yields an italic note, never a blank gap."""
    if not rows:
        return "*No data.*\n"
    head = "| " + " | ".join(cols) + " |"
    sep = "|" + "|".join("---" for _ in cols) + "|"
    body = "\n".join(
        "| " + " | ".join(str(r.get(c, "—")) for c in cols) + " |" for r in rows
    )
    return f"{head}\n{sep}\n{body}\n"


def _pct_rows(frames, col, fmt):
    """Percentile rows per period, plus the delta between the two newest."""
    rows = []
    for period, d in frames.items():
        s = d[col].dropna()
        if s.empty:
            continue
        r = {"period": period, "n": f"{len(s):,}"}
        for q in PCTS:
            r[f"p{q}"] = fmt(s.quantile(q / 100))
        rows.append(r)
    if len(rows) >= 2:
        a_p, b_p = rows[0]["period"], rows[1]["period"]
        d = {"period": f"delta {a_p}-{b_p}", "n": ""}
        for q in PCTS:
            a = frames[a_p][col].dropna().quantile(q / 100)
            b = frames[b_p][col].dropna().quantile(q / 100)
            d[f"p{q}"] = fmt(a - b)
        rows.append(d)
    return rows


def _side_section(side, frames, tier, figs) -> str:
    is_dep = side == "dep"
    word = "Departures" if is_dep else "Arrivals"
    off_col = "off_s" if is_dep else "land_s"
    cap_col = f"{side}_continuity"
    reach_col = f"{side}_reach"
    good = ("**negative** -- the track began before wheels-off" if is_dep
            else "**positive** -- the track ran on past touchdown")

    out = [f"## {word}\n"]
    if not frames:
        out.append(f"*No detected {word.lower()} in any period.*\n")
        return "\n".join(out)

    out.append(f"`{off_col}` is good when {good}.\n")

    hist = figs.get(f"{side}_hist")
    if hist:
        over = figs.get(f"{side}_hist_overflow", {})
        total = sum(a + b for a, b in over.values())
        cap = (f"Distribution of {off_col}. Zero is "
               f"{'wheels-off' if is_dep else 'touchdown'}.")
        if total:
            parts = ", ".join(f"{p}: {a} below / {b} above"
                              for p, (a, b) in over.items() if a or b)
            cap += (f" {total} movement(s) fall outside +/-{CLIP_S} s and are "
                    f"excluded from the plot ({parts}); they are included in "
                    f"every percentile below.")
        out.append(f"![{cap}](figures/{hist})\n")

    kind = "take-off" if is_dep else "landing"
    out.append(f"**When the track starts, relative to {kind} (seconds)**\n")
    out.append(explain_block([f"{off_col}_p50", f"{off_col}_p10", f"{off_col}_p90"],
                             title="How to read this table"))
    out.append(_table(_pct_rows(frames, off_col, _s),
                      ["period", "n"] + [f"p{q}" for q in PCTS]))

    if tier == "A" and figs.get(f"{side}_ecdf"):
        out.append(
            f"![How much of the {'taxi-out' if is_dep else 'taxi-in'} was "
            f"observed, across all movements. The dashed line is every "
            f"aerodrome pooled; a curve to the *right* of it is better, "
            f"because more of this aerodrome's movements were well "
            f"observed.](figures/{figs[f'{side}_ecdf']})\n"
        )
        phase = "taxi-out" if is_dep else "taxi-in"
        out.append(f"**How much of the {phase} was observed (0 = none, "
                   f"1 = throughout)**\n")
        out.append(explain_block([f"{side}_continuity_p50", f"{side}_reach_p50",
                                  f"{side}_max_gap_median_s"],
                                 title="Observed vs merely spanned"))
        out.append(_table(_pct_rows(frames, cap_col, _f),
                          ["period", "n"] + [f"p{q}" for q in PCTS]))
        out.append(f"**How much of the {phase} the track *spans* "
                   f"(the older, weaker measure)**\n")
        out.append(_table(_pct_rows(frames, reach_col, _f),
                          ["period", "n"] + [f"p{q}" for q in PCTS]))

    if figs.get(f"{side}_hour"):
        out.append(
            f"![Median {off_col} by hour of day. A receiver outage or a "
            f"night-movement effect lives here, and a single daily median "
            f"hides both.](figures/{figs[f'{side}_hour']})\n"
        )
    return "\n".join(out)


def _context_section(stats, tier, ranking, latest) -> str:
    out = ["## Against the fleet\n"]
    if latest not in stats or ranking is None or len(ranking) == 0:
        out.append("*Not present in the latest period's ranking.*\n")
        return "\n".join(out)
    row = stats[latest]
    cols = ([("coverage_index", _f), ("detection_pct_dep", _p),
             ("detection_pct_arr", _p), ("dep_continuity_p50", _f),
             ("arr_continuity_p50", _f), ("dep_reach_p50", _f),
             ("dep_no_ground_pct", _p),
             ("off_s_p50", _s), ("land_s_p50", _s)]
            if tier == "A" else
            [("detection_pct_dep", _p), ("detection_pct_arr", _p),
             ("off_s_p50", _s), ("land_s_p50", _s)])
    rows = []
    for col, fmt in cols:
        if col not in ranking.columns or col not in row.index:
            continue
        v = row[col]
        fleet = ranking[col].dropna()
        if pd.isna(v) or fleet.empty:
            continue
        rows.append({
            "column": label(col),
            "this aerodrome": fmt(v),
            "fleet median": fmt(fleet.median()),
            "percentile in tier": f"{100.0 * (fleet < v).sum() / len(fleet):.0f}",
        })
    out.append(explain_block([c for c, _ in cols],
                             title="What each of these means"))
    out.append(_table(rows, ["column", "this aerodrome", "fleet median",
                             "percentile in tier"]))
    out.append("*Percentile is this aerodrome's position within its own tier: "
               "90 means better than 90% of comparable aerodromes. For "
               "\"Track start vs take-off\" a **low** percentile is better, "
               "because the track starts earlier.*\n")
    return "\n".join(out)


def _quality_section(stats) -> str:
    cols = ["period", "clean (dep)", "fragmented (dep)", "merged (dep)",
            "clean (arr)", "fragmented (arr)", "merged (arr)"]
    rows = [{
        "period": p,
        "clean (dep)": _p(r.get("clean_pct_dep")),
        "fragmented (dep)": _p(r.get("fragmented_pct_dep")),
        "merged (dep)": _p(r.get("merged_pct_dep")),
        "clean (arr)": _p(r.get("clean_pct_arr")),
        "fragmented (arr)": _p(r.get("fragmented_pct_arr")),
        "merged (arr)": _p(r.get("merged_pct_arr")),
    } for p, r in stats.items()]
    return (
        "## Segmentation quality\n\n" + _table(rows, cols)
        + "\nPresent so a poor coverage number can be attributed to reception "
          "or to the segmentation. A merged flight is unrecoverable "
          "downstream; a fragmented one is at least present in pieces.\n"
    )


def _counts_section(stats) -> str:
    cols = ["period", "n_gt_dep", "n_detected_dep", "n_gt_arr",
            "n_detected_arr", "n_capture_excluded_dep", "taxi_out_median_s",
            "taxi_in_median_s"]
    rows = [{
        "period": p,
        "n_gt_dep": _i(r.get("n_gt_dep")),
        "n_detected_dep": _i(r.get("n_detected_dep")),
        "n_gt_arr": _i(r.get("n_gt_arr")),
        "n_detected_arr": _i(r.get("n_detected_arr")),
        "n_capture_excluded_dep": _i(r.get("n_capture_excluded_dep")),
        "taxi_out_median_s": _s(r.get("taxi_out_median_s"), plus=False),
        "taxi_in_median_s": _s(r.get("taxi_in_median_s"), plus=False),
    } for p, r in stats.items()]
    return "## Counts\n\n" + _table(rows, cols)


def _map_section(figs) -> str:
    """Where reception exists on the aerodrome surface, per period."""
    maps = figs.get("maps") or {}
    if not maps:
        return ""
    out = ["## Where the coverage is\n",
           "Each position report is placed on a hexagonal grid over the "
           "aerodrome. The left panel is aircraft **on the ground** -- apron, "
           "taxiways and runways -- so an empty stretch there is surface the "
           "receivers do not reach. The right panel is aircraft **airborne "
           "below 1,500 ft**, which shows where reception begins on approach "
           "and departure.\n",
           "Colour is the number of reports, on a log scale: one apron cell "
           "can hold thousands while a runway threshold holds tens, and a "
           "linear scale would render everything but the stand as empty. "
           "**The two panels are at different zooms** -- the approach covers "
           "roughly ten times the area -- so each carries its own scale "
           "bar.\n"]
    for period in sorted(maps, reverse=True):
        out.append(f"![Observed coverage in {period}.](figures/{maps[period]})\n")
    return "\n".join(out)


def build_page(tier, stats, frames_by_side, ranking, latest, figs) -> str:
    """The markdown body for one aerodrome. No YAML front matter.

    ``stats`` maps period -> that period's row from
    ``airport_stats_<period>.csv``, newest first. ``frames_by_side`` maps
    "dep"/"arr" -> {period -> frame}. ``figs`` maps a figure key to its
    filename, plus ``<side>_hist_overflow``.
    """
    out = []
    if tier == "A":
        out.append("Tier **A**: all four milestones measured from APDF, so "
                   "ground capture is computable.\n")
    else:
        out.append("Tier **B**: take-off inferred as `AOBT_3 + TAXI_TIME_3`, "
                   "landing from `ARVT_3`. There is no in-block time outside "
                   "APDF, so **no capture fraction and no coverage index exist "
                   "here**.\n")

    head = [{
        "period": p,
        "departures": _i(r.get("n_gt_dep")),
        "arrivals": _i(r.get("n_gt_arr")),
        "detection (dep)": _p(r.get("detection_pct_dep")),
        "detection (arr)": _p(r.get("detection_pct_arr")),
        "coverage index": _f(r.get("coverage_index")),
    } for p, r in stats.items()]
    out.append(explain_block(["n_gt_dep", "detection_pct_dep",
                              "coverage_index"],
                             title="What the headline numbers mean"))
    out.append(_table(head, ["period", "departures", "arrivals",
                             "detection (dep)", "detection (arr)",
                             "coverage index"]))

    out.append(_side_section("dep", frames_by_side.get("dep", {}), tier, figs))
    out.append(_side_section("arr", frames_by_side.get("arr", {}), tier, figs))
    out.append(_map_section(figs))
    out.append(_context_section(stats, tier, ranking, latest))
    out.append(_quality_section(stats))
    out.append(_counts_section(stats))
    out.append("\n[<- back to rankings](../index.qmd)\n")
    return "\n".join(out)
