"""The Coverage Index and the two ranking tables. Pure pandas."""

import numpy as np
import pandas as pd

from oac.aggregate import MIN_N

__all__ = ["coverage_index", "rank_tiers"]


def coverage_index(row) -> float:
    """`detection_rate * mean(dep_capture_p50, arr_capture_p50)`.

    Read as the expected share of a movement actually captured: the chance the
    flight is seen at all, times how much of its ground phase is seen when it
    is. Both terms are fractions in `0..1`, so the product is too.

    Returns NaN when neither capture term exists. A Tier B aerodrome has no
    AIBT and **must not be given a fabricated capture of any value, including
    zero** -- zero would rank it below every measured aerodrome for a reason
    that is not about coverage at all. Tier B ranks on detection alone, in its
    own table.

    Accepts a dict or a Series, so a test can state a row inline.
    """
    both = [
        v for v in (row["dep_capture_p50"], row["arr_capture_p50"])
        if v is not None and not pd.isna(v)
    ]
    if not both:
        return np.nan
    return float(row["detection_pct"]) / 100.0 * float(np.mean(both))


def rank_tiers(tbl: pd.DataFrame):
    """`(tier_a, tier_b)`, each filtered, sorted and given a 1-based `rank`.

    **Never interleaved.** Tier A's milestones are measured and Tier B's are
    inferred, and Tier B has no capture term at all -- so the two do not
    measure the same thing and a combined leaderboard would imply they do.
    Tier A ranks on `coverage_index`, Tier B on `detection_pct`.
    """
    t = tbl.copy()
    t["coverage_index"] = t.apply(coverage_index, axis=1)
    t = t[t["n_gt"] >= MIN_N]

    a = t[t["t_source"] == "apdf"].sort_values(
        "coverage_index", ascending=False, na_position="last"
    )
    b = t[t["t_source"] != "apdf"].sort_values(
        "detection_pct", ascending=False, na_position="last"
    )
    out = []
    for d in (a, b):
        d = d.reset_index(drop=True)
        d.insert(0, "rank", range(1, len(d) + 1))
        out.append(d)
    return out[0], out[1]
