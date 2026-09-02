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

from oac.labels import TIERS_EXPLAINED, rating, tip_header

#: Percentiles every distribution is summarised at.
#: Percentiles shown in the page tables. The aggregation computes and
#: publishes 10/25/50/75/90; the page shows three, because five columns of
#: percentiles per table is more precision than a reader scanning a page can
#: use, and the CSVs keep all of them.
PCTS = (10, 50, 90)

#: Signed-offset histograms are bounded here; values outside are excluded from
#: the plot and counted in the caption.
CLIP_S = 1800

#: Seconds per minute. Every stored duration is in seconds -- that is what the
#: aggregation writes and what the downloads carry -- and every duration a
#: reader sees is in minutes. This is the only place the two meet, so the
#: conversion cannot drift between the tables, the tooltips and the plots.
SEC_PER_MIN = 60.0

#: The histogram bound in the unit the axis is drawn in.
CLIP_MIN = CLIP_S / SEC_PER_MIN

__all__ = ["build_page", "PCTS", "CLIP_S", "CLIP_MIN", "SEC_PER_MIN"]


def _min(v, plus=True):
    """Seconds in, minutes out. One decimal, which is 6 s of resolution.

    Durations are stored in seconds and shown in minutes. A reader thinks in
    minutes -- "the track began four minutes before take-off" is a fact about
    an aerodrome, while "-247" is a number they have to divide before it means
    anything. The stored column keeps its `_s` name and its seconds, so the
    downloads are unchanged and nothing that already consumes them breaks.
    """
    if v is None or pd.isna(v):
        return "—"
    return (f"{v / SEC_PER_MIN:+,.1f}" if plus
            else f"{v / SEC_PER_MIN:,.1f}")


def _f(v):
    return "—" if v is None or pd.isna(v) else f"{v:.3f}"


def _p(v):
    return "—" if v is None or pd.isna(v) else f"{v:.1f}%"


def _i(v):
    return "—" if v is None or pd.isna(v) else f"{int(v):,}"


