"""The worked example on the rankings page: real, illustrative, and stable.

The example exists to show a reader the arithmetic on one flight before the
tables start. Three things have to hold or it teaches the wrong lesson: the
numbers must be the flight's own, the share must be partial, and the same
data must pick the same flight twice.
"""

import datetime as dt

import pandas as pd
import pytest

from oac.example import CADENCE_S, example_flight

T = dt.datetime


def _flight(key, adep="EBBR", ades="EGLL", taxi_out_s=600, taxi_in_s=300,
            dep_received=80, arr_received=60, **over):
    off = T(2026, 6, 5, 10, 15)
    land = T(2026, 6, 5, 11, 5)
    row = dict(
        flight_key=key, gt_adep=adep, gt_ades=ades,
        dep_measured=True, arr_measured=True,
        aobt=off - dt.timedelta(seconds=taxi_out_s), t_off=off,
        t_land=land, aibt=land + dt.timedelta(seconds=taxi_in_s),
        dep_n_samples=float(dep_received), arr_n_samples=float(arr_received),
    )
    row.update(over)
    return row


def _frame(rows):
    return pd.DataFrame(rows)


def test_the_arithmetic_is_the_flights_own_numbers():
    """expected = taxi / cadence, share = received / expected. Nothing else."""
    ex = example_flight(_frame([_flight("a", taxi_out_s=600, dep_received=80)]))
    assert ex is not None
    assert ex["taxi_out_s"] == 600
    assert ex["dep_expected"] == 600 / CADENCE_S       # 120
    assert ex["dep_received"] == 80
    assert ex["dep_signal"] == pytest.approx(80 / 120)


def test_a_fully_received_flight_is_not_chosen_to_illustrate_a_share():
    """A flight at 1.000 shows the formula without showing it can vary.

    It demonstrates that received/expected divides, and leaves the reader no
    wiser about what a coverage figure below one looks like -- which is the
    entire subject of the page the example introduces.
    """
    perfect = _flight("a", taxi_out_s=600, dep_received=120)   # exactly 1.000
    partial = _flight("b", taxi_out_s=600, dep_received=80)    # 0.667
    ex = example_flight(_frame([perfect, partial]))
    assert ex["dep_signal"] == pytest.approx(80 / 120)


def test_an_unmeasured_end_is_never_used():
    """Only APDF bounds a taxi-in, so an estimated flight cannot show one."""
    est = _flight("a", arr_measured=False)
    assert example_flight(_frame([est])) is None


def test_the_pick_is_stable_across_row_order():
    """A re-render that changed no data must not change the example.

    The frames come off parquet, whose row order is not contractual; a pick
    that depended on it would swap the example between renders and make the
    page look edited when it was not.
    """
    rows = [_flight("c", dep_received=70), _flight("a", dep_received=75),
            _flight("b", dep_received=80)]
    first = example_flight(_frame(rows))
    second = example_flight(_frame(list(reversed(rows))))
    assert first["dep_signal"] == second["dep_signal"]


def test_no_candidate_returns_none_rather_than_a_misleading_flight():
    """The page skips the section; it does not print a flight at 0.000."""
    hopeless = _flight("a", dep_received=0, arr_received=0)
    assert example_flight(_frame([hopeless])) is None


def test_the_committed_data_still_yields_an_example():
    """Guards the page: the section renders nothing if this ever returns None."""
    from pathlib import Path

    data = Path(__file__).resolve().parent.parent / "data"
    offsets = sorted(data.glob("flight_offsets_*.parquet"))
    if not offsets:
        pytest.skip("no committed offsets")
    ex = example_flight(pd.read_parquet(offsets[-1]))
    assert ex is not None, "the rankings page would render no worked example"
    assert 0.33 <= ex["dep_signal"] <= 0.90
    assert ex["dep_expected"] == pytest.approx(ex["taxi_out_s"] / CADENCE_S)
