"""The Coverage Index and the two ranking tables. Pure pandas."""

import numpy as np
import pandas as pd

from oac.aggregate import MIN_N

__all__ = ["coverage_index", "rank_tiers"]


def coverage_index(row) -> float:
    """`detection_rate * mean(dep_signal_p50, arr_signal_p50)`.

    Read as the expected share of a movement actually observed: the chance the
    flight is seen at all, times how much of its ground phase is *continuously*
    observed when it is. Both terms are fractions in `0..1`.

    This replaced a reach-based index. Reach measured only how far back the
    outermost sample lay, so one state vector at push-back scored a perfect
    1.000; every number this function produces therefore differs from the
    reach-based ones, and the site says so rather than renumbering quietly.

    Returns NaN when neither capture term exists. A Tier B aerodrome has no
    AIBT and **must not be given a fabricated capture of any value, including
    zero** -- zero would rank it below every measured aerodrome for a reason
    that is not about coverage at all. Tier B ranks on detection alone, in its
    own table.

    Accepts a dict or a Series, so a test can state a row inline.
    """
    # **Signal, never reach and never bin occupancy.** No fallback: reach
    # standing in would restore the defect signal was added to fix, and bin
    # occupancy standing in would score one report out of an expected six as a
    # full slice. Both would do it for exactly the aerodromes where signal
    # could not be measured.
    # **Both terms are required.** The departure figure is now computed
    # everywhere -- NM supplies an off-block time and a taxi duration even
    # where APDF never saw the movement -- but that window is modelled, and its
    # duration differs from the measured one by an IQR of 300 s. The arrival
    # figure has no such fallback: no in-block time exists outside APDF.
    #
    # So requiring both is what keeps the index a single comparable quantity.
    # Accepting whichever term happens to exist would put a measured figure and
    # a modelled one in the same column with nothing distinguishing them, and
    # an aerodrome with no measured times at all would score 1.000.
    dep, arr = row["dep_signal_p50"], row["arr_signal_p50"]
    if dep is None or arr is None or pd.isna(dep) or pd.isna(arr):
        return np.nan
    return float(row["detection_pct"]) / 100.0 * float(np.mean([dep, arr]))


def rank_tiers(tbl: pd.DataFrame):
    """`(measured, all_aerodromes)`, each sorted and given a 1-based `rank`.

    Two tables answering different questions, deliberately not one:

    * **measured** -- aerodromes whose real stand and runway times are
      recorded, so how much of each ground movement was received can be
      computed. Ranked on `coverage_index`.
    * **all aerodromes** -- every aerodrome above the movement threshold,
      *including* the measured ones. Ranked on `detection_pct`, the one
      question answerable everywhere.

    Combining them would imply the two rankings measure the same thing.
    """
    t = tbl.copy()
    t["coverage_index"] = t.apply(coverage_index, axis=1)
    t = t[t["n_gt"] >= MIN_N]
    # Whether this aerodrome also appears in the measured table, so the
    # all-aerodromes ranking can be cross-referenced without flipping back.
    t["measured"] = np.where(t["t_source"] == "apdf", "yes", "no")

    # Ties on the index are broken by detection, and they are not rare: an
    # aerodrome with no ground reception at all scores exactly 0.000 however
    # well it does otherwise, and on the 2025 sample a double-digit group does.
    # Naples detects 99.7% of its movements and Gran Canaria 62%; both capture
    # no ground phase, and ranking them equal would discard the one thing that
    # still separates them.
    a = t[t["t_source"] == "apdf"].sort_values(
        ["coverage_index", "detection_pct"], ascending=False, na_position="last"
    )
    # **The second table is every aerodrome, not the complement of the first.**
    # Detection -- was the flight seen at all -- is computable everywhere,
    # including where the milestones are measured. Excluding those left no
    # complete ranking of detection anywhere on the site, and made an
    # aerodrome vanish from one table by appearing in the other.
    #
    # Ties are broken by sample size: with no ground-coverage term available, a
    # 100% rate over 800 movements is a stronger statement than over 20.
    b = t.sort_values(
        ["detection_pct", "n_gt"], ascending=False, na_position="last"
    )
    out = []
    for d in (a, b):
        d = d.reset_index(drop=True)
        d.insert(0, "rank", range(1, len(d) + 1))
        out.append(d)
    return out[0], out[1]
