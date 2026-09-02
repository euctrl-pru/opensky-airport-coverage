"""Display names and plain-language explanations for every published column.

The tables on this site are read by people who did not write the pipeline. A
header reading `dep_capture_p50` obliges them to leave the page, find a
glossary, and hold fifty definitions in their head before the first number
means anything.

So every column has three things here: a **display name** carrying its unit and
its direction, a **one-line tip** short enough for a tooltip, and a fuller
**explanation** in ordinary language. Tables show the display name and carry
the tip on hover. `site/metrics.qmd` renders the explanations in full, once.
"""

__all__ = ["LABELS", "TIPS", "EXPLAIN", "UNRANKED", "RATINGS", "RETRACTED",
           "PERIOD_SCOPED", "SAMPLE_DAYS",
           "label", "explain", "tip", "tip_header", "tip_headers",
           "rating_cell", "rename", "rating", "TIERS_EXPLAINED",
           "TIERS_EXPLAINED_OPEN"]

#: Plain-language bands over the coverage index, so a reader can scan a
#: 89-row table without reading three decimal places on every line. The
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
#: The tier note's body, written once. The rankings page shows it open --
#: it is where a reader first meets the two names, and a definition they have
#: to click for is a definition most of them never read. Each aerodrome page
#: shows the same text collapsed, because there it is a reminder rather than
#: an introduction.
_TIERS_BODY = """\
## Tier A (measured by APDF) and Tier B (estimated by NM)

The tier decides what can be measured.

**Tier A (measured by APDF).** The airport's own records give the real times:
off-block, take-off, landing, in-block. The taxi has exact bounds,
so how much of it arrived is a measurement.

**Tier B (estimated by NM).** Network Manager gives an off-block time and a
*predicted* taxi duration -- an estimate, not a measured one. With no runway
times, take-off is inferred, so only a median across a few hundred movements
is worth reading.

There is no in-block time either, so nothing ends a taxi-in; NM's arrival time
is off-block plus predicted taxi plus predicted flight duration, adding
nothing. Tier B therefore gets no arrival coverage, and the coverage index
needs both sides.

The all-aerodromes table holds both, its taxi-out column filled throughout and
asterisked where the window was measured."""

TIERS_EXPLAINED = (
    '::: {.callout-note collapse="true"}\n' + _TIERS_BODY + "\n:::"
)

#: The same note, open. Built from the same body so the two cannot drift.
TIERS_EXPLAINED_OPEN = "::: {.callout-note}\n" + _TIERS_BODY + "\n:::"

#: Columns that carry no measurement and need no explanation.
UNRANKED = {"icao", "name", "rank", "lat", "lon", "t_source", "period"}

#: Columns kept in `LABELS`/`TIPS`/`EXPLAIN` for reference but retracted from
#: every rendered table and download. `signal_p50` was cut 2026-08-29: it
#: duplicates `coverage_index` (r = 0.998, see `oac.tables.measured_table`),
#: so no page or CSV shows it any more. Recorded here, once, rather than as a
#: magic column name skipped inline wherever the column list is built.
#: `dep_signal_est` followed on 2026-09-01. It was `dep_signal_p50` blanked
#: wherever a measured figure existed, so that the estimate could never be read
#: as a second opinion on a measured aerodrome. The all-aerodromes table now
#: shows one taxi-out column for every row and marks the measured ones with an
#: asterisk instead: the two windows are still not comparable, but an em dash
#: told the reader nothing at all, and a labelled number tells them what they
#: came for. The definitions stay here because the quantity did not go away --
#: it is what `dep_signal_p50` means on a Tier B row.
RETRACTED = {"signal_p50", "dep_signal_est"}

