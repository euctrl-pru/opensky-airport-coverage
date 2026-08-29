"""Display names and plain-language explanations for every published column.

The tables on this site are read by people who did not write the pipeline. A
header reading `dep_capture_p50` obliges them to leave the page, find a
glossary, and hold fifty definitions in their head before the first number
means anything.

So every column has two things here: a **display name** carrying its unit and
its direction, and a **one-sentence explanation** in ordinary language. Tables
render the display name; each table is preceded by a collapsible block
explaining only the columns *it* uses, so a reader meets ten terms where they
are needed rather than fifty on a reference page.

`site/metrics.qmd` remains the full reference for someone who wants the
formula. This module is what makes consulting it optional.
"""

__all__ = ["LABELS", "EXPLAIN", "UNRANKED", "RATINGS", "label", "explain",
           "rename", "explain_block", "rating", "TIERS_EXPLAINED"]

#: Plain-language bands over the coverage index, so a reader can scan a
#: 69-row table without reading three decimal places on every line. The
#: thresholds are round numbers chosen to be legible, not fitted to the data;
#: the index itself is always shown beside the word so the banding can be
#: checked rather than trusted.
RATINGS = (
    (0.90, "Excellent", "Tracked throughout, on the ground and in the air."),
    (0.60, "Good", "Most of each movement observed, with some gaps."),
    (0.30, "Partial", "Roughly half of a typical movement is missed."),
    (0.05, "Poor", "Only fragments of ground movement are received."),
    (0.00, "None", "Aircraft are effectively invisible until airborne."),
)


def rating(index) -> str:
    """The band a coverage index falls in, or an em dash when there is none."""
    import math

    if index is None or (isinstance(index, float) and math.isnan(index)):
        return "—"
    for threshold, name, _ in RATINGS:
        if index >= threshold:
            return name
    return RATINGS[-1][1]


#: The difference readers most need and are least likely to guess. Used on the
#: rankings page and on every estimated aerodrome's page.
TIERS_EXPLAINED = """\
::: {.callout-note collapse="true"}
## Measured or estimated? The two kinds of aerodrome

Coverage is judged against reference data, and there are two sources of it.

**Tier A (measured) - the airport's own records.** Airport operators report the
real times: off the stand, wheels off, wheels on, on the stand. All four are
observed facts. With them the taxi phase has exact bounds, so we can say
precisely how much of it was received.

**Tier B (estimated) - Network Manager.** Covers all of Europe, but **none of
its runway or stand times are observed**. The flight table records an off-block
time and a predicted taxi time, and take-off is inferred by adding the two.

**What an estimated aerodrome can and cannot be asked.** The predicted taxi
duration is *unbiased* - checked against real airport records it sits a median
of 13 s from the truth - but *imprecise*: the middle half of flights are off by
up to five minutes, and only one in six lands within a minute. Per flight that
window is useless as a yardstick. Across a few hundred movements the error
cancels, so a **median** taxi-out figure is meaningful even though no
individual one is. An estimated aerodrome therefore carries an *estimated*
departure coverage, shown in its own column and never mixed into the measured
ranking.

The arrival side has no such fallback. Network Manager records no in-block time
anywhere, so there is nothing to mark the end of a taxi-in, and no arrival
coverage is computed for an estimated aerodrome. That is also why the coverage
index, which needs both sides, appears only in the measured table.
:::
"""

#: Columns that carry no measurement and need no explanation.
UNRANKED = {"icao", "name", "rank", "lat", "lon", "t_source", "period"}

