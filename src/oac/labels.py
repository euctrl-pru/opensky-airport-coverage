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
#: rankings page and on every Tier B aerodrome page.
TIERS_EXPLAINED = """\
::: {.callout-note collapse="true"}
## Measured or estimated? The two tiers

Coverage is judged against reference data, and there are two sources of it.

**Tier A — measured (APDF).** Airport operators report the real times: off the
stand, wheels off, wheels on, on the stand. All four are observed facts. With
them the taxi phase has exact bounds, so we can say precisely how much of it
was received. About 69 aerodromes.

**Tier B — estimated (Network Manager).** Covers all of Europe, but take-off
is *inferred* as off-block plus a predicted taxi time, and there is **no
in-block time at all**. Without a real arrival stand time there is no arrival
taxi phase to measure. So Tier B airports are judged only on whether their
flights were seen at all, not on how much of the ground movement was received.

The inference was checked against real APDF movements and agrees to a median of
0 s. It is good — but a predicted taxi time cannot be used as the denominator
of a taxi-coverage measurement without measuring the prediction as much as the
reception. The tiers are therefore ranked separately and never mixed.
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
}

EXPLAIN = {
    "n_gt": "How many take-offs or landings the reference data records here "
            "over the sampled days. Every other number is unreliable when this "
            "is small, so an aerodrome needs at least 20 to be ranked.",
    "n_gt_dep": "Take-offs the reference data records here over the sampled days.",
    "n_gt_arr": "Landings the reference data records here over the sampled days.",
    "n_detected": "How many of those movements OpenSky picked up at all, even "
                  "once.",
    "n_detected_dep": "Take-offs OpenSky picked up at all, even once.",
    "n_detected_arr": "Landings OpenSky picked up at all, even once.",
    "detection_pct": "The share of movements seen at all. 100% means every "
                     "flight in the reference data produced at least one "
                     "position report. This is the most basic coverage "
                     "question there is.",
    "detection_pct_dep": "The share of departures seen at all.",
    "detection_pct_arr": "The share of arrivals seen at all.",
    "measured_pct": "The share of movements whose off-block and take-off times "
                    "are measured rather than estimated. Above 50% puts an "
                    "aerodrome in Tier A, where taxi coverage can be computed.",
    "measured_pct_dep": "As above, for departures.",
    "measured_pct_arr": "As above, for arrivals.",
    "n_capture_excluded": "Movements whose reference times are impossible — "
                          "an off-block after take-off, say. They are left out "
                          "of the coverage figures rather than counted as zero "
                          "coverage, and shown here so you can see how many.",
    "n_capture_excluded_dep": "As above, on the departure side.",
    "n_capture_excluded_arr": "As above, on the arrival side.",
    "dep_signal_p50": "Of the position reports we should have received while "
                      "the aircraft taxied out — one every 5 seconds — how "
                      "many actually arrived. 1.00 means the aircraft was "
                      "tracked the whole way; 0.10 means nine reports in ten "
                      "were never received.",
    "arr_signal_p50": "The same for taxi-in, between touchdown and the stand.",
    "signal_p50": "How much of a typical ground movement was actually "
                  "received, averaging the taxi-out and taxi-in figures.",
    "rating": "A plain-language band over the coverage index, so the table can "
              "be scanned without reading decimals. The index is shown beside "
              "it.",
    "dep_continuity_p50": "The share of 30-second slices of the taxi-out that "
                          "contained at least one report. Read against "
                          "\"received\": a high figure here with a low one "
                          "there means a thin but unbroken stream; the reverse "
                          "means a dense burst around a gap.",
    "arr_continuity_p50": "The same for taxi-in.",
    "dep_continuity_p10": "The worst-covered tenth of departures.",
    "arr_continuity_p10": "The worst-covered tenth of arrivals.",
    "dep_continuity_p90": "The best-covered tenth of departures.",
    "arr_continuity_p90": "The best-covered tenth of arrivals.",
    "dep_max_gap_median_s": "The longest unbroken silence during taxi-out, for "
                            "a typical departure. A large gap with otherwise "
                            "good coverage points at one blind spot rather than "
                            "poor reception overall.",
    "arr_max_gap_median_s": "The same for taxi-in.",
    "dep_reach_p50": "How much of the taxi-out the track *spans*, from its "
                     "first position report to take-off. Shown beside the "
                     "observed figure because the two disagree in a "
                     "revealing way: a single report at the stand spans the "
                     "whole taxi while observing almost none of it.",
    "arr_reach_p50": "The same for taxi-in.",
    "off_s_p50": "How long after take-off the track begins, in seconds. "
                 "Negative is good — it means the aircraft was already being "
                 "tracked on the ground. Positive means part of the departure "
                 "was missed.",
    "off_s_p10": "The earliest tenth of tracks — how far ahead of take-off "
                 "coverage begins when it is at its best here.",
    "off_s_p90": "The latest tenth — how much of the departure is missed in "
                 "the worst cases.",
    "land_s_p50": "How long after landing the track ends, in seconds. Positive "
                  "is good — it means the aircraft was still tracked while "
                  "taxiing in.",
    "land_s_p10": "The worst tenth, where the track ends earliest relative to "
                  "landing.",
    "land_s_p90": "The best tenth, where tracking continues longest.",
    "dep_no_ground_pct": "The share of departures never heard while on the "
                         "ground — the track only starts once airborne.",
    "arr_no_ground_pct": "The share of arrivals lost at or before touchdown.",
    "dep_full_capture_pct": "The share of departures where essentially the "
                            "whole taxi-out was observed, with no meaningful "
                            "gap.",
    "arr_full_capture_pct": "The same for taxi-in.",
    "taxi_out_median_s": "How long a typical taxi-out takes here. Context: the "
                         "same 200 seconds of coverage is most of a small "
                         "aerodrome's taxi and a fraction of a large hub's.",
    "taxi_in_median_s": "How long a typical taxi-in takes here.",
    "clean_pct_dep": "The share of flights matched to exactly one track, with "
                     "nothing else in it. The algorithm got these right.",
    "clean_pct_arr": "As above.",
    "fragmented_pct_dep": "The share of flights broken across several tracks. "
                          "Recoverable — the flight is present, in pieces.",
    "fragmented_pct_arr": "As above.",
    "merged_pct_dep": "The share of flights sharing a track with another "
                      "flight. Worse than fragmentation: the other flight "
                      "simply does not appear in the output.",
    "merged_pct_arr": "As above.",
    "measured": "Whether this aerodrome's real stand and runway times are "
                "recorded. Where they are, how much of each ground movement "
                "was received can be measured; where they are not, only "
                "whether the flight was seen at all.",
    "coverage_index": "One number combining the two questions: how often is a "
                      "flight seen at all, and how much of its time on the "
                      "ground is genuinely observed. It is the first "
                      "multiplied by the second, so 1.00 is perfect and 0.00 "
                      "means the aerodrome surface is effectively invisible.",
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
