"""The about page may not claim a filter the committed figures predate.

`oac.positions` landed as a code change. Every extract produced before it
still counts reports carrying no position, and the site deploys on every push
to main -- so between the merge and the re-run the page would have asserted a
correction that none of its numbers reflected.
"""

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location(
    "oac_site_data", REPO / "site" / "_data.py")
_data = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_data)


@pytest.fixture
def fake_data(tmp_path, monkeypatch):
    """A DATA directory whose periods and manifest the test controls."""
    def build(entries):
        for period in entries:
            (tmp_path / f"flight_offsets_{period}.parquet").write_bytes(b"")
        manifest = {
            f"flight_offsets_{p}.parquet": {"notes": note}
            for p, note in entries.items() if note is not None
        }
        (tmp_path / "_manifest.json").write_text(json.dumps(manifest))
        monkeypatch.setattr(_data, "DATA", tmp_path)
        _data.manifest.cache_clear() if hasattr(_data.manifest, "cache_clear") \
            else None
        return _data
    return build


#: A note as `run_offsets` writes it, built from the same constant the site
#: looks for -- a hand-typed copy here would pass while the real pair drifted.
FILTERED = (f"arm=recommended. {_data.POSITION_FILTER_MARK} "
            "140,000,000 of 153,407,259 rows kept (91.3%).")
OLD = "arm=recommended, days=[...]. Ground occupancy binned at 30 s."


def test_an_extract_produced_before_the_filter_is_reported(fake_data):
    d = fake_data({"2026": OLD})
    assert d.periods_without_filter() == ["2026"]


def test_a_regenerated_extract_clears_the_warning(fake_data):
    d = fake_data({"2026": FILTERED})
    assert d.periods_without_filter() == []


def test_only_the_periods_that_predate_it_are_named(fake_data):
    d = fake_data({"2026": FILTERED, "2025": OLD, "2024": OLD})
    assert d.periods_without_filter() == ["2025", "2024"]


def test_an_unverified_extract_counts_as_unfiltered(fake_data):
    """No manifest entry cannot evidence the filter.

    Treating silence as compliance would restore the overclaim in exactly the
    case where there is least reason to trust the file.
    """
    d = fake_data({"2026": None})
    assert d.periods_without_filter() == ["2026"]


@pytest.mark.parametrize("script", ["run_offsets.py", "run_h3.py",
                                    "run_examples.py"])
def test_every_script_stamps_the_shared_note_rather_than_its_own(script):
    """The two ends of this match are joined by an import, not by wording.

    `_data` decides whether the about page may state the filter by looking for
    this note in the manifest. If a script wrote its own phrasing, rewording
    either end would stop the warning firing -- a failure in the safe-looking
    direction, leaving a clean page over figures that predate the filter.
    """
    src = (REPO / "scripts" / script).read_text()
    assert "POSITION_FILTER_NOTE" in src, f"{script} does not import the note"
    assert "{POSITION_FILTER_NOTE}" in src, f"{script} does not write the note"


def test_the_site_reads_the_note_from_the_module_that_writes_it():
    assert _data.POSITION_FILTER_MARK == _data.POSITION_FILTER_NOTE


def test_reading_the_note_needs_no_pyspark():
    """The site render must never import pyspark; CI installs it nowhere.

    `oac.positions` holds the filter and imports pyspark, so the note lives in
    `oac.provenance` instead. If it ever moves back, the whole site render
    dies at import rather than at the one page that uses it.
    """
    import os
    import subprocess
    import sys

    # This worktree's src, ahead of whatever `pip install -e .` resolved to --
    # that points at the main checkout and would test the wrong file.
    env = dict(os.environ, PYTHONPATH=str(REPO / "src"))
    out = subprocess.run(
        [sys.executable, "-c",
         "import sys; from oac.provenance import POSITION_FILTER_NOTE;"
         "assert 'pyspark' not in sys.modules, 'pyspark reached the site path';"
         "print('ok')"],
        capture_output=True, text=True, cwd=REPO, env=env)
    assert out.returncode == 0, out.stderr
    assert "ok" in out.stdout


def test_the_about_page_asks_rather_than_asserts():
    text = (REPO / "site" / "about.qmd").read_text()
    assert "periods_without_filter" in text, (
        "the about page states the filter unconditionally"
    )
    assert "Not yet in these figures" in text
