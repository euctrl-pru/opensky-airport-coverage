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

from oac.labels import TIERS_EXPLAINED, explain_block, label, rating

#: Percentiles every distribution is summarised at.
#: Percentiles shown in the page tables. The aggregation computes and
#: publishes 10/25/50/75/90; the page shows three, because five columns of
#: percentiles per table is more precision than a reader scanning a page can
#: use, and the CSVs keep all of them.
PCTS = (10, 50, 90)

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


def _mmss(v):
    """Seconds as m:ss. "720" is a number; "12:00" is a taxi time."""
    if v is None or pd.isna(v):
        return "—"
    v = int(round(v))
    return f"{v // 60}:{v % 60:02d}"


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
        out.append(f"**How much of the {phase} was received "
                   f"(1.00 = every expected report arrived)**\n")
        out.append(explain_block([f"{side}_signal_p50",
                                  f"{side}_continuity_p50",
                                  f"{side}_max_gap_median_s"],
                                 title="Received, and without gaps"))
        out.append(_table(_pct_rows(frames, cap_col, _f),
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
             ("dep_signal_p50", _f), ("arr_signal_p50", _f),
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
            "measure": label(col),
            "this aerodrome": fmt(v),
            "typical aerodrome": fmt(fleet.median()),
            "rank (0–100)": f"{100.0 * (fleet < v).sum() / len(fleet):.0f}",
        })
    tier_name = (f"the {len(ranking)} aerodromes with measured milestones"
                 if tier == "A"
                 else "the aerodromes with estimated milestones")
    out.append(
        f"How this aerodrome compares with {tier_name}. **Typical "
        f"aerodrome** is the median across all of them — for \"seen (%)\" "
        f"that median is 100%, because at most aerodromes essentially every "
        f"flight is picked up at least once. **Rank** is this aerodrome's "
        f"position among them, from 0 (lowest value) to 100 (highest).\n"
    )
    out.append(explain_block([c for c, _ in cols],
                             title="What each row measures"))
    out.append(_table(rows, ["measure", "this aerodrome", "typical aerodrome",
                             "rank (0–100)"]))
    out.append("*Higher rank is better for everything above except **track "
               "start vs take-off**, where a low value — a track beginning "
               "before wheels-off — is the good case.*\n")
    return "\n".join(out)


def _quality_section(stats) -> str:
    """Did the algorithm turn these flights into tracks correctly?

    Separate from coverage: a low coverage number can mean the receivers did
    not hear the aircraft, or that the algorithm cut its track up. This table
    is how a reader tells those apart.
    """
    cols = ["period", "One flight, one track", "Split across tracks",
            "Merged with another flight"]
    rows = []
    for p, r in stats.items():
        for side, sfx in (("departures", "dep"), ("arrivals", "arr")):
            rows.append({
                "period": f"{p} {side}",
                "One flight, one track": _p(r.get(f"clean_pct_{sfx}")),
                "Split across tracks": _p(r.get(f"fragmented_pct_{sfx}")),
                "Merged with another flight": _p(r.get(f"merged_pct_{sfx}")),
            })
    return (
        "::: {.callout-note collapse=\"true\"}\n"
        "## Was each flight tracked as one flight?\n\n"
        "Before coverage can be read, the flights have to be cut out of the "
        "raw position stream correctly. This says how often that worked here. "
        "It matters because a poor coverage number has two possible causes, "
        "and they need different fixes:\n\n"
        "- **One flight, one track** — the algorithm got it right.\n"
        "- **Split across tracks** — one flight was cut into several. The "
        "flight is still there, in pieces, so its coverage is understated.\n"
        "- **Merged with another flight** — two flights ended up in one track. "
        "The worse failure: the other flight simply does not exist in the "
        "output, and nothing downstream can recover it.\n\n"
        + _table(rows, cols)
        + ":::\n"
    )


def _counts_section(stats) -> str:
    """The raw numbers everything else is derived from."""
    cols = ["period", "Departures in reference data", "…of those, seen",
            "Arrivals in reference data", "…of those, seen",
            "Unusable reference rows", "Typical taxi-out", "Typical taxi-in"]
    rows = []
    for p, r in stats.items():
        rows.append({
            "period": p,
            "Departures in reference data": _i(r.get("n_gt_dep")),
            "…of those, seen": _i(r.get("n_detected_dep")),
            "Arrivals in reference data": _i(r.get("n_gt_arr")),
            # Two columns cannot share a heading in a markdown table, so the
            # arrival one is disambiguated on the way out.
            "…of those, seen ": _i(r.get("n_detected_arr")),
            "Unusable reference rows": _i(r.get("n_capture_excluded_dep")),
            "Typical taxi-out": _mmss(r.get("taxi_out_median_s")),
            "Typical taxi-in": _mmss(r.get("taxi_in_median_s")),
        })
    cols = ["period", "Departures in reference data", "…of those, seen",
            "Arrivals in reference data", "…of those, seen ",
            "Unusable reference rows", "Typical taxi-out", "Typical taxi-in"]
    return (
        "::: {.callout-note collapse=\"true\"}\n"
        "## The underlying counts\n\n"
        "Everything above is derived from these. **Reference data** is the "
        "official record of which flights actually operated — the movements we "
        "expected to see. **Seen** is how many of them produced at least one "
        "position report. **Unusable reference rows** are movements whose "
        "recorded times are impossible, such as an off-block after take-off; "
        "they are left out of the coverage figures rather than counted as zero "
        "coverage.\n\n"
        "**Typical taxi** times are context: the same 200 seconds of reception "
        "is most of a short taxi and a fraction of a long one.\n\n"
        + _table(rows, cols)
        + ":::\n"
    )


def _storyline(tier, row) -> str:
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

    seen = ("nearly every movement is picked up" if det is not None
            and not pd.isna(det) and det >= 98
            else f"{_p(det)} of movements are picked up")

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
                   f"taxi-out reached the network — estimated against a "
                   f"predicted taxi duration, so read as a tendency for this "
                   f"aerodrome rather than a fact about any one flight.")
        return (
            f"Coverage here is judged on **estimated** reference times. The "
            f"question answered most firmly is whether flights were seen at "
            f"all: {seen}. {est} There is no arrival figure — no in-block time "
            f"is recorded outside APDF — so this page carries no coverage "
            f"index. See the note below.\n"
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
        "aerodrome, on a log colour scale — one apron cell can hold thousands "
        "of reports while a runway threshold holds tens. Empty ground is "
        "surface the receivers do not reach.\n",
        "Use the legend to add the **airborne** layer, which shows where "
        "reception begins on approach and departure, and the **example "
        "flights** if this aerodrome has them. Scroll to zoom.\n",
        "```{=html}\n" + html + "\n```\n",
    ]
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
    out.append(_storyline(tier, latest_row))

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
    if tier != "A":
        out.append(TIERS_EXPLAINED)
    out.append(_context_section(stats, tier, ranking, latest))
    out.append(_quality_section(stats))
    out.append(_counts_section(stats))
    out.append("\n[<- back to rankings](../index.qmd)\n")
    return "\n".join(out)
