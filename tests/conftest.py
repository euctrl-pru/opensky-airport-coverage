import os
import sys

import pytest


@pytest.fixture(scope="session")
def spark():
    """Local Spark session. Mirrors opdi's own conftest -- no cluster.

    `PYSPARK_PYTHON` is set explicitly and is not optional here. A Spark worker
    resolves `python3` from PATH, which on this machine is 3.13, while the venv
    driver is 3.10 -- and PySpark refuses to run across different minor
    versions. Without this the failure surfaces as a Py4J stack trace from a
    `.parquet()` write, which points at everything except the cause.
    """
    pytest.importorskip("pyspark")
    from pyspark.sql import SparkSession

    os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
    os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)

    s = (
        SparkSession.builder.master("local[2]")
        .appName("oac-tests")
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.session.timeZone", "UTC")
        .getOrCreate()
    )
    s.sparkContext.setLogLevel("ERROR")
    yield s
    s.stop()


import numpy as np
import pandas as pd

#: One aerodrome's stats row, complete enough that every section of
#: `build_page` renders its prose rather than its "no data" branch.
_PAGE_STATS = pd.Series({
    "n_gt_dep": 500, "n_gt_arr": 480, "n_detected_dep": 498,
    "n_detected_arr": 470, "detection_pct_dep": 99.6, "detection_pct_arr": 97.9,
    "coverage_index": 0.71, "dep_signal_p50": 0.74, "arr_signal_p50": 0.68,
    "off_s_p50": -320.0, "land_s_p50": 210.0,
    "clean_pct_dep": 91.0, "fragmented_pct_dep": 8.0, "merged_pct_dep": 1.0,
    "clean_pct_arr": 90.0, "fragmented_pct_arr": 9.0, "merged_pct_arr": 1.0,
    "n_capture_excluded_dep": 3, "taxi_out_median_s": 700.0,
    "taxi_in_median_s": 300.0,
})


@pytest.fixture
def aerodrome_page():
    """Build a complete aerodrome page for a tier. Returns the markdown."""
    from oac.page import build_page

    rng = np.random.default_rng(0)

    def frame(off_col, sig_col):
        return pd.DataFrame({off_col: rng.normal(-300, 200, 50),
                             sig_col: rng.uniform(0, 1, 50)})

    def build(tier="A"):
        frames = {"dep": {p: frame("off_s", "dep_signal")
                          for p in ("2026", "2025")},
                  "arr": {p: frame("land_s", "arr_signal")
                          for p in ("2026", "2025")}}
        figs = {"dep_hist": "d.svg", "arr_hist": "a.svg",
                "dep_ecdf": "de.svg", "arr_ecdf": "ae.svg",
                "dep_hist_overflow": {"2026": (2, 1)},
                "map_html": "<div>map</div>"}
        ranking = pd.DataFrame([dict(_PAGE_STATS)] * 3)
        stats = {"2026": _PAGE_STATS, "2025": _PAGE_STATS}
        return build_page(tier, stats, frames, ranking, "2026", figs)

    return build