LABELS = {
    # identity
    "icao": "ICAO",
    "name": "Aerodrome",
    "rank": "#",
    # counts and detection
    "n_gt": "Movements",
    "n_gt_dep": "Departures",
    "n_gt_arr": "Arrivals",
    "n_detected": "Movements seen",
    "n_detected_dep": "Departures seen",
    "n_detected_arr": "Arrivals seen",
    "detection_pct": "Flights seen (%)",
    "detection_pct_dep": "Departures seen (%)",
    "detection_pct_arr": "Arrivals seen (%)",
    "n_capture_excluded": "Unusable reference rows",
    "n_capture_excluded_dep": "Unusable reference rows (dep)",
    "n_capture_excluded_arr": "Unusable reference rows (arr)",
    "measured_pct": "Milestones measured (%)",
    "measured_pct_dep": "Departure milestones measured (%)",
    "measured_pct_arr": "Arrival milestones measured (%)",
    # signal -- the headline quantity
    "dep_signal_p50": "Taxi-out received (median)",
    "dep_signal_est": "Taxi-out received (estimated)",
    "arr_signal_p50": "Taxi-in received (median)",
    "signal_p50": "Ground movement received",
    "rating": "Coverage",
    # bin occupancy -- the gap detector
    "dep_continuity_p50": "Taxi-out without gaps (median)",
    "arr_continuity_p50": "Taxi-in without gaps (median)",
    "dep_continuity_p10": "Taxi-out observed (worst 10%)",
    "arr_continuity_p10": "Taxi-in observed (worst 10%)",
    "dep_continuity_p90": "Taxi-out observed (best 10%)",
    "arr_continuity_p90": "Taxi-in observed (best 10%)",
    "dep_max_gap_median_s": "Longest taxi-out gap (s, median)",
    "arr_max_gap_median_s": "Longest taxi-in gap (s, median)",
    # reach -- retained as a diagnostic
    "dep_reach_p50": "Taxi-out spanned (median)",
    "arr_reach_p50": "Taxi-in spanned (median)",
    # boundary error
    "off_s_p10": "Track start vs take-off (s, earliest 10%)",
    "off_s_p50": "Track start vs take-off (s, median)",
    "off_s_p90": "Track start vs take-off (s, latest 10%)",
    "land_s_p10": "Track end vs landing (s, earliest 10%)",
    "land_s_p50": "Track end vs landing (s, median)",
    "land_s_p90": "Track end vs landing (s, latest 10%)",
    "dep_no_ground_pct": "Never seen on the ground (%)",
    "arr_no_ground_pct": "Lost at touchdown (%)",
    "dep_full_capture_pct": "Whole taxi-out observed (%)",
    "arr_full_capture_pct": "Whole taxi-in observed (%)",
    "taxi_out_median_s": "Typical taxi-out (s)",
    "taxi_in_median_s": "Typical taxi-in (s)",
    # segmentation
    "clean_pct_dep": "One flight, one track (%)",
    "clean_pct_arr": "One flight, one track (%)",
    "fragmented_pct_dep": "Split across tracks (%)",
    "fragmented_pct_arr": "Split across tracks (%)",
    "merged_pct_dep": "Merged with another flight (%)",
    "merged_pct_arr": "Merged with another flight (%)",
    # the index
    "coverage_index": "Coverage index",
    "measured": "Times measured?",
    "tracking_err_pct": "Tracking errors (%)",
}

