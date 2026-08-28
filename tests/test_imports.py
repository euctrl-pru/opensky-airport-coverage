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


def test_every_site_module_imports_with_only_the_declared_dependencies():
    """CI installs `pip install -e .` -- no `cluster` extra, no local leftovers.

    This has now bitten twice. `h3` reached the local environment as a
    transitive of `h3-pyspark`, and `plotly` because I had pip-installed it by
    hand; both rendered fine here and failed on the runner. The earlier version
    of this test listed the imports it expected, so it only caught what I
    remembered to list -- and `plotly` was imported lazily inside a function,
    which no import-time check would have caught anyway.

    So: import **every** module under `site/`, in a clean subprocess, and let
    any undeclared dependency raise. The modules keep their imports at the top
    for exactly this reason.
    """
    site = REPO / "site"
    mods = sorted(p.stem for p in site.glob("*.py"))
    assert "_maps" in mods and "_charts" in mods, mods
    code = (
        "import sys; sys.path.insert(0, %r); sys.path.insert(0, %r);"
        "import matplotlib; matplotlib.use('Agg');"
        "import importlib;"
        "[importlib.import_module(m) for m in %r];"
        "print('ok')" % (str(REPO / "src"), str(site), mods)
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.returncode == 0, (
        "a site module needs something that is not a declared dependency:\n"
        + out.stderr
    )
    assert "ok" in out.stdout


def test_the_map_builder_runs_without_the_cluster_extra():
    """Importing is not enough when the failure is inside a call.

    `plotly` was imported lazily, so the module imported cleanly and the build
    died on the first aerodrome. This exercises the function itself.
    """
    code = (
        "import sys; sys.path.insert(0, %r); sys.path.insert(0, %r);"
        "import matplotlib; matplotlib.use('Agg');"
        "import pandas as pd, h3, _maps;"
        "c = h3.geo_to_h3(50.9014, 4.4844, 11);"
        "df = pd.DataFrame({'h3': [c], 'layer': ['ground'], 'n': [10]});"
        "html = _maps.coverage_map(df);"
        "assert html and 'carto-positron' in html;"
        "print('ok')" % (str(REPO / "src"), str(REPO / "site"))
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert "ok" in out.stdout


def _qmd_imports(path: Path) -> list:
    """Top-level import statements from the `{python}` chunks of a `.qmd`."""
    lines, inside, out = path.read_text().splitlines(), False, []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            inside = stripped.startswith("```{python}")
            continue
        if inside and (line.startswith("import ") or line.startswith("from ")):
            out.append(line)
    return out


def test_every_qmd_imports_with_only_the_declared_dependencies():
    """The same check as above, for the `.qmd` files themselves.

    This is the hole the third failure came through. The test above globs
    `site/*.py`, so it saw `_charts`, `_data` and `_maps` and never looked at
    the pages that import them -- and `index.qmd` had picked up
    `from oac.truth import BBOX`, which imports pyspark for a tuple of four
    floats. Everything imported fine locally, where the `cluster` extra is
    installed, and the runner died on the first cell of the render.

    Quarto executes these chunks in a plain Jupyter kernel, so an import
    statement in a `.qmd` is exactly as much of a dependency declaration as
    one in a module, and gets checked the same way.
    """
    qmds = sorted(REPO.joinpath("site").rglob("*.qmd"))
    assert any(p.name == "index.qmd" for p in qmds), qmds
    stmts = []
    for p in qmds:
        stmts += _qmd_imports(p)
    assert any("_maps" in s for s in stmts), "no chunk imports found -- parser broken"

    body = "\n".join(stmts)
    code = (
        "import sys; sys.path.insert(0, %r); sys.path.insert(0, %r);"
        "import matplotlib; matplotlib.use('Agg')\n"
        "%s\n"
        "bad = [m for m in sys.modules if m in ('pyspark', 'opdi')"
        " or m.startswith('pyspark.') or m.startswith('opdi.')]\n"
        "assert not bad, bad\n"
        "print('ok')" % (str(REPO / "src"), str(REPO / "site"), body)
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.returncode == 0, (
        "a .qmd imports something CI will not have:\n" + out.stderr
    )
    assert "ok" in out.stdout
