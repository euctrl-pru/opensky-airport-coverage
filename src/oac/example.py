"""One real flight, picked to show how a coverage figure is built.

The rankings page explains the metric in the abstract -- reports received over
reports expected -- and a reader asked for the arithmetic on a single flight
before the tables start. This picks that flight.

**Picked from the data, not written into the page.** A worked example with
numbers typed into the prose is a number that goes stale the next time the
pipeline runs, and nothing in the page would say so. The pick is deterministic
given a period's offsets table, so the example is stable between renders while
the data is, and moves with the data when it is not.
"""

import pandas as pd

__all__ = ["CADENCE_S", "example_flight"]

#: The feed's nominal reporting interval. A taxi of *n* seconds should produce
#: about *n* / CADENCE_S reports; the coverage figure is how many arrived over
#: how many were expected. Defined here rather than as a literal in the page,
#: which is where the "expected" count would otherwise disagree with the
#: pipeline that produced the received one.
CADENCE_S = 5


def example_flight(offsets: pd.DataFrame) -> dict:
    """Real numbers for one flight measured at both ends, or None.

    Both ends must be measured, because the example has to show the taxi-in as
    well as the taxi-out and only APDF bounds a taxi-in at all.

    The flight is chosen to be *illustrative* rather than typical: a taxi-out
    somewhere between a third and nine tenths received, so the arithmetic
    produces a number the reader can see is neither nothing nor everything. A
    flight at 1.000 would demonstrate the formula without demonstrating that it
    can be anything else.

    Ties are broken on `flight_key`, which is a hash and therefore arbitrary --
    but arbitrary and *fixed*, which is what stops the example changing
    identity on a re-render that did not change the data.
    """
    d = offsets
    need = ["dep_measured", "arr_measured", "aobt", "t_off", "t_land", "aibt",
            "dep_n_samples", "arr_n_samples", "gt_adep", "gt_ades",
            "flight_key"]
    if any(c not in d.columns for c in need):
        return None

    d = d[d["dep_measured"].fillna(False) & d["arr_measured"].fillna(False)]
    d = d.dropna(subset=["aobt", "t_off", "t_land", "aibt",
                         "dep_n_samples", "arr_n_samples"])
    if d.empty:
        return None

    d = d.assign(
        taxi_out_s=(d["t_off"] - d["aobt"]).dt.total_seconds(),
        taxi_in_s=(d["aibt"] - d["t_land"]).dt.total_seconds(),
    )
    # A taxi has to be long enough to have a shape and short enough to draw.
    d = d[d["taxi_out_s"].between(300, 1200) & d["taxi_in_s"].between(180, 900)]
    if d.empty:
        return None

    d = d.assign(
        dep_signal=d["dep_n_samples"] / (d["taxi_out_s"] / CADENCE_S),
        arr_signal=d["arr_n_samples"] / (d["taxi_in_s"] / CADENCE_S),
    )
    # Partly received on the departure side: the case worth showing.
    pick = d[d["dep_signal"].between(0.33, 0.90)]
    if pick.empty:
        return None
    r = pick.sort_values("flight_key").iloc[0]

    return {
        "adep": r["gt_adep"], "ades": r["gt_ades"],
        "aobt": r["aobt"], "t_off": r["t_off"],
        "t_land": r["t_land"], "aibt": r["aibt"],
        "taxi_out_s": float(r["taxi_out_s"]),
        "taxi_in_s": float(r["taxi_in_s"]),
        "dep_expected": float(r["taxi_out_s"]) / CADENCE_S,
        "arr_expected": float(r["taxi_in_s"]) / CADENCE_S,
        "dep_received": float(r["dep_n_samples"]),
        "arr_received": float(r["arr_n_samples"]),
        "dep_signal": float(r["dep_signal"]),
        "arr_signal": float(r["arr_signal"]),
    }