EXPLAIN = {
    "n_gt": "Every take-off and landing the reference data records at this "
            "aerodrome over the sampled days. Departures are counted against "
            "the flight's origin and arrivals against its destination, so a "
            "single flight contributes one movement at each end. The reference "
            "data is the Network Manager flight table, which lists what "
            "actually operated — it is independent of ADS-B, which is what "
            "makes it usable as a yardstick. Aerodromes below 20 movements are "
            "left out of the rankings entirely: a percentile over a handful of "
            "flights is noise wearing the same formatting as a finding.",
    "n_gt_dep": "Take-offs the reference data records here over the sampled "
                "days, counted against the flight's origin aerodrome.",
    "n_gt_arr": "Landings the reference data records here, counted against the "
                "flight's destination aerodrome.",
    "n_detected": "How many of those movements produced any ADS-B position "
                  "report at all. Each reference flight is matched to position "
                  "reports by airframe — the 24-bit ICAO address, which both "
                  "sources carry — and by time: a report counts if its "
                  "timestamp falls inside that flight's own airborne interval. "
                  "Callsign is deliberately not used, because the "
                  "track-building rule may change it. One matching report is "
                  "enough for the movement to count as seen.",
    "n_detected_dep": "Take-offs with at least one matching position report. "
                      "See “Movements seen”.",
    "n_detected_arr": "Landings with at least one matching position report.",
    "detection_pct": "Movements seen divided by movements the reference data "
                     "records, as a percentage. **Read this as a floor, not a "
                     "coverage figure**: it sits above 99% at four aerodromes "
                     "in five, so it separates “invisible to the network” from "
                     "“seen, but only partly” and says nothing at all about "
                     "how much of a movement was tracked.\n\n"
                     "**What “seen” means, exactly.** Each flight in the "
                     "reference data has a recorded take-off time and landing "
                     "time. A flight counts as seen if at least **one** ADS-B "
                     "position report exists that (a) comes from the same "
                     "airframe — matched on the 24-bit ICAO address the "
                     "aircraft transmits, which both sources carry — and (b) "
                     "has a timestamp between that flight's take-off and "
                     "landing. Callsign is deliberately not used for the "
                     "match, because the rule that builds tracks can change "
                     "it, and matching on it would test that rule rather than "
                     "the reception.\n\n"
                     "Note the window is the **airborne** one. Reports while "
                     "the aircraft is taxiing do not make a flight “seen” — "
                     "in practice an aircraft heard on the ground is heard in "
                     "the air too, so this rarely bites, but it is why this "
                     "number says nothing about ground coverage.\n\n"
                     "One report over a whole flight is enough, so this is the "
                     "weakest possible test and is meant to be: it separates "
                     "“invisible to the network” from “seen, but only partly”. "
                     "Almost everywhere in Europe it sits above 99%, which is "
                     "why it cannot be the whole story.",
    "detection_pct_dep": "As above, over departures only.",
    "detection_pct_arr": "As above, over arrivals only.",
    "measured_pct": "The share of this aerodrome's movements whose stand and "
                    "runway times come from the airport operator's own records "
                    "rather than being estimated. At or above 50% the "
                    "aerodrome is treated as measured, and its ground coverage "
                    "can be computed; below it, only whether flights were seen "
                    "at all. The test is applied to the aerodrome's busier "
                    "side, and in practice it is not a close call — aerodromes "
                    "cluster near 0% or near 100%, with almost nothing "
                    "between.",
    "measured_pct_dep": "As above, over departures only.",
    "measured_pct_arr": "As above, over arrivals only.",
    "measured": "Whether this aerodrome's real stand and runway times are "
                "recorded by the operator. Where they are, the taxi phase has "
                "exact bounds and how much of it was received can be measured; "
                "where they are not, only whether the flight was seen at all.",
    "n_capture_excluded": "Movements whose recorded times are impossible — an "
                          "off-block after take-off, or an on-stand before "
                          "landing. They are dropped from the ground-coverage "
                          "figures and counted here instead. Dropping rather "
                          "than clamping matters: a movement with a negative "
                          "taxi duration has no denominator, and forcing it to "
                          "zero or one would move this aerodrome's median for "
                          "a reason that has nothing to do with reception.",
    "n_capture_excluded_dep": "As above, on the departure side.",
    "n_capture_excluded_arr": "As above, on the arrival side.",

    "dep_signal_p50": "**How it is computed.** The taxi-out is the interval "
                      "between two measured times: off the stand, and wheels "
                      "off the runway. The feed delivers roughly one position "
                      "report every 5 seconds, so a taxi of *n* seconds should "
                      "produce about *n*/5 reports. We count how many actually "
                      "arrived inside that interval and divide by how many "
                      "were expected. The figure shown is the median across "
                      "this aerodrome's departures.\n\n"
                      "1.00 means the aircraft was tracked the whole way out. "
                      "0.10 means nine reports in ten never arrived. Values "
                      "slightly above 1.00 happen where the feed ran denser "
                      "than nominal and are left as they are rather than "
                      "capped.",
    "dep_signal_est": "The same count of received against expected reports as the measured taxi-out figure, but over a window Network Manager predicted rather than one an airport observed.\n\n**Read the median, never a single row of it.** The predicted taxi duration is unbiased - a median of 13 s from the real one - but imprecise: the middle half of flights are off by up to five minutes. One movement\u2019s figure is therefore not evidence; a median over a few hundred of them is, because the error cancels.\n\nShown only for aerodromes whose times are **not** measured. Where they are, the measured figure is used instead.",
    "arr_signal_p50": "The same computation over the taxi-in: the interval "
                      "between wheels on the runway and reaching the stand, "
                      "with reports counted against the same 5-second "
                      "expectation.",
    "signal_p50": "The average of the taxi-out and taxi-in figures, giving one "
                  "number for how much of a typical ground movement reaches "
                  "the network. Each side is a median over that aerodrome's "
                  "own movements first, so a single very good or very bad "
                  "flight cannot move it.",
    "dep_continuity_p50": "A second, looser reading of the same interval. The "
                          "taxi-out is cut into 30-second slices and we count "
                          "how many contained **at least one** report, "
                          "regardless of how many were expected in it.\n\n"
                          "Read it against “received”. High here and low there "
                          "means a thin but unbroken stream — something arrived "
                          "in every half-minute, but far less than it should "
                          "have. The reverse means a dense burst with a hole "
                          "in it. Neither is visible in the other number.",
    "arr_continuity_p50": "The same over the taxi-in.",
    "dep_continuity_p10": "The worst-covered tenth of departures, by the "
                          "30-second-slice measure.",
    "dep_continuity_p90": "The best-covered tenth of departures, by the same "
                          "measure.",
    "arr_continuity_p10": "The worst-covered tenth of arrivals.",
    "arr_continuity_p90": "The best-covered tenth of arrivals.",
    "dep_max_gap_median_s": "The longest unbroken silence during taxi-out, for "
                            "a typical departure. Measured from the start of "
                            "the taxi to the first report, between consecutive "
                            "reports, and from the last report to wheels-off — "
                            "so a receiver that stops halfway is counted as "
                            "having a gap even though no two reports straddle "
                            "it. A large gap alongside otherwise good reception "
                            "points at one blind spot rather than weak coverage "
                            "throughout.",
    "arr_max_gap_median_s": "The same for taxi-in.",
    "dep_reach_p50": "How far back the track's **first** report lies, as a "
                     "fraction of the taxi: the seconds between that first "
                     "report and wheels-off, divided by the whole taxi "
                     "duration.\n\n"
                     "It is shown because it disagrees with “received” in a "
                     "revealing way. A single report at the stand and nothing "
                     "afterwards spans the entire taxi and scores 1.00 here, "
                     "while “received” correctly scores it near zero. Above "
                     "1.00 the track began before the aircraft left the stand; "
                     "below zero it began after the aircraft was already "
                     "airborne. Neither is clipped, because both are real.",
    "arr_reach_p50": "The same on the arrival side, measured forward from "
                     "touchdown to the track's last report.",
    "off_s_p50": "The gap between when the track starts and when the aircraft "
                 "actually left the ground, in seconds, for a typical "
                 "departure. Computed as the track's first position report "
                 "minus the recorded take-off time.\n\n"
                 "**Negative is good**: the track began before wheels-off, so "
                 "the aircraft was already being followed on the ground. "
                 "Positive means part of the departure was never seen.",
    "off_s_p10": "The earliest tenth of departures — how far ahead of take-off "
                 "tracking begins when this aerodrome is at its best.",
    "off_s_p90": "The latest tenth — how much of the departure is missed in "
                 "the worst cases here.",
    "land_s_p50": "The gap between landing and the end of the track, in "
                  "seconds, for a typical arrival: the track's last position "
                  "report minus the recorded landing time.\n\n"
                  "**Positive is good**: the aircraft was still being tracked "
                  "while it taxied in. Negative means the track ended before "
                  "the aircraft was down.",
    "land_s_p10": "The worst tenth, where tracking stops earliest relative to "
                  "landing.",
    "land_s_p90": "The best tenth, where tracking continues longest after it.",
    "dep_no_ground_pct": "The share of departures whose track starts at or "
                         "after wheels-off — the aircraft was never heard while "
                         "it was on the ground at all.",
    "arr_no_ground_pct": "The share of arrivals whose track ends at or before "
                         "touchdown.",
    "dep_full_capture_pct": "The share of departures where at least 95% of the "
                            "expected reports arrived during taxi-out — "
                            "effectively complete coverage of the ground "
                            "movement.",
    "arr_full_capture_pct": "The same for taxi-in.",
    "taxi_out_median_s": "How long a typical taxi-out takes here, from off the "
                         "stand to wheels off. Context rather than a coverage "
                         "figure: the same 200 seconds of reception is most of "
                         "a short taxi and a fraction of a long one, which is "
                         "why coverage is expressed as a fraction and not in "
                         "seconds.",
    "taxi_in_median_s": "How long a typical taxi-in takes here, from wheels on "
                        "to reaching the stand.",
    "clean_pct_dep": "The share of movements the track-building algorithm "
                     "matched to exactly one track that contains no other "
                     "flight. Position reports arrive as a continuous stream "
                     "per airframe with no notion of a flight, so they have to "
                     "be cut into flights first; this says how often that cut "
                     "was right here.",
    "clean_pct_arr": "As above, over arrivals.",
    "fragmented_pct_dep": "The share of movements broken across several tracks. "
                          "Recoverable — the flight is present, in pieces — but "
                          "coverage is measured against the largest piece, so a "
                          "fragmented flight's coverage is understated.",
    "fragmented_pct_arr": "As above, over arrivals.",
    "merged_pct_dep": "The share of movements sharing a track with another "
                      "flight. The worse failure: only one flight comes out of "
                      "a merged track, so the other simply does not exist "
                      "downstream and nothing can recover it.",
    "merged_pct_arr": "As above, over arrivals.",
    "tracking_err_pct": "The share of this aerodrome's movements the "
                        "track-building step got wrong, split and merged "
                        "added together.\n\n"
                        "Position reports arrive as one continuous stream per "
                        "aircraft with nothing marking where a flight begins "
                        "or ends, so flights have to be cut out of it. A "
                        "*split* flight is cut into several tracks and its "
                        "coverage is measured against only the largest piece, "
                        "understating it. A *merged* pair is left in one "
                        "track, and only one of the two flights survives "
                        "downstream.\n\n"
                        "Both depress coverage for reasons that have nothing "
                        "to do with reception, so a high figure means read "
                        "this aerodrome's coverage with caution. Its own page "
                        "separates split from merged.",
    "coverage_index": "**How it is computed.** Two fractions multiplied "
                      "together:\n\n"
                      "1. the share of movements seen at all, and\n"
                      "2. the share of a typical ground movement actually "
                      "received — the average of the taxi-out and taxi-in "
                      "medians.\n\n"
                      "Read it as the expected share of one movement that the "
                      "network captures: the chance the flight is seen at all, "
                      "times how much of its time on the ground is seen when "
                      "it is. 1.00 is perfect; 0.00 means the surface is "
                      "effectively invisible even though the aircraft may be "
                      "tracked once airborne.\n\n"
                      "It is deliberately **not** computed where the ground "
                      "figures are unavailable — it is left blank rather than "
                      "falling back to detection alone, which would rank an "
                      "unmeasurable aerodrome as though it were well covered.",
    "rating": "A band over the coverage index, so a long table can be scanned "
              "without reading three decimals on every row: **Excellent** at "
              "0.90 and above, **Good** from 0.60, **Partial** from 0.30, "
              "**Poor** from 0.05, and **None** below that. The thresholds are "
              "round numbers chosen to be legible rather than fitted to the "
              "data, and the index itself is shown beside the word so the "
              "banding can be checked rather than trusted.",
}


def label(col: str) -> str:
    """Display name for a column, falling back to the raw name."""
    return LABELS.get(col, col)


def explain(col: str) -> str:
    return EXPLAIN.get(col, "")


def rename(df):
    """Return `df` with display names as headers."""
    return df.rename(columns={c: label(c) for c in df.columns})


def explain_block(cols, title="What these columns mean") -> str:
    """A collapsed Quarto callout defining just these columns.

    Collapsed rather than open: a reader who knows the terms should see the
    table, and one who does not should not have to go looking.
    """
    rows = [(label(c), explain(c)) for c in cols
            if c not in UNRANKED and explain(c)]
    if not rows:
        return ""
    body = "\n\n".join(f"**{name}** — {text}" for name, text in rows)
    return (f"::: {{.callout-note collapse=\"true\"}}\n"
            f"## {title}\n\n{body}\n:::\n")