LABELS = {
    # identity
    "icao": "ICAO",
    "name": "Aerodrome",
    "rank": "#",
    # counts and detection
    # `n_gt` is `max(dep, arr)` -- a sample-size gate for the >= 20
    # threshold, not a traffic figure. The column a reader sees is the
    # sum, which is what "movements" means in aviation.
    "n_gt": "Movements (larger side)",
    "n_movements": "Movements",
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
    # Unused since 2026-08-29: the column was removed from the ranking table
    # because it duplicates coverage_index (r = 0.998). Kept in case the
    # aerodrome pages want the combined figure -- but note EXPLAIN below is
    # the framing that removal retracted.
    "signal_p50": "Ground movement received",
    "rating": "Coverage",
    # bin occupancy -- the gap detector
    "dep_continuity_p50": "Taxi-out without gaps (median)",
    "arr_continuity_p50": "Taxi-in without gaps (median)",
    "dep_continuity_p10": "Taxi-out observed (worst 10%)",
    "arr_continuity_p10": "Taxi-in observed (worst 10%)",
    "dep_continuity_p90": "Taxi-out observed (best 10%)",
    "arr_continuity_p90": "Taxi-in observed (best 10%)",
    "dep_max_gap_median_s": "Longest taxi-out gap (min, median)",
    "arr_max_gap_median_s": "Longest taxi-in gap (min, median)",
    # reach -- retained as a diagnostic
    "dep_reach_p50": "Taxi-out spanned (median)",
    "arr_reach_p50": "Taxi-in spanned (median)",
    # boundary error
    "off_s_p10": "Track start vs take-off (min, earliest 10%)",
    "off_s_p50": "Track start vs take-off (min, median)",
    "off_s_p90": "Track start vs take-off (min, latest 10%)",
    "land_s_p10": "Track end vs landing (min, earliest 10%)",
    "land_s_p50": "Track end vs landing (min, median)",
    "land_s_p90": "Track end vs landing (min, latest 10%)",
    "dep_no_ground_pct": "Never seen on the ground (%)",
    "arr_no_ground_pct": "Lost at landing (%)",
    "dep_full_capture_pct": "Whole taxi-out observed (%)",
    "arr_full_capture_pct": "Whole taxi-in observed (%)",
    "taxi_out_median_s": "Typical taxi-out (min)",
    "taxi_in_median_s": "Typical taxi-in (min)",
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

#: One line per column, short enough for a `title` attribute. `EXPLAIN` below
#: carries the full definition, and the Metrics page is where it is rendered.
#: Plain text only: no markdown, no HTML, and no double quote, which would
#: close the attribute and leak the rest of the tip into the tag.
TIPS = {
    "n_gt": "The busier of this aerodrome's two sides. Used only for the 20-movement ranking floor.",
    "n_movements": "Take-offs plus landings the reference data records here, over the sampled days.",
    "n_gt_dep": "Take-offs recorded here, counted against each flight's origin aerodrome.",
    "n_gt_arr": "Landings recorded here, counted against each flight's destination aerodrome.",
    "n_detected": "How many of those movements produced at least one ADS-B position report.",
    "n_detected_dep": "Take-offs with at least one matching position report.",
    "n_detected_arr": "Landings with at least one matching position report.",
    "detection_pct": "Share of movements seen at least once in the air. A floor, not a coverage figure.",
    "detection_pct_dep": "Share of departures seen at least once in the air.",
    "detection_pct_arr": "Share of arrivals seen at least once in the air.",
    "n_capture_excluded": "Movements with impossible times, such as off-block after take-off. Dropped, not clamped.",
    "n_capture_excluded_dep": "Departures with impossible recorded times, excluded from the coverage figures.",
    "n_capture_excluded_arr": "Arrivals with impossible recorded times, excluded from the coverage figures.",
    "measured_pct": "Share of movements whose stand and runway times come from the airport operator.",
    "measured_pct_dep": "Share of departures with operator-recorded stand and runway times.",
    "measured_pct_arr": "Share of arrivals with operator-recorded stand and runway times.",
    "measured": "Whether the airport operator records this aerodrome's real stand and runway times.",
    "dep_signal_p50": "Share of the position reports a taxi-out should produce that arrived. Median across departures.",
    "dep_signal_est": "Share of expected taxi-out reports that arrived, over Network Manager's predicted taxi window. Median only, never one flight.",
    "arr_signal_p50": "Share of expected reports that arrived during taxi-in. Median across arrivals.",
    "signal_p50": "Taxi-out and taxi-in averaged: one figure for a typical ground movement.",
    "dep_continuity_p50": "Share of 30-second slices of the taxi-out holding at least one report.",
    "arr_continuity_p50": "Share of 30-second slices of the taxi-in holding at least one report.",
    "dep_continuity_p10": "The worst-covered tenth of departures, by the 30-second slice measure.",
    "dep_continuity_p90": "The best-covered tenth of departures, by the 30-second slice measure.",
    "arr_continuity_p10": "The worst-covered tenth of arrivals, by the 30-second slice measure.",
    "arr_continuity_p90": "The best-covered tenth of arrivals, by the 30-second slice measure.",
    "dep_max_gap_median_s": "Longest silence during a typical taxi-out. One big gap means a blind spot.",
    "arr_max_gap_median_s": "Longest silence during a typical taxi-in.",
    "dep_reach_p50": "How far back the first report lies, as a share of the taxi. Diagnostic only.",
    "arr_reach_p50": "How far forward the last report lies, as a share of the taxi-in. Diagnostic only.",
    "off_s_p50": "Minutes between the track starting and take-off. Negative is good.",
    "off_s_p10": "The earliest tenth: how far ahead of take-off tracking begins at best.",
    "off_s_p90": "The latest tenth: how much of the departure is missed at worst.",
    "land_s_p50": "Minutes between landing and the track ending. Positive is good.",
    "land_s_p10": "The tenth where tracking stops earliest after landing.",
    "land_s_p90": "The tenth where tracking runs longest after landing.",
    "dep_no_ground_pct": "Share of departures never heard while still on the ground.",
    "arr_no_ground_pct": "Share of arrivals whose track ends at or before landing.",
    "dep_full_capture_pct": "Share of departures where at least 95% of expected reports arrived.",
    "arr_full_capture_pct": "Share of arrivals where at least 95% of expected reports arrived.",
    "taxi_out_median_s": "How long a typical taxi-out takes here. Context for the coverage figures.",
    "taxi_in_median_s": "How long a typical taxi-in takes here. Context for the coverage figures.",
    # Side-neutral on purpose: `_quality_section` in `oac.page` shows both
    # dep and arr rows under one dep-named header, so a tip written for one
    # side would misdescribe the other's row.
    "clean_pct_dep": "Share of movements matched to exactly one track holding no other flight.",
    "clean_pct_arr": "Share of movements matched to exactly one track holding no other flight.",
    "fragmented_pct_dep": "Share of movements cut across several tracks, which understates their coverage.",
    "fragmented_pct_arr": "Share of movements cut across several tracks, which understates their coverage.",
    "merged_pct_dep": "Share of movements sharing a track with another flight, which is then lost.",
    "merged_pct_arr": "Share of movements sharing a track with another flight, which is then lost.",
    "tracking_err_pct": "Split and merged added together. High means coverage understated, not poor reception.",
    "coverage_index": "Share of movements seen, times how much of a typical ground movement arrives.",
    "rating": "Plain-language band over the coverage index. Hover a value for what that band means.",
}

EXPLAIN = {
    "n_movements": "Take-offs plus landings the reference data records here, "
                   "one flight contributing a movement at each end. The "
                   "reference is the Network Manager flight table, "
                   "independent of ADS-B. Where only one side is known, this "
                   "counts the side that is.",
    "n_gt": "The larger of the two sides. The ranking floor and nothing else: "
            "20 movements on one side, a stricter test than 20 across both.",
    "n_gt_dep": "Take-offs the reference data records here over the sampled "
                "days, counted against the flight's origin aerodrome.",
    "n_gt_arr": "Landings the reference data records here, counted against the "
                "flight's destination aerodrome.",
    "n_detected": "How many of those movements produced any ADS-B position "
                  "report at all, matched by airframe (24-bit ICAO address) "
                  "and by time, inside that flight's own airborne interval. "
                  "One matching report is enough to count as seen.",
    "n_detected_dep": "Take-offs with at least one matching position report. "
                      "See “Movements seen”.",
    "n_detected_arr": "Landings with at least one matching position report.",
    "detection_pct": "Movements seen divided by movements the reference data "
                     "records. **Read it as a floor, not a coverage figure**: "
                     "above 99% at four measured aerodromes in five, it "
                     "separates “invisible to the network” from "
                     "“seen, but only partly” and says nothing about how "
                     "much was tracked.\n\n"
                     "A flight counts as seen if one position report comes "
                     "from the same airframe, matched on the ICAO address, "
                     "and falls between its take-off and landing. That window "
                     "is the **airborne** one, which is why this says nothing "
                     "about ground coverage.",
    "detection_pct_dep": "As above, over departures only.",
    "detection_pct_arr": "As above, over arrivals only.",
    "measured_pct": "The share of this aerodrome's movements whose stand and "
                    "runway times come from the airport operator, rather "
                    "than being estimated. At or above 50% the aerodrome is "
                    "treated as measured; below it, only whether flights were "
                    "seen at all.",
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

    "dep_signal_p50": "The taxi-out is the interval between two measured "
                      "times: off-block, and take-off. The "
                      "feed delivers about one position report every 5 "
                      "seconds, so a taxi of *n* seconds should produce about "
                      "*n*/5 reports. We count how many arrived and divide by "
                      "how many were expected, then take the median across "
                      "this aerodrome's departures.\n\n"
                      "1.00 means the aircraft was tracked the whole way out. "
                      "0.10 means nine reports in ten never arrived.",
    "dep_signal_est": "The same received-over-expected count as the taxi-out "
                      "figure above, but over a window Network Manager "
                      "predicted rather than one the airport observed.\n\n"
                      "Shown only for aerodromes whose times are not "
                      "measured. Where they are, this cell is blank and the "
                      "measured figure above is what ranks them.",
    "arr_signal_p50": "The same computation over the taxi-in: the interval "
                      "between landing and in-block, "
                      "with reports counted against the same 5-second "
                      "expectation.",
    # Unused since 2026-08-29: the column was removed from the ranking table
    # because it duplicates coverage_index (r = 0.998). Kept in case the
    # aerodrome pages want the combined figure -- but note EXPLAIN below is
    # the framing that removal retracted.
    "signal_p50": "The average of the taxi-out and taxi-in figures, giving one "
                  "number for how much of a typical ground movement reaches "
                  "the network. Each side is a median over that aerodrome's "
                  "own movements first, so a single very good or very bad "
                  "flight cannot move it.",
    "dep_continuity_p50": "The taxi-out cut into 30-second slices; this "
                          "counts how many held **at least one** report, "
                          "regardless of how many were expected.\n\n"
                          "Read it against “received”: high here and low "
                          "there means a thin but unbroken stream, arriving "
                          "every half-minute but far short of what was "
                          "expected.",
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
                            "reports, and from the last report to take-off — "
                            "so a receiver that stops halfway is counted as "
                            "having a gap even though no two reports straddle "
                            "it. A large gap alongside otherwise good reception "
                            "points at one blind spot rather than weak coverage "
                            "throughout.",
    "arr_max_gap_median_s": "The same for taxi-in.",
    "dep_reach_p50": "How far back the track's **first** report lies, as a "
                     "fraction of the taxi: the time between that report and "
                     "take-off, divided by the taxi duration.\n\n"
                     "Disagrees with “received” in a revealing way: a single "
                     "report at the stand and nothing afterwards spans the "
                     "entire taxi and scores 1.00 here, where “received” "
                     "scores it near zero.",
    "arr_reach_p50": "The same on the arrival side, measured forward from "
                     "landing to the track's last report.",
    "off_s_p50": "The gap between when the track starts and when the aircraft "
                 "actually left the ground, in minutes, for a typical "
                 "departure. Computed as the track's first position report "
                 "minus the recorded take-off time.\n\n"
                 "**Negative is good**: the track began before take-off, so "
                 "the aircraft was already being followed on the ground. "
                 "Positive means part of the departure was never seen.",
    "off_s_p10": "The earliest tenth of departures — how far ahead of take-off "
                 "tracking begins when this aerodrome is at its best.",
    "off_s_p90": "The latest tenth — how much of the departure is missed in "
                 "the worst cases here.",
    "land_s_p50": "The gap between landing and the end of the track, in "
                  "minutes, for a typical arrival: the track's last position "
                  "report minus the recorded landing time.\n\n"
                  "**Positive is good**: the aircraft was still being tracked "
                  "while it taxied in. Negative means the track ended before "
                  "the aircraft was down.",
    "land_s_p10": "The worst tenth, where tracking stops earliest relative to "
                  "landing.",
    "land_s_p90": "The best tenth, where tracking continues longest after it.",
    "dep_no_ground_pct": "The share of departures whose track starts at or "
                         "after take-off — the aircraft was never heard while "
                         "it was on the ground at all.",
    "arr_no_ground_pct": "The share of arrivals whose track ends at or before "
                         "landing.",
    "dep_full_capture_pct": "The share of departures where at least 95% of the "
                            "expected reports arrived during taxi-out — "
                            "effectively complete coverage of the ground "
                            "movement.",
    "arr_full_capture_pct": "The same for taxi-in.",
    "taxi_out_median_s": "How long a typical taxi-out takes here, from off-block "
                         "to take-off. Context rather than a coverage figure: "
                         "the same three minutes of reception is most of a "
                         "short taxi and a fraction of a long one, which is "
                         "why coverage is expressed as a fraction and not as "
                         "a duration.",
    "taxi_in_median_s": "How long a typical taxi-in takes here, from landing "
                        "to in-block.",
    "clean_pct_dep": "The share of movements the track-building algorithm "
                     "matched to exactly one track that contains no other "
                     "flight. Position reports arrive as a continuous stream "
                     "per airframe with no notion of a flight, so they have to "
                     "be cut into flights first; this says how often that cut "
                     "was right here.",
    "clean_pct_arr": "As above, over arrivals.",
    "fragmented_pct_dep": "The share of movements broken across several "
                          "tracks. Recoverable — the flight is present, in "
                          "pieces — but coverage is measured against the "
                          "largest piece, so a split flight's coverage is "
                          "understated. Within the same aerodrome a split "
                          "departure's track starts a median 6.5 minutes later "
                          "than a clean one, which is the size of the "
                          "understatement.",
    "fragmented_pct_arr": "As above, over arrivals.",
    "merged_pct_dep": "The share of movements sharing a track with another "
                      "flight. Only one comes out of a merged track; the "
                      "other does not exist downstream. The survivor's own "
                      "coverage shows no consistent shift (median −0.009 "
                      "against clean flights): a completeness loss, not a "
                      "coverage one.",
    "merged_pct_arr": "As above, over arrivals.",
    "tracking_err_pct": "The share of this aerodrome's movements the "
                        "track-building step got wrong: split and merged "
                        "added together.\n\n"
                        "**Split** understates coverage, because only the "
                        "largest piece is scored. A split departure's track "
                        "starts a median **6.5 minutes later** than a clean "
                        "one, at 182 of 206 aerodromes.\n\n"
                        "**Merged** costs a whole flight: two share a track, "
                        "one survives, the other is absent downstream. No "
                        "measurable effect on the survivor (median −0.009, on "
                        "0.8% of movements).\n\n"
                        "So a high figure means coverage understated and "
                        "movements missing, not poor reception.",
    "coverage_index": "The share of movements seen at all, multiplied by the "
                      "share of a typical ground movement received (the "
                      "average of the taxi-out and taxi-in medians).\n\n"
                      "Read it as the expected share of one movement the "
                      "network captures. 1.00 is perfect; 0.00 means the "
                      "surface is invisible even where the aircraft is "
                      "tracked once airborne.\n\n"
                      "Left **blank**, never zero, where the ground figures "
                      "are unavailable. Falling back to detection alone would "
                      "rank an unmeasurable aerodrome as though it were well "
                      "covered.",
    "rating": "A band over the coverage index, so a long table can be scanned "
              "without reading three decimals on every row: **Excellent** at "
              "0.90 and above, **Good** from 0.60, **Partial** from 0.30, "
              "**Poor** from 0.05, and **None** below that.",
}


#: Columns whose label counts movements, and which therefore mean nothing
#: without the period they count over. The rankings and each aerodrome page
#: show one period at a time, so "Movements: 516" invites the reader to take it
#: as a rate, a total, or whatever they last read -- when it is 516 movements
#: across three sampled days of one June.
PERIOD_SCOPED = ("n_gt", "n_movements", "n_detected", "n_gt_dep", "n_gt_arr",
                 "n_detected_dep", "n_detected_arr")


#: Days each period samples. Named here because the movement-count headers
#: state it, and a reader who takes 516 movements for a June total is out by a
#: factor of ten. `tests/test_period_and_units.py` counts the distinct days in
#: the committed extracts and fails if this ever stops being true, so the
#: header cannot go quietly stale when the sample changes.
SAMPLE_DAYS = 3


def label(col: str, period: str = None) -> str:
    """Display name for a column, falling back to the raw name.

    `period` is appended to the movement counts and to nothing else. Adding it
    to every column would put the sample description on ICAO and on the rank.
    """
    name = LABELS.get(col, col)
    if period and col in PERIOD_SCOPED:
        return f"{name} {period} sample ({SAMPLE_DAYS} days)"
    return name


def explain(col: str) -> str:
    return EXPLAIN.get(col, "")


def rename(df, period: str = None):
    """Return `df` with display names as headers."""
    return df.rename(columns={c: label(c, period) for c in df.columns})


def tip(col: str) -> str:
    """The tooltip text for a column, or an empty string."""
    return TIPS.get(col, "")


def _tip_span(text: str, tip_text: str) -> str:
    """`text` wrapped so Bootstrap will show `tip_text` on hover or focus.

    `tabindex` is what makes it reachable without a mouse. Bootstrap opens a
    tooltip on focus as well as hover, so a keyboard user tabs to the heading
    and a touch user taps it; without the attribute a `<span>` takes neither.
    """
    return (f'<span data-bs-toggle="tooltip" tabindex="0" '
            f'title="{tip_text}">{text}</span>')


def tip_header(col: str, period: str = None) -> str:
    """The display name, carrying its tooltip.

    Columns with nothing to explain get a bare name. Wrapping them anyway
    would put a focus stop and an empty tooltip on `ICAO` and `#`.
    """
    name = label(col, period)
    t = tip(col)
    return _tip_span(name, t) if t else name


def tip_headers(df, period: str = None):
    """`df` with tooltip-carrying display names as headers.

    The display-path counterpart of `rename`. `rename` stays, and is what the
    CSV and XLSX downloads use: a `<span>` in a spreadsheet header is markup a
    reader has to look past, and the file has no Bootstrap to render it.
    """
    return df.rename(columns={c: tip_header(c, period) for c in df.columns})


#: Band name -> the sentence describing it, from `RATINGS`.
_RATING_TEXT = {name: description for _, name, description in RATINGS}


def rating_cell(band: str) -> str:
    """A rating word carrying its band's description on hover.

    Applied on the display path only. The downloads keep the bare word, so a
    spreadsheet column of ratings stays sortable and filterable.
    """
    text = _RATING_TEXT.get(band)
    return _tip_span(band, text) if text else band
