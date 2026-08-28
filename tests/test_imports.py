import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_bootstrap_makes_opdi_importable():
    from oac._opdi import bootstrap
    bootstrap()
    import track_score
    import track_truth
    from opdi.pipeline.segmentation.methods import ARMS

    assert "recommended" in ARMS
    assert hasattr(track_score, "boundary_offsets")
    assert hasattr(track_truth, "load_flight_intervals")


def test_aggregate_does_not_import_spark_or_opdi():
    """The site renders in GitHub Actions, which has neither.

    Asserted in a subprocess with a clean interpreter: importing in-process
    would pass simply because an earlier test already imported pyspark.
    """
    code = (
        "import sys; sys.path.insert(0, %r);"
        "import oac.aggregate, oac.rank;"
        "bad = [m for m in sys.modules if m in ('pyspark', 'opdi')"
        " or m.startswith('pyspark.') or m.startswith('opdi.')];"
        "assert not bad, bad; print('clean')" % str(REPO / "src")
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert "clean" in out.stdout


def test_the_site_path_has_every_dependency_it_needs():
    """CI installs `pip install -e .` only -- no `cluster` extra.

    `h3` was reaching the local environment as a transitive of `h3-pyspark`,
    which lives in that extra. The render worked here and would have failed on
    the first push. Asserted by importing what `gen_pages` imports, in a clean
    subprocess, with only the declared main dependencies on the path.
    """
    code = (
        "import sys; sys.path.insert(0, %r); sys.path.insert(0, %r);"
        "import h3, matplotlib, pandas, numpy;"
        "matplotlib.use('Agg');"
        "import _charts;"
        "assert hasattr(_charts, 'h3_map');"
        "assert h3.__version__.startswith('3.'), h3.__version__;"
        "print('ok')" % (str(REPO / "src"), str(REPO / "site"))
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert "ok" in out.stdout