def _dur(v):
    """An unsigned duration in minutes.

    Was `m:ss`. Dropped in favour of one unit across the whole site: a page
    carrying "12:00" beside "+3.8" makes the reader work out that both are
    minutes and that one of them is not a clock time.
    """
    return _min(v, plus=False)


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
    cap_col = f"{side}_signal"
    good = ("**negative** -- the track began before take-off" if is_dep
            else "**positive** -- the track ran on past landing")

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
               f"{'take-off' if is_dep else 'landing'}.")
        if total:
            parts = ", ".join(f"{p}: {a} below / {b} above"
                              for p, (a, b) in over.items() if a or b)
            cap += (f" {total} movement(s) fall outside +/-{CLIP_MIN:.0f} min "
                    f"and are excluded from the plot ({parts}). They are "
                    f"included in every percentile below.")
        out.append(f"![{cap}](figures/{hist})\n")

    # `off_s` is the track's *start* against take-off; `land_s` is its *end*
    # against landing. Calling both "when the track starts" described the
    # arrival column as the opposite of what it measures.
    edge = "starts" if is_dep else "ends"
    kind = "take-off" if is_dep else "landing"
    out.append(f"**When the track {edge}, relative to {kind} (minutes)**\n")
    out.append(_table(_pct_rows(frames, off_col, _min),
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
        out.append(f"**How much of the {phase} was received "
                   f"(1.00 = every expected report arrived)**\n")
        out.append(_table(_pct_rows(frames, cap_col, _f),
                          ["period", "n"] + [f"p{q}" for q in PCTS]))

    return "\n".join(out)


def _context_section(stats, tier, ranking, latest) -> str:
    out = ["## Against the fleet\n"]
    if latest not in stats or ranking is None or len(ranking) == 0:
        out.append("*Not present in the latest period's ranking.*\n")
        return "\n".join(out)
    row = stats[latest]
    cols = ([("coverage_index", _f), ("detection_pct_dep", _p),
             ("dep_signal_p50", _f), ("arr_signal_p50", _f),
             ("off_s_p50", _min), ("land_s_p50", _min)]
            if tier == "A" else
            [("detection_pct_dep", _p), ("detection_pct_arr", _p),
             ("off_s_p50", _min), ("land_s_p50", _min)])
    rows = []
    for col, fmt in cols:
        if col not in ranking.columns or col not in row.index:
            continue
        v = row[col]
        fleet = ranking[col].dropna()
        if pd.isna(v) or fleet.empty:
            continue
        rows.append({
            "measure": tip_header(col),
            "this aerodrome": fmt(v),
            "typical aerodrome": fmt(fleet.median()),
            "rank (0–100)": f"{100.0 * (fleet < v).sum() / len(fleet):.0f}",
        })
    tier_name = (f"the {len(ranking)} aerodromes with measured milestones"
                 if tier == "A"
                 else "the aerodromes with estimated milestones")
    out.append(
        f"How this aerodrome compares with {tier_name}. **Typical aerodrome** "
        f"is the median across all of them. **Rank** is this aerodrome's "
        f"position among them, 0 (lowest) to 100 (highest).\n"
    )
    out.append(_table(rows, ["measure", "this aerodrome", "typical aerodrome",
                             "rank (0–100)"]))
    out.append("*Higher rank is better everywhere except track start vs "
               "take-off, where a low value is the good case.*\n")
    return "\n".join(out)


def _quality_section(stats) -> str:
    """Did the algorithm turn these flights into tracks correctly?

    Separate from coverage: a low coverage number can mean the receivers did
    not hear the aircraft, or that the algorithm cut its track up. This table
    is how a reader tells those apart.
    """
    cols = ["period",
            tip_header("clean_pct_dep"),
            tip_header("fragmented_pct_dep"),
            tip_header("merged_pct_dep")]
    rows = []
    for p, r in stats.items():
        for side, sfx in (("departures", "dep"), ("arrivals", "arr")):
            rows.append({
                "period": f"{p} {side}",
                cols[1]: _p(r.get(f"clean_pct_{sfx}")),
                cols[2]: _p(r.get(f"fragmented_pct_{sfx}")),
                cols[3]: _p(r.get(f"merged_pct_{sfx}")),
            })
    return ("## Was each flight tracked as one flight?\n\n"
            "A poor coverage number can mean the receivers heard nothing, or "
            "that the algorithm cut the flight's track up. This separates "
            "them.\n\n"
            + _table(rows, cols))


def _counts_section(stats) -> str:
    """The raw numbers everything else is derived from."""
    cols = ["period",
            tip_header("n_gt_dep"), tip_header("n_detected_dep"),
            tip_header("n_gt_arr"), tip_header("n_detected_arr"),
            tip_header("n_capture_excluded"),
            tip_header("taxi_out_median_s"), tip_header("taxi_in_median_s")]
    rows = []
    for p, r in stats.items():
        rows.append({
            "period": p,
            cols[1]: _i(r.get("n_gt_dep")),
            cols[2]: _i(r.get("n_detected_dep")),
            cols[3]: _i(r.get("n_gt_arr")),
            cols[4]: _i(r.get("n_detected_arr")),
            cols[5]: _i(r.get("n_capture_excluded_dep")),
            cols[6]: _dur(r.get("taxi_out_median_s")),
            cols[7]: _dur(r.get("taxi_in_median_s")),
        })
    return (
        "## The underlying counts\n\n"
        "Everything above is derived from these. Typical taxi times are "
        "context: the same 200 seconds of reception is most of a short taxi "
        "and a fraction of a long one.\n\n"
        + _table(rows, cols)
    )


def _storyline(tier, row, period=None) -> str:
    """Two or three sentences saying what this aerodrome's numbers amount to.

    Written from the numbers rather than fixed text, so a page cannot describe
    an aerodrome it does not match. Kept short on purpose: the tables carry the
    detail, and a reader who wants prose is not served by more of it.
    """
    if row is None:
        return "No statistics for this aerodrome in the latest period.\n"

    det = row.get("detection_pct_dep")
    idx = row.get("coverage_index")
    sig = row.get("dep_signal_p50")
    band = rating(idx)

    # The period travels with the sentence. This is the latest period's row,
    # and the table directly beneath it lists every period -- so a bare
    # "of movements" invites the reader to attach the figure to the wrong row.
    _in = f" in {period}" if period else ""
    seen = (f"nearly every movement{_in} is picked up" if det is not None
            and not pd.isna(det) and det >= 98
            else f"{_p(det)} of movements{_in} are picked up")

    if tier != "A":
        # The estimated taxi-out is stated only when there is one, and always
        # as a median with its looseness attached. Asserting it flatly would
        # give a predicted window the standing of a measured one.
        if sig is None or pd.isna(sig):
            est = ("Its taxi-out could not be estimated either — no departure "
                   "in the sample had a usable predicted window.")
        elif sig < 0.05:
            est = ("Across its departures, essentially none of the taxi-out "
                   "reached the network: this aerodrome is invisible on the "
                   "ground even though its flights are seen in the air.")
        else:
            est = (f"Across its departures, a median of **{_f(sig)}** of the "
                   f"taxi-out reached the network, estimated against a "
                   f"predicted taxi duration. Read it as a tendency for this "
                   f"aerodrome, not a fact about one flight.")
        return (
            f"Coverage here is judged on **estimated** reference times. What "
            f"can be said firmly is whether flights were seen at all: {seen}. "
            f"{est} There is no arrival figure, so this page carries no "
            f"coverage index.\n"
        )

    if pd.isna(sig):
        body = "Ground coverage could not be measured here."
    elif sig >= 0.9:
        body = ("Aircraft are tracked essentially throughout their time on the "
                "ground, so surface events can be derived with confidence.")
    elif sig >= 0.5:
        body = ("Roughly half to most of each ground movement is received — "
                "usable, but with gaps that will show in any surface event "
                "derived from it.")
    elif sig > 0.05:
        body = ("Only fragments of ground movement reach the network. Surface "
                "events here rest on very little evidence.")
    else:
        body = ("Almost nothing is received while aircraft are on the ground. "
                "They become visible only once airborne, so no surface event "
                "can be derived at this aerodrome.")

    # A percentage, not the raw ratio: "1.000 arrive" is a number in the
    # middle of a sentence and reads as a count rather than a share.
    pct = "—" if pd.isna(sig) else f"{min(sig, 1.0) * 100:.0f}%"
    # "None coverage" is what the bare band name produces, so the opening is
    # phrased per band rather than templated from it.
    opener = {"None": "No ground coverage.",
              "Poor": "Poor coverage.",
              "Partial": "Partial coverage.",
              "Good": "Good coverage.",
              "Excellent": "Excellent coverage."}.get(band, f"{band} coverage.")
    return (f"**{opener}** {seen.capitalize()}, and {pct} of the "
            f"position reports expected while taxiing out actually arrive. "
            f"{body}\n")


def _map_section(figs) -> str:
    """The interactive coverage map, or an explanation of its absence."""
    html = figs.get("map_html")
    if not html:
        if not figs.get("map_expected"):
            return ""
        return (
            "## Where the coverage is\n\n"
            "::: {.callout-warning}\n"
            "## Nothing observed near the aerodrome\n\n"
            "No position report was received from an aircraft on the ground "
            "here, or from one airborne below 1,500 ft, in any sampled "
            "period. There is no map to draw: aircraft only become visible "
            "once they are already well above the aerodrome.\n"
            ":::\n"
        )
    lines = [
        "## Where the coverage is\n",
        "Each position report is placed on a hexagonal grid over the "
        "aerodrome, on a log colour scale: one apron cell can hold thousands "
        "of reports while a runway threshold holds tens. Empty ground is "
        "surface the receivers do not reach.\n",
    ]
    # The two layers are not always both there, and the instruction has to
    # match what the reader is looking at: telling someone to switch on a
    # layer that is already the only thing drawn sends them hunting for a
    # control that will not change anything.
    if figs.get("map_has_ground"):
        lines.append("Use the legend to add the **airborne** layer and any "
                     "**example flights**. Scroll to zoom.\n")
    else:
        lines.append(
            "**Nothing here was received on the ground.** Every report drawn "
            "was made in the air, below 1,500 ft, so the map shows the "
            "approach and the climb-out and stops where the surface begins. "
            "Use the legend to switch off layers or any **example flights**. "
            "Scroll to zoom.\n")
    lines.append("```{=html}\n" + html + "\n```\n")
    if figs.get("tracks_note"):
        lines.append(figs["tracks_note"])
    return "\n".join(lines)


def build_page(tier, stats, frames_by_side, ranking, latest, figs) -> str:
    """The markdown body for one aerodrome. No YAML front matter.

    ``stats`` maps period -> that period's row from
    ``airport_stats_<period>.csv``, newest first. ``frames_by_side`` maps
    "dep"/"arr" -> {period -> frame}. ``figs`` maps a figure key to its
    filename, plus ``<side>_hist_overflow``.
    """
    out = []
    latest_row = stats.get(latest) if stats else None
    out.append(_storyline(tier, latest_row, latest))

    # "departures"/"arrivals" are movement counts, and the period column
    # beside them is what makes each row's counts unambiguous.
    head_cols = ["period", "departures", "arrivals",
                 tip_header("detection_pct_dep"),
                 tip_header("detection_pct_arr"),
                 tip_header("coverage_index")]
    head = [{
        "period": p,
        "departures": _i(r.get("n_gt_dep")),
        "arrivals": _i(r.get("n_gt_arr")),
        head_cols[3]: _p(r.get("detection_pct_dep")),
        head_cols[4]: _p(r.get("detection_pct_arr")),
        head_cols[5]: _f(r.get("coverage_index")),
    } for p, r in stats.items()]
    out.append(_table(head, head_cols))

    out.append(_side_section("dep", frames_by_side.get("dep", {}), tier, figs))
    out.append(_side_section("arr", frames_by_side.get("arr", {}), tier, figs))
    out.append(_map_section(figs))
    if tier != "A":
        out.append(TIERS_EXPLAINED)
    out.append(_context_section(stats, tier, ranking, latest))
    out.append(_quality_section(stats))
    out.append(_counts_section(stats))
    out.append("\n[<- back to rankings](../index.qmd)\n")
    return "\n".join(out)
