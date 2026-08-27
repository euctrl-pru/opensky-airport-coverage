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
