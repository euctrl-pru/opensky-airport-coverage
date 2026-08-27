# ADS-B Airport Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure OpenSky ADS-B coverage per aerodrome from track boundary error, and publish it as a static Quarto site on GitHub Pages.

**Architecture:** A Spark job on the OSN cluster produces one row per ground-truth flight (signed boundary offsets, block times, aerodrome keys, match class). That table is committed to this repo, a few MB. Everything after it — aggregation, ranking, charts, pages — is pure pandas and renders offline, so GitHub Actions can rebuild Pages with no credentials.

**Tech Stack:** Python 3.10, PySpark (cluster only), pandas, Quarto with the Python engine, matplotlib, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-27-airport-coverage-design.md`

## Global Constraints

- **Sign conventions, stated once and never re-derived.** `off_s = trk_start − ATOT` (negative is good: track began before wheels-off). `land_s = trk_end − ALDT` (positive is good: track ran past touchdown).
- **`track_extents` comes from the unfiltered assignment table, never from `matched`.** `overlap_join` clips rows to `[t_off, t_land]`; extents taken after it make boundary error one-sided and score a merged track near zero.
- **`oac/aggregate.py`, `oac/rank.py` and everything under `site/` must not import `pyspark` or `opdi`.** GitHub Actions has neither. This is enforced by a test.
- **S3 discipline:** the `eurocontrol` bucket measured **76.99 GB on 2026-08-27**, against a ~100 GB quota — roughly **23 GB free**, not the 3.11 GB `DATASETS.md` records from 2026-08-23. The symposium project shrank from 42.81 GB to 35.37 GB and research prefixes were cleaned. That headroom is what makes Phase 0 possible; re-measure before relying on it. One assignment table (~0.31 GB) exists at a time; deletion runs on the failure path as well as the success path; every deleted key is checked against this run's own prefix first.
- **Units:** seconds for time, fractions in `0..1` for capture, percentages `0..100` for `*_pct`. The unit is in the column name.
- **Never mutate a published version string.** `FLIGHT_LIST_VERSION` is `v5.0.0`, deliberately one string covering the whole 2026-08 change set.
- **Tier B threshold:** an aerodrome qualifies when `max(n_dep, n_arr) >= 20` in at least one period. Stated once, referenced everywhere.
- **Sample: three periods, same three days of the same month, three years running.** `2026` = 2026-06-05/06/07 (Phase 0 builds it), `2025` = 2025-06-05/06/07, months `["202506"]`, tracks `s3a://eurocontrol/opdi/osn_tracks_clean`, `2024` = 2024-06-05/06/07, months `["202406"]`, tracks `s3a://eurocontrol/opdi/research/tracks_clean`.
- **The latest period is the report.** Every ranking, every headline number and every page header is the newest period. Earlier periods appear only as comparison columns and as second traces on a distribution chart. A reader must never have to work out which year a ranking is from.
- **Commits:** no `Co-Authored-By` trailer, no "generated with" line. The message describes the change only.

---

# Phase 0 — A recent period

The two existing samples are June 2025 and June 2024. Today is 2026-08-27, so
the newest coverage number the study could otherwise publish is **fourteen
months old**, and a coverage map is a claim about the receiver network *now*.

**The month is 2026-06, and the days are the 5th, 6th and 7th** — the same three
days of the same month, three years running. That is not conservatism: reception
has a seasonal component (foliage, propagation, traffic mix, and the summer
schedule itself), so a June-to-June comparison isolates network growth while a
June-to-February one confounds it with the season. June 2026 is also about three
months back, which clears APDF's delivery lag; August 2026 would not.

**This phase is blocked on one thing only the user can do**: PRISME runs on the
work laptop. Everything after the extract is scriptable here.

### Task 0a: Extract the ground truth (user action)

- [ ] **Step 1: On the work laptop, in the `opensky-airport-coverage` checkout**

```bash
Rscript scripts/fetch_reference.R 2026-06 --days 05,06,07
```

Writes `../opdi/reference/apdf_202606.parquet` and `flights_202606.parquet`, then
runs four study-specific validations. Each corresponds to something that, if
wrong, yields a complete and plausible site that is quietly false:

1. **Block-time completeness** — `BLOCK_TIME_UTC` is the denominator of every
   capture fraction. Prior months run at 0.02% null; above 5% and Tier A is thin.
2. **Ground-phase sign** — `AOBT >= ATOT` or `AIBT <= ALDT` is bad reference
   data, excluded rather than clipped. A high rate stops being a footnote.
3. **Per-aerodrome sample sizes** — the total can look fine while no individual
   aerodrome clears `MIN_N`. Earlier samples cleared 94 Tier A aerodromes.
4. **`AIRCRAFT_ADDRESS` completeness** — it *is* `icao24` and the only join key
   to ADS-B. Missing means "unmatched", which is indistinguishable in the output
   from genuinely absent coverage.

- [ ] **Step 2: Commit the extracts under git-lfs and push**

The script prints the exact commands, including the `git cat-file` check that
the parquet went in as an LFS pointer rather than a blob, and the two
`reference/MANIFEST.md` rows to add.

- [ ] **Step 3: Report the validation output**

Paste the four validation blocks back. If Tier A clears fewer than ~90
aerodromes or block times are above 1% null, stop — the month is weaker than the
existing samples and the choice of month should be revisited before spending
cluster time.

### Task 0b: Mirror the reference to S3

- [ ] **Step 1: Pull opdi on the cluster and mirror**

```bash
cd /home/jupyter/work/opdi-workspace/opdi
git pull
.venv310/bin/python benchmarks/mirror_reference.py --include '*_202606.parquet' --dry-run
.venv310/bin/python benchmarks/mirror_reference.py --include '*_202606.parquet'
```

The dry run first is not ceremony: `mirror_reference.py` checks for LFS pointers,
and uploading a 130-byte pointer file instead of a 300 MB parquet produces a
ground-truth table with zero rows and no error anywhere.

### Task 0c: Ingest and build tracks for 2026-06-05/07

**Files:**
- Modify: `<opdi>/benchmarks/track_methods.py:PERIODS` (add the `2026` entry)
- Modify: `<opdi>/benchmarks/DATASETS.md` (correct the stale bucket figure)

- [ ] **Step 1: Re-measure the bucket before writing anything**

```bash
cd /home/jupyter/work/opdi-workspace/opdi
.venv310/bin/python -c "
import sys; sys.path.insert(0,'src'); sys.path.insert(0,'benchmarks')
import osn_sample; osn_sample.load_dotenv()
import track_methods as tm
s3 = tm.s3_client()
print('total %.2f GB, free %.2f GB' % (tm.bucket_total_gb(s3), 100 - tm.bucket_total_gb(s3)))
"
```

Expected: around 77 GB total, 23 GB free. **A 3-day track build is ~10 GB and
the raw ingest is more**, so if free space is under 25 GB, delete
`opdi/research/tracks/` (11.93 GB, regenerable) before starting — it belongs to
the finished V1–V3 studies.

- [ ] **Step 2: Ingest state vectors for the three days**

Use the pipeline's own ingestion, filtered to the Europe bbox and decimated to
5 s at read time — never persist the raw global 1 s feed.

```bash
.venv310/bin/python benchmarks/osn_sample.py --days 2026-06-05 2026-06-06 2026-06-07
```

Check the flags this script actually exposes before running; if the day
arguments differ, follow its `--help` rather than this line.

- [ ] **Step 3: Build and clean tracks, then delete the intermediate**

```bash
.venv310/bin/python benchmarks/clean_tracks.py --period 2026
```

Writes `s3a://eurocontrol/opdi/research/tracks_clean_2026`. Delete the uncleaned
intermediate as soon as the clean table is verified — two 10 GB tables at once is
most of the headroom.

- [ ] **Step 4: Register the period**

```python
    "2026": {
        "months": ["202606"],
        "days": ["2026-06-05", "2026-06-06", "2026-06-07"],
        "tracks": "s3a://eurocontrol/opdi/research/tracks_clean_2026",
    },
```

- [ ] **Step 5: Correct the stale bucket figure in `DATASETS.md`**

The file records 96.89 GB with 3.11 GB free as of 2026-08-23. Measured
2026-08-27 it is 76.99 GB, with the symposium prefix down from 42.81 GB to
35.37 GB. Record the new measurement and the date, and keep the old one beside
it — the point of the section is that the number moves, so replacing it silently
would remove the very warning it exists to give.

```bash
cd /home/jupyter/work/opdi-workspace/opdi
git add benchmarks/track_methods.py benchmarks/DATASETS.md
git commit -m "Add the 2026-06 period and re-measure the bucket"
```

- [ ] **Step 6: Run the offsets job for the new period**

```bash
cd ../opensky-airport-coverage
OPDI_REPO=../opdi .venv/bin/python scripts/run_offsets.py --period 2026
```

Then the same sanity checks Task 6 Step 5 lists — `land_s` p10 positive,
`clean_pct` near 0.91, `gt_adep` in the hundreds.

---

# Phase 1 — Merge `track-construction-v1` into `opdi` main

Nothing in this repo works until the A8 segmentation, `track_truth.py` and `track_score.py` are on `opdi` main. Do this first and completely.

### Task 1: Merge main into the branch and resolve the version conflict

**Files:**
- Modify: `<opdi>/src/opdi/pipeline/flights.py` (conflict at `FLIGHT_LIST_VERSION`)
- Work in: `/home/jupyter/work/opdi-workspace/opdi/.claude/worktrees/track-construction-v1`

**Interfaces:**
- Consumes: nothing.
- Produces: branch `track-construction-v1` containing every commit of `opdi` main, full test suite green.

**Background the implementer needs.** The branch is 49 commits ahead of main and 30 behind. There is exactly one content conflict, in `src/opdi/pipeline/flights.py`, and it is a *semantic* conflict wearing a textual disguise: both sides bump `FLIGHT_LIST_VERSION` from `v4.0.0` to `v5.0.0`, for different reasons. Main bumps it for the field-elevation datum change; the branch bumps it for the callsign-labelling change. Main's own comment at line 71 says `v5.0.0` "covers the 2026-08 change set, and it is one string for the whole" of it. Both changes are 2026-08 and neither has been published.

**Resolution: keep `v5.0.0`, and keep both rationales in the comment block.** Do not invent `v6.0.0` — that would split one unreleased change set across two version strings and contradict main's stated intent.

- [ ] **Step 1: Confirm the starting state**

```bash
cd /home/jupyter/work/opdi-workspace/opdi/.claude/worktrees/track-construction-v1
git status --short
git log --oneline -1
git rev-list --count main..HEAD   # expect 49
git rev-list --count HEAD..main   # expect 30
```

Expected: clean tree, HEAD at `6116873`, counts 49 and 30. If the tree is dirty, stop and report — do not stash.

- [ ] **Step 2: Record the pre-merge test baseline**

```bash
.venv310/bin/python -m pytest tests/ -q 2>&1 | tail -5
```

Expected: 322 tests, all passing. Write the exact number down; Step 7 compares against it.

- [ ] **Step 3: Start the merge**

```bash
git merge main
```

Expected: `CONFLICT (content): Merge conflict in src/opdi/pipeline/flights.py`, and nothing else conflicted.

- [ ] **Step 4: Resolve the conflict**

Open `src/opdi/pipeline/flights.py` at the conflict. Keep **one** `FLIGHT_LIST_VERSION = "v5.0.0"` assignment, preceded by a comment block that carries both sides' text. The result must contain main's sentence about the 2026-08 change set *and* the branch's paragraph about dominant non-blank callsign labelling. Delete every conflict marker.

The merged comment reads, in order: main's existing `v5.0.0` change-set paragraph, then the branch's paragraph beginning "``v5.0.0``: a flight is labelled with its track's dominant non-blank callsign", edited so it no longer reads as a separate bump — change its opening from "``v5.0.0``:" to "Also in ``v5.0.0``:".

```bash
grep -c '^<<<<<<<\|^=======$\|^>>>>>>>' src/opdi/pipeline/flights.py
```

Expected: `0`.

- [ ] **Step 5: Verify the version is asserted once and consistently**

```bash
grep -n 'FLIGHT_LIST_VERSION = ' src/opdi/pipeline/flights.py
grep -rn '"v5.0.0"' tests/ | head
```

Expected: exactly one assignment, and `tests/test_detection_config.py:230` plus the `test_flight_detection.py` assertions all reading `v5.0.0`. No test should still expect `v4.0.0` except the frozen legacy stamps (`v2.0.0`, `v3.0.0`), which must not change.

- [ ] **Step 6: Complete the merge**

```bash
git add src/opdi/pipeline/flights.py
git commit -m "Merge main into track-construction-v1

Both sides bumped FLIGHT_LIST_VERSION to v5.0.0 for different 2026-08
changes -- the field-elevation datum on main, the dominant-callsign
labelling on this branch. v5.0.0 is deliberately one string for the whole
change set, so the two rationales are merged into one comment rather than
split across two versions."
```

- [ ] **Step 7: Run the full suite**

```bash
.venv310/bin/python -m pytest tests/ -q 2>&1 | tail -15
```

Expected: every test passes, and the count is **at least** the 322 from Step 2 (main's 30 commits may add tests). A failure here is a real merge defect — fix it, do not skip it. Report the count.

- [ ] **Step 8: Verify A8 is the default and selectable**

```bash
.venv310/bin/python -c "
import sys; sys.path.insert(0, 'src')
from opdi.pipeline.segmentation.methods import ARMS
r = ARMS['recommended']()
print('arm:', r.name, '| group:', r.group_cols, '| month_suffix:', r.month_suffix)
assert r.group_cols == ['icao24'] and r.month_suffix is False
print('OK')
"
```

Expected: `arm: recommended | group: ['icao24'] | month_suffix: False`, then `OK`.

---

### Task 2: Land the merge on `opdi` main and delete the branch

**Files:**
- Modify: `opdi` main branch ref; meta-repo submodule pointer.

**Interfaces:**
- Consumes: Task 1's merged branch.
- Produces: `opdi` main containing `src/opdi/pipeline/segmentation/`, `benchmarks/track_truth.py`, `benchmarks/track_score.py`. Branch `track-construction-v1` deleted.

- [ ] **Step 1: Verify main can fast-forward**

```bash
cd /home/jupyter/work/opdi-workspace/opdi
git merge-base --is-ancestor main track-construction-v1 && echo "fast-forward possible"
```

Expected: `fast-forward possible`. If not, Task 1 Step 6 did not include main — go back.

- [ ] **Step 2: Fast-forward main**

```bash
cd /home/jupyter/work/opdi-workspace/opdi
git checkout main
git merge --ff-only track-construction-v1
git log --oneline -1
```

- [ ] **Step 3: Verify the modules landed**

```bash
ls src/opdi/pipeline/segmentation/ benchmarks/track_truth.py benchmarks/track_score.py
```

Expected: `base.py methods.py __init__.py` and both benchmark modules present.

- [ ] **Step 4: Run the suite on main**

```bash
.venv310/bin/python -m pytest tests/ -q 2>&1 | tail -5
```

Expected: the same green count as Task 1 Step 7.

- [ ] **Step 5: Push main, then remove the branch and its worktree**

```bash
cd /home/jupyter/work/opdi-workspace/opdi
git push origin main
git worktree remove .claude/worktrees/track-construction-v1
git branch -d track-construction-v1
git push origin --delete track-construction-v1
```

`git branch -d` (not `-D`) is deliberate: it refuses if the branch is not fully merged, which is the check, not a formality. If the remote branch does not exist, the last command errors harmlessly — report it and continue.

- [ ] **Step 6: Update the meta-repo submodule pointer**

```bash
cd /home/jupyter/work/opdi-workspace
git add opdi
git commit -m "Update submodule pointer: A8 segmentation lands on opdi main"
```

- [ ] **Step 7: Record the consequence in CLAUDE.md**

`CLAUDE.md` currently states under "Conventions that matter":

> - **Track splitting is frozen.** `tracks.py:_add_track_id` is marked `CRITICAL - DO NOT MODIFY` — changing it breaks `track_id` continuity with all published data.

That is now false. Replace it with:

```markdown
- **Track identity is a versioned choice, not a frozen rule.** As of 2026-08-27
  the default segmentation is A8 `recommended` (group on `icao24`, break on a
  genuine non-blank callsign change with the lookback bounded to the gap
  threshold), selected through `src/opdi/pipeline/segmentation/`. **`track_id`
  changes shape from the next production run forward** — A8 carries no
  `_{year}_{month}` suffix, so identifiers become `{hash}_{offset}` and any
  consumer parsing the suffix breaks. Past months will not reproduce. Every
  dataset published before this date used the legacy rule. See
  `opdi-portal/papers/track-construction-v1/`.
```

Also delete the now-stale sentence in the same file that says `track_gap_low_altitude_meters` "feeds `tracks.py:_add_track_id`, which is frozen" — keep the rest of that bullet, which is still true about the storage layer and the DDL contract, and reword the clause to "which is a published contract".

```bash
git add CLAUDE.md && git commit -m "Record that track identity is versioned, not frozen"
```

---

# Phase 2 — Analysis

### Task 3: Repo skeleton and packaging

**Files:**
- Create: `pyproject.toml`, `src/oac/__init__.py`, `src/oac/_opdi.py`, `tests/conftest.py`, `tests/test_imports.py`, `.gitignore`, `README.md`

**Interfaces:**
- Produces: `oac._opdi.bootstrap() -> None` (puts opdi's `src/` and `benchmarks/` on `sys.path`); pytest fixture `spark` (local session).

**Why `_opdi.py` exists.** `opdi` is pip-installable (`pyproject.toml`, name `opdi`), but `benchmarks/track_truth.py` and `benchmarks/track_score.py` live *outside* `src/` and are therefore not part of the installed package. They still must not be copied — they are the single definition of ground truth and of the offset computation. `bootstrap()` puts both directories on `sys.path`, the same device `opdi`'s own benchmark modules use.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_imports.py
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_bootstrap_makes_opdi_importable():
    from oac._opdi import bootstrap
    bootstrap()
    import track_truth
    import track_score
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
        "bad = [m for m in sys.modules if m == 'pyspark' or m == 'opdi'"
        " or m.startswith('pyspark.') or m.startswith('opdi.')];"
        "assert not bad, bad; print('clean')" % str(REPO / "src")
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert "clean" in out.stdout
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_imports.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'oac'`.

- [ ] **Step 3: Write `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=65.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "oac"
version = "0.1.0"
description = "OpenSky ADS-B airport coverage from OPDI track boundary error"
requires-python = ">=3.10"
dependencies = ["pandas>=2.0", "numpy>=1.24", "pyarrow>=12.0", "matplotlib>=3.7"]

[project.optional-dependencies]
cluster = ["pyspark>=3.4", "boto3>=1.28"]
dev = ["pytest>=7.4"]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

- [ ] **Step 4: Write `src/oac/_opdi.py`**

```python
"""Put the `opdi` repository on `sys.path`.

`opdi` is pip-installable, but `benchmarks/track_truth.py` and
`benchmarks/track_score.py` live outside `src/` and are not part of the
installed package. They are the single definition of ground truth and of the
signed offset computation, and copying them here would fork exactly what
`boundary_offsets` was extracted to keep single -- so they are imported from
the source tree instead.

`OPDI_REPO` overrides the location; the default is a sibling checkout.

**Nothing under `oac.aggregate`, `oac.rank` or `site/` may call this.** Those
render in GitHub Actions, which has no `opdi` checkout and no Spark.
"""

import os
import sys
from pathlib import Path

DEFAULT_OPDI = Path(__file__).resolve().parents[3] / "opdi"


def opdi_repo() -> Path:
    """The `opdi` checkout this repo reads its shared modules from."""
    return Path(os.environ.get("OPDI_REPO", DEFAULT_OPDI)).resolve()


def bootstrap() -> None:
    """Idempotently place opdi's `src/` and `benchmarks/` on `sys.path`."""
    repo = opdi_repo()
    if not (repo / "src" / "opdi").is_dir():
        raise RuntimeError(
            f"opdi not found at {repo}. Set OPDI_REPO to the checkout that "
            "carries src/opdi and benchmarks/track_truth.py."
        )
    for sub in ("src", "benchmarks"):
        p = str(repo / sub)
        if p not in sys.path:
            sys.path.insert(0, p)
```

Create `src/oac/__init__.py` empty, and stub `src/oac/aggregate.py` and `src/oac/rank.py` with a module docstring only, so the second test can import them.

- [ ] **Step 5: Write `tests/conftest.py`**

```python
import pytest


@pytest.fixture(scope="session")
def spark():
    """Local Spark session. Mirrors opdi's own conftest -- no cluster."""
    pyspark = pytest.importorskip("pyspark")
    from pyspark.sql import SparkSession

    s = (
        SparkSession.builder.master("local[2]")
        .appName("oac-tests")
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    yield s
    s.stop()
```

- [ ] **Step 6: Create the virtualenv and install**

```bash
cd /home/jupyter/work/opdi-workspace/opensky-airport-coverage
python3 -m venv .venv
.venv/bin/pip install -q -e ".[dev,cluster]"
```

- [ ] **Step 7: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_imports.py -v`
Expected: both PASS.

- [ ] **Step 8: Write `.gitignore` and `README.md`, then commit**

`.gitignore`: `.venv/`, `__pycache__/`, `*.pyc`, `site/_site/`, `site/.quarto/`, `site/airports/*.qmd` (generated), `.env`.

`README.md`: what the repo measures, the two-stage architecture (cluster job → committed extract → offline site), and the exact regeneration commands. No marketing.

```bash
git add -A && git commit -m "Repo skeleton: packaging, opdi bootstrap, test harness"
```

---

### Task 4: Ground truth with block times and a bbox filter

**Files:**
- Create: `src/oac/truth.py`, `tests/test_truth.py`
- Modify: `<opdi>/benchmarks/track_truth.py` (`load_apdf_times` gains `BLOCK_TIME_UTC`)

**Interfaces:**
- Consumes: `track_truth.load_apdf_times(spark, months, reference_base) -> (dep, arr)`.
- Produces:
  - `track_truth.load_apdf_times` — `dep` gains `aobt`, `arr` gains `aibt`.
  - `oac.truth.load_block_times(spark, months, reference_base=None) -> DataFrame` with `callsign, mvt_day, aerodrome, phase, block_time`.
  - `oac.truth.BBOX = (-25.86653, 26.74617, 49.65699, 70.25976)`
  - `oac.truth.in_bbox(lon, lat) -> Column`
  - `oac.truth.airports_in_bbox(spark, airports_path) -> DataFrame` with `icao, name, lat, lon`.

**Why `load_apdf_times` changes rather than being wrapped.** APDF has no literal AOBT/AIBT column: both are `BLOCK_TIME_UTC`, discriminated by `SRC_PHASE` — `DEP` is off-block, `ARR` is in-block. That discrimination is already implemented, correctly, in `load_apdf_times`. Adding a second implementation of it in this repo is how the two drift. The change is additive: `dep` and `arr` gain one column each, and existing callers select what they already selected.

- [ ] **Step 1: Write the failing test for the opdi change**

```python
# tests/test_truth.py
import datetime as dt
import pytest
from oac._opdi import bootstrap

bootstrap()
import track_truth  # noqa: E402


def _apdf_rows(spark, tmp_path):
    """Two APDF rows: one departure, one arrival, both with block times."""
    from pyspark.sql import Row
    rows = [
        Row(APDS_ID=1, ID=1, AP_C_FLTID="TST123 ", AP_C_FLTRUL="I", AP_C_REG="X",
            ADEP_ICAO="EBBR", ADES_ICAO="EGLL", SRC_PHASE="DEP",
            MVT_TIME_UTC=dt.datetime(2025, 6, 5, 10, 15, 0),
            BLOCK_TIME_UTC=dt.datetime(2025, 6, 5, 10, 0, 0),
            SCHED_TIME_UTC=None, ARCTYP="A320", AP_C_RWY="25R", AP_C_STND="A1",
            C40_CROSS_TIME=None, C40_CROSS_LAT=None, C40_CROSS_LON=None,
            C40_CROSS_FL=None, C40_BEARING=None, C100_CROSS_TIME=None,
            C100_CROSS_LAT=None, C100_CROSS_LON=None, C100_CROSS_FL=None,
            C100_BEARING=None),
        Row(APDS_ID=2, ID=2, AP_C_FLTID="TST123 ", AP_C_FLTRUL="I", AP_C_REG="X",
            ADEP_ICAO="EBBR", ADES_ICAO="EGLL", SRC_PHASE="ARR",
            MVT_TIME_UTC=dt.datetime(2025, 6, 5, 11, 5, 0),
            BLOCK_TIME_UTC=dt.datetime(2025, 6, 5, 11, 12, 0),
            SCHED_TIME_UTC=None, ARCTYP="A320", AP_C_RWY="27L", AP_C_STND="B2",
            C40_CROSS_TIME=None, C40_CROSS_LAT=None, C40_CROSS_LON=None,
            C40_CROSS_FL=None, C40_BEARING=None, C100_CROSS_TIME=None,
            C100_CROSS_LAT=None, C100_CROSS_LON=None, C100_CROSS_FL=None,
            C100_BEARING=None),
    ]
    base = str(tmp_path)
    spark.createDataFrame(rows).write.parquet(f"{base}/apdf_202506.parquet")
    return base


def test_departure_block_time_is_aobt_arrival_is_aibt(spark, tmp_path):
    base = _apdf_rows(spark, tmp_path)
    dep, arr = track_truth.load_apdf_times(spark, ["202506"], reference_base=base)

    d = dep.collect()
    assert len(d) == 1
    assert d[0]["atot"] == dt.datetime(2025, 6, 5, 10, 15, 0)
    assert d[0]["aobt"] == dt.datetime(2025, 6, 5, 10, 0, 0)
    assert d[0]["aobt"] < d[0]["atot"], "off-block precedes take-off"

    a = arr.collect()
    assert len(a) == 1
    assert a[0]["aldt"] == dt.datetime(2025, 6, 5, 11, 5, 0)
    assert a[0]["aibt"] == dt.datetime(2025, 6, 5, 11, 12, 0)
    assert a[0]["aibt"] > a[0]["aldt"], "in-block follows landing"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_truth.py -v`
Expected: FAIL, `KeyError: 'aobt'` (the column does not exist yet).

- [ ] **Step 3: Extend `load_apdf_times` in opdi**

In `<opdi>/benchmarks/track_truth.py`, add `BLOCK_TIME_UTC` to the projection and to both phase frames:

```python
    ap = ap.select(
        F.trim(F.col("AP_C_FLTID")).alias("callsign"),
        F.col("SRC_PHASE"),
        F.col("MVT_TIME_UTC"),
        F.col("BLOCK_TIME_UTC"),
        F.upper(F.trim(F.col("ADEP_ICAO"))).alias("apdf_adep"),
        F.upper(F.trim(F.col("ADES_ICAO"))).alias("apdf_ades"),
    ).withColumn("mvt_day", F.to_date("MVT_TIME_UTC"))

    dep = ap.filter(F.col("SRC_PHASE") == "DEP").select(
        "callsign", "mvt_day", "apdf_adep",
        F.col("MVT_TIME_UTC").alias("atot"),
        # Off-block. APDF has no literal AOBT column: BLOCK_TIME_UTC is
        # off-block on a DEP row and in-block on an ARR row, which is the same
        # SRC_PHASE discrimination this function already applies to
        # MVT_TIME_UTC. Carried so a consumer can normalise boundary error by
        # the flight's own ground phase instead of by an absolute number of
        # seconds, which is not comparable between a hub and a regional field.
        F.col("BLOCK_TIME_UTC").alias("aobt"),
    )
    arr = ap.filter(F.col("SRC_PHASE") == "ARR").select(
        "callsign", "mvt_day", "apdf_ades",
        F.col("MVT_TIME_UTC").alias("aldt"),
        F.col("BLOCK_TIME_UTC").alias("aibt"),  # in-block
    )
```

Then carry `aobt` and `aibt` through `load_flight_intervals`: add `dep.aobt` to the `jdep` select, `arr.aibt` to the `j` select, and both to the final `select(...)` column list. **Do not** add them to `flight_key`'s hash — that would change every existing key.

Update the module docstring's opening paragraph to say APDF gives real ATOT, ALDT, AOBT and AIBT.

- [ ] **Step 4: Run the test**

Run: `.venv/bin/python -m pytest tests/test_truth.py -v`
Expected: PASS.

- [ ] **Step 5: Verify opdi's own suite still passes**

```bash
cd /home/jupyter/work/opdi-workspace/opdi
.venv310/bin/python -m pytest tests/test_track_truth.py tests/test_track_truth_window.py -q 2>&1 | tail -5
```

Expected: green. The change is additive, so a failure means a test asserted an exact column list — update the list, not the behaviour.

- [ ] **Step 6: Write the bbox test**

```python
def test_airports_outside_the_ingestion_bbox_are_excluded(spark, tmp_path):
    """A non-European ADEP appears in NM but was never ingested.

    Its detection rate would read as zero coverage when it is really out of
    scope, so it must not reach a ranking table.
    """
    from oac.truth import airports_in_bbox
    from pyspark.sql import Row
    rows = [
        Row(ident="EBBR", name="Brussels", latitude_deg=50.9, longitude_deg=4.48),
        Row(ident="KJFK", name="New York JFK", latitude_deg=40.64, longitude_deg=-73.78),
        Row(ident="OMDB", name="Dubai", latitude_deg=25.25, longitude_deg=55.36),
    ]
    p = str(tmp_path / "apts")
    spark.createDataFrame(rows).write.parquet(p)
    got = {r["icao"] for r in airports_in_bbox(spark, p).collect()}
    assert got == {"EBBR"}
```

- [ ] **Step 7: Run it to verify it fails**

Expected: FAIL, `ImportError: cannot import name 'airports_in_bbox'`.

- [ ] **Step 8: Implement `src/oac/truth.py`**

```python
"""Ground truth for the coverage study: block times and the ingestion bbox.

Everything about *what a flight is* comes from `opdi`'s `track_truth`, which
this module imports rather than reimplements. What is added here is the two
things a per-aerodrome cut needs and a Europe-wide study did not: the block
times that normalise boundary error by an aerodrome's own ground phase, and the
bounding-box filter that keeps an un-ingested aerodrome out of the ranking.
"""

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

#: The ingestion bounding box, copied from `benchmarks/osn_sample.py:BBOX`.
#: min_lon, min_lat, max_lon, max_lat.
BBOX = (-25.86653, 26.74617, 49.65699, 70.25976)


def in_bbox(lon, lat):
    """Column expression: is this position inside the ingested area."""
    min_lon, min_lat, max_lon, max_lat = BBOX
    return (
        (lon >= min_lon) & (lon <= max_lon) & (lat >= min_lat) & (lat <= max_lat)
    )


def airports_in_bbox(spark: SparkSession, airports_path: str) -> DataFrame:
    """OurAirports aerodromes inside the ingestion bbox.

    An aerodrome outside it appears in the NM flight table -- a flight from
    Dubai to Frankfurt has ADEP OMDB -- but its departure was never ingested,
    so a detection rate computed for it measures the bbox rather than the
    receiver network. Excluding them is the difference between "no coverage"
    and "not in scope", and nothing in the number itself distinguishes the two.
    """
    return (
        spark.read.parquet(airports_path)
        .select(
            F.col("ident").alias("icao"),
            F.col("name").alias("name"),
            F.col("latitude_deg").cast("double").alias("lat"),
            F.col("longitude_deg").cast("double").alias("lon"),
        )
        .filter(in_bbox(F.col("lon"), F.col("lat")))
        .filter(F.col("icao").isNotNull())
        .dropDuplicates(["icao"])
    )
```

- [ ] **Step 9: Run the tests and commit**

Run: `.venv/bin/python -m pytest tests/test_truth.py -v`
Expected: all PASS.

```bash
cd /home/jupyter/work/opdi-workspace/opdi
git add benchmarks/track_truth.py
git commit -m "Carry APDF block times through ground truth

BLOCK_TIME_UTC is off-block on a DEP row and in-block on an ARR row -- the
same SRC_PHASE discrimination already applied to MVT_TIME_UTC. Carried so a
consumer can normalise boundary error by the flight's own ground phase; an
absolute number of seconds is not comparable between a hub and a regional
field. Additive: flight_key is unchanged."

cd /home/jupyter/work/opdi-workspace/opensky-airport-coverage
git add -A && git commit -m "Ground truth: block times and the ingestion bbox filter"
```

---

### Task 5: Per-flight offsets with aerodrome keys, detection and match class

**Files:**
- Create: `src/oac/offsets.py`, `tests/test_offsets.py`

**Interfaces:**
- Consumes: `track_score.boundary_offsets(matched, extents) -> DataFrame`, `track_score.track_extents(assign) -> DataFrame`, `track_truth.overlap_join(assign, gt) -> DataFrame`.
- Produces: `oac.offsets.flight_offsets(matched, extents, gt) -> DataFrame` with columns `flight_key, icao24, gt_adep, gt_ades, t_source, t_off, t_land, aobt, aibt, track_id, trk_start, trk_end, off_s, land_s, match_class, detected`.

**What this adds to `boundary_offsets`.** Three things, none of which belongs upstream because none of them is about a boundary: the aerodrome keys and block times joined back from ground truth; the three-way match classification per flight; and the *undetected* flights, which `boundary_offsets` cannot see because it starts from `matched` and `overlap_join` is an inner join. The signed subtraction and the dominant-track pick are **not** reimplemented — `boundary_offsets` is called.

`match_class` is `merged` / `fragmented` / `clean`, evaluated in that order, matching `track_score.match_rates`: a flight that is both counts as `merged`, because merging is the worse failure and a flight must not improve its class by breaking a second way.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_offsets.py
import datetime as dt
from oac._opdi import bootstrap

bootstrap()
import track_score  # noqa: E402
import track_truth  # noqa: E402

T = dt.datetime


def _gt(spark, rows):
    from pyspark.sql import Row
    return spark.createDataFrame([Row(**r) for r in rows])


def _one_flight(**over):
    row = dict(
        flight_key="fk1", icao24="abc123", callsign="TST1",
        gt_adep="EBBR", gt_ades="EGLL",
        t_off=T(2025, 6, 5, 10, 15), t_land=T(2025, 6, 5, 11, 5),
        aobt=T(2025, 6, 5, 10, 0), aibt=T(2025, 6, 5, 11, 12),
        t_source="apdf", day=dt.date(2025, 6, 5),
    )
    row.update(over)
    return row


def _assign(spark, samples):
    from pyspark.sql import Row
    return spark.createDataFrame(
        [Row(icao24=i, event_time=t, track_id=k) for i, t, k in samples]
    )


def test_track_starting_before_takeoff_has_negative_off_s(spark):
    """The good case, and the sign convention that is easiest to invert."""
    from oac.offsets import flight_offsets
    gt = _gt(spark, [_one_flight()])
    # Track runs 10:05 (taxiing) to 11:10 (taxiing in).
    assign = _assign(spark, [
        ("abc123", T(2025, 6, 5, 10, 5), "t1"),
        ("abc123", T(2025, 6, 5, 10, 30), "t1"),
        ("abc123", T(2025, 6, 5, 11, 10), "t1"),
    ])
    extents = track_score.track_extents(assign)
    matched = track_truth.overlap_join(assign, gt)
    out = flight_offsets(matched, extents, gt).collect()

    assert len(out) == 1
    r = out[0]
    assert r["off_s"] == -600, "10:05 is 600 s before 10:15 take-off"
    assert r["land_s"] == 300, "11:10 is 300 s after 11:05 landing"
    assert r["gt_adep"] == "EBBR" and r["gt_ades"] == "EGLL"
    assert r["aobt"] == T(2025, 6, 5, 10, 0)
    assert r["aibt"] == T(2025, 6, 5, 11, 12)
    assert r["detected"] is True
    assert r["match_class"] == "clean"


def test_flight_never_seen_is_present_and_undetected(spark):
    """The whole point of the left join: an unseen flight is not a missing row.

    boundary_offsets starts from `matched`, and overlap_join is an inner join,
    so a flight with no state vectors is invisible to every V1 metric. It is
    the strongest coverage signal there is.
    """
    from oac.offsets import flight_offsets
    gt = _gt(spark, [_one_flight(), _one_flight(flight_key="fk2", icao24="def456")])
    assign = _assign(spark, [("abc123", T(2025, 6, 5, 10, 30), "t1")])
    extents = track_score.track_extents(assign)
    matched = track_truth.overlap_join(assign, gt)
    out = {r["flight_key"]: r for r in flight_offsets(matched, extents, gt).collect()}

    assert set(out) == {"fk1", "fk2"}
    assert out["fk2"]["detected"] is False
    assert out["fk2"]["off_s"] is None
    assert out["fk2"]["land_s"] is None
    assert out["fk2"]["gt_adep"] == "EBBR", "keys survive so it can be counted"


def test_two_flights_in_one_track_are_classed_merged(spark):
    """Merging is worse than fragmentation and must win the classification."""
    from oac.offsets import flight_offsets
    gt = _gt(spark, [
        _one_flight(),
        _one_flight(flight_key="fk2",
                    t_off=T(2025, 6, 5, 12, 0), t_land=T(2025, 6, 5, 13, 0),
                    aobt=T(2025, 6, 5, 11, 45), aibt=T(2025, 6, 5, 13, 7)),
    ])
    assign = _assign(spark, [
        ("abc123", T(2025, 6, 5, 10, 30), "t1"),
        ("abc123", T(2025, 6, 5, 12, 30), "t1"),
    ])
    extents = track_score.track_extents(assign)
    matched = track_truth.overlap_join(assign, gt)
    out = {r["flight_key"]: r for r in flight_offsets(matched, extents, gt).collect()}
    assert out["fk1"]["match_class"] == "merged"
    assert out["fk2"]["match_class"] == "merged"


def test_one_flight_in_two_tracks_is_fragmented(spark):
    from oac.offsets import flight_offsets
    gt = _gt(spark, [_one_flight()])
    assign = _assign(spark, [
        ("abc123", T(2025, 6, 5, 10, 20), "t1"),
        ("abc123", T(2025, 6, 5, 10, 50), "t2"),
    ])
    extents = track_score.track_extents(assign)
    matched = track_truth.overlap_join(assign, gt)
    out = flight_offsets(matched, extents, gt).collect()
    assert out[0]["match_class"] == "fragmented"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_offsets.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'oac.offsets'`.

- [ ] **Step 3: Implement `src/oac/offsets.py`**

```python
"""One row per ground-truth flight, ready to aggregate by aerodrome.

`track_score.boundary_offsets` already does the hard half -- sample selection,
the dominant-track pick, the `extents` join and the signed subtraction -- and
it is **called**, not reimplemented. A second implementation of the sign
convention would look entirely plausible while describing a different
population, and nothing in the output would say so.

Three things are added, none of which is about a boundary:

* the aerodrome keys and block times, joined back from ground truth so the
  result can be cut per aerodrome and normalised by the flight's own ground
  phase;
* `match_class`, the three-way clean/fragmented/merged classification, so a bad
  coverage number can be attributed to reception or to the segmentation;
* the **undetected flights**. `boundary_offsets` starts from `matched`, and
  `track_truth.overlap_join` is an inner join, so a flight OpenSky never saw
  simply is not there. That is the single strongest coverage signal available,
  and recovering it needs a left join from full ground truth.
"""

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F

import track_score

__all__ = ["match_classes", "flight_offsets"]


def match_classes(matched: DataFrame) -> DataFrame:
    """`flight_key` -> `match_class`, one row per detected flight.

    The same three mutually exclusive classes `track_score.match_rates`
    counts, and evaluated in the same order: a flight that is both merged and
    fragmented counts as **merged**, because merging is the worse failure and a
    flight must not improve its classification by also breaking a second way.
    """
    per_pair = matched.groupBy("flight_key", "track_id").agg(
        F.count(F.lit(1)).alias("n")
    )
    # Tracks this flight touches, and -- for each of those tracks -- whether it
    # also carries another flight.
    track_flights = matched.groupBy("track_id").agg(
        F.countDistinct("flight_key").alias("n_flights_on_track")
    )
    j = per_pair.join(track_flights, "track_id")
    return j.groupBy("flight_key").agg(
        F.countDistinct("track_id").alias("n_tracks"),
        F.max("n_flights_on_track").alias("max_flights_on_track"),
    ).select(
        "flight_key",
        F.when(F.col("max_flights_on_track") > 1, F.lit("merged"))
        .when(F.col("n_tracks") > 1, F.lit("fragmented"))
        .otherwise(F.lit("clean"))
        .alias("match_class"),
    )


def flight_offsets(matched: DataFrame, extents: DataFrame, gt: DataFrame) -> DataFrame:
    """One row per ground-truth flight, detected or not.

    `matched` and `extents` must come from the same assignment table --
    `boundary_offsets` raises if they do not, and that check is deliberately
    not duplicated here.

    Sign convention, stated once: `off_s = trk_start - t_off` (negative means
    the track began before wheels-off, which is the good case) and
    `land_s = trk_end - t_land` (positive means it ran on past touchdown).
    """
    # boundary_offsets restricts itself to t_source == "apdf". This study
    # reports both tiers, so it is called on the full frame and the tier is
    # carried as a column instead -- the widening `boundary_error`'s docstring
    # records as open, opened here deliberately and only for the airborne
    # metrics. Capture fractions still require APDF, because AIBT exists
    # nowhere else.
    apdf_only = matched.filter(F.col("t_source") == "apdf")
    nm_only = matched.filter(F.col("t_source") != "apdf")

    parts = []
    for side in (apdf_only, nm_only):
        # boundary_offsets keys its own filter on t_source == "apdf"; feed each
        # tier a frame that satisfies it by relabelling, then restore.
        relabelled = side.withColumn("t_source", F.lit("apdf"))
        off = track_score.boundary_offsets(relabelled, extents)
        parts.append(off.select("flight_key", "track_id", "trk_start", "off_s",
                                "land_s").localCheckpoint(eager=True))
        off.unpersist()
    offs = parts[0].unionByName(parts[1])

    # trk_end is not returned by boundary_offsets; join it from extents.
    offs = offs.join(extents.select("track_id", "trk_end"), "track_id", "left")

    cls = match_classes(matched)

    return (
        gt.select("flight_key", "icao24", "gt_adep", "gt_ades", "t_source",
                  "t_off", "t_land", "aobt", "aibt")
        .join(offs, "flight_key", "left")
        .join(cls, "flight_key", "left")
        .withColumn("detected", F.col("track_id").isNotNull())
    )
```

**Note on `localCheckpoint`.** `boundary_offsets` caches its result and requires the caller to `unpersist()` it. Materialising each tier before the union means the union does not re-derive a cached-then-unpersisted plan. If `localCheckpoint` is unavailable in the local test session, `.cache().count()` is an acceptable substitute — but the `unpersist()` contract must still be honoured.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_offsets.py -v`
Expected: all four PASS. If `test_two_flights_in_one_track_are_classed_merged` fails, check `match_classes` — the bug is almost always classifying on `n_tracks` before `max_flights_on_track`.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "Per-flight offsets with aerodrome keys, match class and detection"
```

---

### Task 6: The cluster job

**Files:**
- Create: `scripts/run_offsets.py`

**Interfaces:**
- Consumes: `oac.offsets.flight_offsets`, `oac.truth.airports_in_bbox`, `track_methods.run_arm`, `track_truth.load_flight_intervals`, `osn_sample.build_spark`.
- Produces: `data/flight_offsets_<period>.parquet`, and a manifest entry per period.

**Reuse, not reimplementation.** `track_methods.run_arm(spark, s3, arm_name, period, sv, gt, params, keep_assignments, score=..., path_arm=...)` already owns the streamed write, the free-space check, the prefix-scoped delete and the release on the failure path. Its `score` hook takes `(matched, extents)` and returns whatever you want. Pass a closure that calls `flight_offsets` and returns a pandas DataFrame. Pass `path_arm="coverage_<period>"` so this job's deletes can never match a prefix another job is mid-write on.

- [ ] **Step 1: Write the script**

```python
"""Produce the per-flight offsets table for one period, on the OSN cluster.

    python scripts/run_offsets.py --period 2025

Reads cleaned tracks for the sample days, segments them with the A8
`recommended` rule, and writes one row per ground-truth flight to
`data/flight_offsets_<period>.parquet`.

**The assignment table is written, read back and deleted within one run.** The
bucket was at 96.89 GB of a ~100 GB quota on 2026-08-23 and one assignment
table is ~0.31 GB, so peak footprint is one, not two. That discipline lives in
`track_methods.run_arm`, which this script calls rather than copies -- including
the release on the failure path, which is what stops a crash orphaning a table
on a bucket with single-digit GB free.

**Extents come from the unfiltered assignment table.** `run_arm` computes them
that way; do not recompute from `matched`, which `overlap_join` has clipped to
`[t_off, t_land]`.
"""

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from oac._opdi import bootstrap  # noqa: E402

bootstrap()

import osn_sample  # noqa: E402
import provenance  # noqa: E402
import track_methods  # noqa: E402
import track_truth  # noqa: E402
from pyspark.sql import functions as F  # noqa: E402

from oac.offsets import flight_offsets  # noqa: E402
from oac.truth import airports_in_bbox  # noqa: E402
from opdi.config import OPDIConfig  # noqa: E402
from opdi.pipeline.segmentation import SegmentationParams  # noqa: E402

ARM = "recommended"  # A8 -- the study's segmentation, now opdi's default
DATA = REPO / "data"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", choices=sorted(track_methods.PERIODS), required=True)
    ap.add_argument("--days", nargs="+", default=None)
    ap.add_argument("--keep-assignments", action="store_true")
    args = ap.parse_args()

    osn_sample.load_dotenv()
    spark = osn_sample.build_spark(cores=8, driver_memory="8g")
    s3 = track_methods.s3_client()

    p = track_methods.PERIODS[args.period]
    days = args.days or p["days"]

    sv = spark.read.parquet(p["tracks"]).filter(F.to_date("event_time").isin(days))
    sv = track_methods.attach_airport_context(spark, sv).cache()
    gt = track_truth.load_flight_intervals(spark, p["months"], days).cache()

    # Aerodromes outside the ingestion bbox were never sampled, so a detection
    # rate for them measures the bbox and not the receiver network.
    apts = airports_in_bbox(spark, track_methods.AIRPORTS).select("icao").cache()
    gt = (
        gt.join(apts.withColumnRenamed("icao", "gt_adep"), "gt_adep", "left_semi")
        .union(gt.join(apts.withColumnRenamed("icao", "gt_ades"), "gt_ades", "left_semi"))
        .dropDuplicates(["flight_key"])
        .cache()
    )

    n_sv, n_gt = sv.count(), gt.count()
    print(f"{n_sv:,} samples, {n_gt:,} ground-truth flights in bbox")

    cfg = OPDIConfig().segmentation
    params = SegmentationParams(
        gap_minutes=cfg.gap_minutes,
        low_alt_gap_minutes=cfg.low_alt_gap_minutes,
        low_alt_ft=cfg.low_alt_ft,
        ground_dwell_minutes=cfg.ground_dwell_minutes,
        turnaround_max_height_ft=cfg.turnaround_max_height_ft,
        turnaround_max_speed_kt=cfg.turnaround_max_speed_kt,
        descent_floor_ft=cfg.descent_floor_ft,
    )

    def score(matched, extents):
        out = flight_offsets(matched, extents, gt)
        return out.toPandas()

    df, meta = track_methods.run_arm(
        spark, s3, ARM, args.period, sv, gt, params,
        args.keep_assignments, score=score, path_arm=f"coverage_{args.period}",
    )
    df["period"] = args.period

    DATA.mkdir(parents=True, exist_ok=True)
    name = f"flight_offsets_{args.period}.parquet"
    df.to_parquet(DATA / name, index=False)
    print(f"wrote {len(df):,} rows to {name}")

    provenance.record(
        DATA, name,
        script="scripts/run_offsets.py", argv=sys.argv[1:],
        code_paths=[REPO / "src" / "oac" / "offsets.py",
                    REPO / "src" / "oac" / "truth.py",
                    REPO / "scripts" / "run_offsets.py"],
        inputs={"state_vectors": n_sv, "ground_truth_flights": n_gt,
                "assignment_objects": meta["assign_objects"],
                "assignment_bytes": meta["assign_bytes"]},
        input_tables=[p["tracks"]],
        notes=f"arm={ARM}, days={days}. Signed: off_s = trk_start - ATOT, "
              f"land_s = trk_end - ALDT.",
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Syntax and import check without touching the cluster**

```bash
.venv/bin/python -c "import ast,sys; ast.parse(open('scripts/run_offsets.py').read()); print('parses')"
```

Expected: `parses`.

- [ ] **Step 3: Commit before running anything expensive**

```bash
git add -A && git commit -m "Cluster job: per-flight offsets for one period"
```

- [ ] **Step 4: Run the 2025 period**

```bash
cd /home/jupyter/work/opdi-workspace/opensky-airport-coverage
OPDI_REPO=../opdi .venv/bin/python scripts/run_offsets.py --period 2025 2>&1 | tail -30
```

Expected: a sample count near 143 M state vectors and ground truth near 90,000 flights, then `wrote ~90,000 rows`. This takes tens of minutes. **One Spark job at a time** — do not start the 2024 run in parallel.

- [ ] **Step 5: Sanity-check the output before trusting it**

```bash
.venv/bin/python -c "
import pandas as pd
d = pd.read_parquet('data/flight_offsets_2025.parquet')
print(len(d), 'rows;', d.detected.mean().round(4), 'detected')
print(d.t_source.value_counts())
det = d[d.detected]
print('off_s  p10/p50/p90:', det.off_s.quantile([.1,.5,.9]).round(0).tolist())
print('land_s p10/p50/p90:', det.land_s.quantile([.1,.5,.9]).round(0).tolist())
print('match_class:'); print(det.match_class.value_counts(normalize=True).round(4))
print('adep nunique:', d.gt_adep.nunique(), '| ades nunique:', d.gt_ades.nunique())
"
```

Expected, and each is a real check rather than a formality:
- `land_s` p10 is **positive** — tracks essentially always run through taxi-in. A negative p10 means the sign convention inverted somewhere.
- `off_s` p50 is small and near zero, p10 strongly negative — V1 measured the signed departure median at roughly +109 s absolute with a long negative tail.
- `match_class` shows `clean` around 0.91 for A8. Around 0.50 means the legacy arm ran instead — check `ARM`.
- `gt_adep` nunique is in the hundreds, not thousands: the bbox filter worked.

If any of these is wrong, stop and diagnose. A silently inverted sign produces a complete, plausible ranking that is exactly backwards.

- [ ] **Step 6: Run the 2024 period and sanity-check it the same way**

```bash
OPDI_REPO=../opdi .venv/bin/python scripts/run_offsets.py --period 2024 2>&1 | tail -30
```

- [ ] **Step 7: Confirm the bucket was left clean**

```bash
.venv/bin/python -c "
import sys; sys.path.insert(0,'src')
from oac._opdi import bootstrap; bootstrap()
import track_methods as tm
s3 = tm.s3_client()
for per in ('2025','2024'):
    n, b = tm.prefix_size(s3, f'{tm.ASSIGN_PREFIX}/coverage_{per}/')
    print(per, n, 'objects', round(b/1e9,3), 'GB')
print('bucket total', round(tm.bucket_total_gb(s3),2), 'GB')
"
```

Expected: `0 objects` for both periods. A non-zero count means an assignment table was orphaned — delete it before continuing, the bucket has ~3 GB of headroom.

- [ ] **Step 8: Commit the extracts**

```bash
git add data/ && git commit -m "Per-flight offsets for both sample periods"
```

---

### Task 7: Per-aerodrome aggregation, capture and the Coverage Index

**Files:**
- Create: `src/oac/aggregate.py`, `src/oac/rank.py`, `scripts/aggregate.py`, `tests/test_aggregate.py`

**Interfaces:**
- Consumes: `data/flight_offsets_{2025,2024}.parquet`.
- Produces:
  - `oac.aggregate.capture(df) -> DataFrame` — adds `dep_capture`, `arr_capture`, `taxi_out_s`, `taxi_in_s`, `capture_valid`.
  - `oac.aggregate.by_airport(df, side) -> DataFrame` where `side` is `"dep"` or `"arr"`.
  - `oac.aggregate.airport_table(df) -> DataFrame` — departures and arrivals merged, one row per aerodrome.
  - `oac.rank.coverage_index(row) -> float`, `oac.rank.rank_tiers(tbl) -> (tier_a, tier_b)`.
  - `oac.aggregate.MIN_N = 20`

**Pure pandas. No pyspark, no opdi** — `tests/test_imports.py` enforces it.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_aggregate.py
import numpy as np
import pandas as pd
import pytest

from oac.aggregate import MIN_N, airport_table, by_airport, capture
from oac.rank import coverage_index, rank_tiers

T = pd.Timestamp


def _flights(n=1, **over):
    base = dict(
        flight_key=[f"fk{i}" for i in range(n)],
        gt_adep="EBBR", gt_ades="EGLL", t_source="apdf",
        t_off=T("2025-06-05 10:15"), t_land=T("2025-06-05 11:05"),
        aobt=T("2025-06-05 10:00"), aibt=T("2025-06-05 11:12"),
        trk_start=T("2025-06-05 10:05"), trk_end=T("2025-06-05 11:10"),
        off_s=-600.0, land_s=300.0, match_class="clean", detected=True,
        period="2025",
    )
    base.update(over)
    return pd.DataFrame(base)


def test_capture_is_the_fraction_of_the_ground_phase_seen():
    """Taxi-out is 900 s; the track began 600 s before take-off."""
    out = capture(_flights())
    assert out.taxi_out_s.iloc[0] == 900
    assert out.dep_capture.iloc[0] == pytest.approx(600 / 900)
    assert out.taxi_in_s.iloc[0] == 420
    assert out.arr_capture.iloc[0] == pytest.approx(300 / 420)


def test_capture_is_clipped_to_the_unit_interval():
    """A track starting before off-block saw all of the taxi, not 140% of it."""
    out = capture(_flights(trk_start=T("2025-06-05 09:55")))
    assert out.dep_capture.iloc[0] == 1.0


def test_a_track_starting_after_takeoff_captures_none_of_the_ground():
    out = capture(_flights(trk_start=T("2025-06-05 10:20"), off_s=300.0))
    assert out.dep_capture.iloc[0] == 0.0


def test_non_positive_ground_phase_is_excluded_not_clipped():
    """AOBT >= ATOT is bad reference data, not zero coverage.

    Clipping it would score the flight 0 or 1 and quietly move the
    aerodrome's median; excluding it and counting it is the honest option.
    """
    bad = _flights(aobt=T("2025-06-05 10:20"))  # off-block after take-off
    out = capture(bad)
    assert bool(out.capture_valid.iloc[0]) is False
    assert pd.isna(out.dep_capture.iloc[0])

    stats = by_airport(out, "dep")
    assert stats.n_capture_excluded.iloc[0] == 1
    assert pd.isna(stats.dep_capture_p50.iloc[0])


def test_detection_counts_flights_never_seen():
    df = pd.concat([
        _flights(n=3),
        _flights(n=1, detected=False, off_s=np.nan, land_s=np.nan,
                 trk_start=pd.NaT, trk_end=pd.NaT, match_class=None),
    ], ignore_index=True)
    df["flight_key"] = [f"k{i}" for i in range(len(df))]
    stats = by_airport(capture(df), "dep")
    assert stats.n_gt.iloc[0] == 4
    assert stats.n_detected.iloc[0] == 3
    assert stats.detection_pct.iloc[0] == pytest.approx(75.0)


def test_coverage_index_is_detection_times_mean_capture():
    row = dict(detection_pct=80.0, dep_capture_p50=0.5, arr_capture_p50=0.9)
    assert coverage_index(row) == pytest.approx(0.8 * 0.7)


def test_coverage_index_is_null_without_capture():
    """Tier B has no capture term and must not be given a fabricated one."""
    row = dict(detection_pct=80.0, dep_capture_p50=np.nan, arr_capture_p50=np.nan)
    assert pd.isna(coverage_index(row))


def test_tiers_are_separated_and_thresholded():
    tbl = pd.DataFrame([
        dict(icao="EBBR", t_source="apdf", n_gt=500, detection_pct=90.0,
             dep_capture_p50=0.6, arr_capture_p50=0.8),
        dict(icao="LFXX", t_source="nm_inferred", n_gt=50, detection_pct=70.0,
             dep_capture_p50=np.nan, arr_capture_p50=np.nan),
        dict(icao="TINY", t_source="nm_inferred", n_gt=5, detection_pct=20.0,
             dep_capture_p50=np.nan, arr_capture_p50=np.nan),
    ])
    a, b = rank_tiers(tbl)
    assert list(a.icao) == ["EBBR"]
    assert list(b.icao) == ["LFXX"], f"n_gt < {MIN_N} must be cut"
    assert a["rank"].iloc[0] == 1 and b["rank"].iloc[0] == 1
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_aggregate.py -v`
Expected: FAIL on import.

- [ ] **Step 3: Implement `src/oac/aggregate.py`**

Key points the implementer must get right, each of which a test above pins:

```python
"""Per-aerodrome statistics from the committed per-flight table.

Pure pandas, deliberately. The cluster produces one small table; everything
after it -- percentiles, capture, tiers, the index -- is a laptop edit rather
than a two-hour re-run, and it must import neither pyspark nor opdi because the
site renders in GitHub Actions.
"""

import numpy as np
import pandas as pd

#: An aerodrome qualifies when max(n_dep, n_arr) >= MIN_N in at least one
#: period. Stated once; never re-chosen per table.
MIN_N = 20

PCTS = [10, 25, 50, 75, 90]


def capture(df: pd.DataFrame) -> pd.DataFrame:
    """Add the normalised ground-phase capture fractions.

        dep_capture = clip((ATOT - trk_start) / (ATOT - AOBT), 0, 1)
        arr_capture = clip((trk_end - ALDT) / (AIBT - ALDT), 0, 1)

    Raw seconds are not comparable between aerodromes: -180 s is complete
    coverage at a field with a three-minute taxi and about 15% of it at a hub
    with a twenty-minute one.

    **A non-positive ground phase is excluded, not clipped.** `AOBT >= ATOT` or
    `AIBT <= ALDT` is bad reference data; clipping would silently score the
    flight 0 or 1 and move the aerodrome's median. `capture_valid` marks them
    and `by_airport` counts them into `n_capture_excluded`.
    """
    out = df.copy()
    out["taxi_out_s"] = (out.t_off - out.aobt).dt.total_seconds()
    out["taxi_in_s"] = (out.aibt - out.t_land).dt.total_seconds()
    valid_out = out.taxi_out_s > 0
    valid_in = out.taxi_in_s > 0
    out["capture_valid"] = valid_out & valid_in

    dep = (-out.off_s) / out.taxi_out_s        # off_s = trk_start - t_off
    arr = out.land_s / out.taxi_in_s           # land_s = trk_end - t_land
    out["dep_capture"] = np.where(valid_out & out.detected, dep.clip(0, 1), np.nan)
    out["arr_capture"] = np.where(valid_in & out.detected, arr.clip(0, 1), np.nan)
    return out
```

`by_airport(df, side)` groups on `gt_adep` for `"dep"` and `gt_ades` for `"arr"`, and emits, with the side's prefix where the column is side-specific:

`icao, t_source, n_gt, n_detected, detection_pct, n_capture_excluded, off_s_p10..p90` (dep) or `land_s_p10..p90` (arr), `off_abs_p50, off_abs_p90` (dep) / `land_abs_p50, land_abs_p90` (arr), `{dep,arr}_capture_p10/p50/p90`, `dep_no_ground_pct`, `dep_full_capture_pct`, `taxi_out_median_s` / `taxi_in_median_s`, `clean_pct`, `fragmented_pct`, `merged_pct`.

Percentiles are computed over **detected** flights only (an undetected flight has no offset), while `n_gt` counts **all** ground-truth flights — that asymmetry is the whole point of the detection column and must not be smoothed away. `t_source` per aerodrome is the modal value.

`airport_table(df)` runs both sides and outer-merges on `icao`, so an aerodrome with departures but no arrivals keeps its row.

- [ ] **Step 4: Implement `src/oac/rank.py`**

```python
"""The Coverage Index and the two ranking tables."""

import numpy as np
import pandas as pd

from oac.aggregate import MIN_N


def coverage_index(row) -> float:
    """`detection_rate * (0.5*dep_capture_p50 + 0.5*arr_capture_p50)`.

    Read as the expected share of a movement actually captured: the chance the
    flight is seen at all, times how much of its ground phase is seen when it
    is. Returns NaN when neither capture term exists -- a Tier B aerodrome has
    no AIBT and must not be given a fabricated capture of any value, including
    zero, which would rank it below every measured aerodrome for a reason that
    is not about coverage.
    """
    dep, arr = row["dep_capture_p50"], row["arr_capture_p50"]
    both = [v for v in (dep, arr) if v is not None and not pd.isna(v)]
    if not both:
        return np.nan
    return (row["detection_pct"] / 100.0) * float(np.mean(both))


def rank_tiers(tbl: pd.DataFrame):
    """`(tier_a, tier_b)`, each sorted and given a 1-based `rank`.

    Never interleaved: the two tiers do not measure the same thing. Tier A
    ranks on `coverage_index`, Tier B on `detection_pct` alone.
    """
    t = tbl.copy()
    t["coverage_index"] = t.apply(coverage_index, axis=1)
    t = t[t.n_gt >= MIN_N]

    a = t[t.t_source == "apdf"].sort_values("coverage_index", ascending=False)
    b = t[t.t_source != "apdf"].sort_values("detection_pct", ascending=False)
    for d in (a, b):
        d.insert(0, "rank", range(1, len(d) + 1))
    return a.reset_index(drop=True), b.reset_index(drop=True)
```

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_aggregate.py tests/test_imports.py -v`
Expected: all PASS, including the subprocess purity check.

- [ ] **Step 6: Write `scripts/aggregate.py` and produce the CSVs**

A thin entrypoint: read both periods' parquet, `capture`, `airport_table`, `rank_tiers`, join aerodrome names from a committed `data/airports.csv` (written once by a small helper from `oa_airports`, so the site needs no S3), write `data/airport_stats_{2025,2024}.csv`, `data/ranking_tier_a.csv`, `data/ranking_tier_b.csv`, and a `provenance.record` entry per file.

```bash
.venv/bin/python scripts/aggregate.py
```

- [ ] **Step 7: Eyeball the ranking before building a site on it**

```bash
.venv/bin/python -c "
import pandas as pd
a = pd.read_csv('data/ranking_tier_a.csv')
print(a.head(10)[['rank','icao','n_gt','detection_pct','dep_capture_p50','arr_capture_p50','coverage_index']])
print('...'); print(a.tail(5)[['rank','icao','detection_pct','coverage_index']])
print('tier A rows:', len(a))
b = pd.read_csv('data/ranking_tier_b.csv'); print('tier B rows:', len(b))
"
```

Expected: about 94 Tier A rows and 300–450 Tier B rows. Every `coverage_index` in `0..1`. If the top of the table is dominated by tiny aerodromes, `MIN_N` is not being applied.

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -m "Per-aerodrome aggregation, capture fractions and the Coverage Index"
```

---

# Phase 3 — The site

### Task 8: Quarto skeleton, `metrics.qmd` and `pipeline.qmd`

**Files:**
- Create: `site/_quarto.yml`, `site/index.qmd` (stub), `site/metrics.qmd`, `site/pipeline.qmd`, `site/about.qmd`, `site/_data.py`, `site/styles.css`

**Interfaces:**
- Produces: `site/_data.py` exposing `load_ranking(tier) -> DataFrame`, `load_stats(period) -> DataFrame`, `load_offsets() -> DataFrame`, `manifest() -> dict`, `DATA: Path`.

**Numbers first.** Prose exists only to define a column or state a caveat that would make a number misread. No narrative sections.

- [ ] **Step 1: Write `site/_quarto.yml`**

```yaml
project:
  type: website
  output-dir: _site
website:
  title: "OpenSky airport coverage"
  description: "ADS-B coverage per aerodrome, measured from OPDI track boundary error"
  navbar:
    left:
      - href: index.qmd
        text: Rankings
      - href: pipeline.qmd
        text: Pipeline
      - href: metrics.qmd
        text: Metrics
      - href: about.qmd
        text: About
format:
  html:
    theme: [cosmo, styles.css]
    toc: true
    df-print: paged
    code-fold: true
execute:
  echo: false
  warning: false
  freeze: false
```

- [ ] **Step 2: Write `site/_data.py`**

Loads the committed CSVs relative to the file's own location, never from a hard-coded absolute path, and exposes the manifest so a page can render a row as **unverified** when it has no entry.

- [ ] **Step 3: Write `site/metrics.qmd`**

The data dictionary from the spec, verbatim: one row per column, with `Column | Formula | Unit | Domain | Reading`. It opens with the two sign conventions stated once, because they are the single most likely thing to be misread:

> `off_s` is good when **negative** — the track began before wheels-off.
> `land_s` is good when **positive** — the track ran on past touchdown.

Every column that appears anywhere on the site has a row here, with a stable anchor id so other pages' column headers can link to it.

- [ ] **Step 4: Write `site/pipeline.qmd`**

The mermaid diagram from the spec in a ```` ```{mermaid} ```` block — Quarto renders it natively, no external library, which is what makes it survive the offline render and the Actions build. Below it, the two callouts the diagram exists to make unmissable (extents bypass `overlap_join`; detection needs ground truth as well as `matched`), then the stage table.

The stage table's row counts are **read from `data/_manifest.json`**, not typed in, so the page cannot claim a count the run did not produce. A stage with no manifest entry renders as `unverified`.

- [ ] **Step 5: Write `site/about.qmd`**

Four sections, all of them numbers or lists:

1. **The sample** — the two periods, their day lists, the ground-truth row
   counts read from `data/_manifest.json`, and the segmentation arm.
2. **Provenance** — one row per committed file: the script, argv, git SHA,
   dirty flag and produced-at timestamp, straight from the manifest. A file
   with no entry renders as **unverified** rather than being shown as fact.
3. **Limitations**, verbatim from the spec and stated plainly, not softened:
   six days total and no longer sample is buildable; June only, so nothing here
   describes winter reception; **A8 is not the segmentation any published OPDI
   dataset used**, so these numbers do not describe downloadable OPDI data;
   coverage is receiver coverage *as OPDI ingests it*, after the Europe bbox
   filter and 5 s decimation, not a statement about OpenSky's raw feed; Tier B
   take-off times are inferred, at a measured median error of 0 s but with a
   tail that is not characterised per aerodrome.
4. **Regeneration** — the exact commands, in order, with a note that
   `run_offsets.py` needs cluster credentials and the rest does not.

- [ ] **Step 6: Render and check**

```bash
cd site && quarto render metrics.qmd pipeline.qmd about.qmd 2>&1 | tail -20
```

Expected: no errors, and the mermaid block renders as SVG in `_site/pipeline.html`. Verify with `grep -c '<svg' _site/pipeline.html`.

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "Site skeleton: data dictionary and pipeline provenance page"
```

---

### Task 9: The ranking page

**Files:**
- Modify: `site/index.qmd`
- Create: `site/_charts.py`

**Interfaces:**
- Consumes: `site/_data.py`, `data/ranking_tier_{a,b}.csv`.
- Produces: `site/_charts.py` exposing `hist_offsets(...)`, `ecdf(...)`, `fleet_distribution(...)`, `PALETTE`.

**Read the `dataviz` skill before writing the first line of chart code.** Charts must be theme-neutral and consistent across ~520 pages.

- [ ] **Step 1: Write `site/_charts.py`**

Matplotlib, one shared palette and one shared axis style. Every function returns a figure; no function calls `plt.show()`. Charts render at a fixed size so 520 pages look like one system.

- [ ] **Step 2: Write `site/index.qmd`**

Above the tables: the fleet distribution of `coverage_index` and of `detection_pct`, each with the summary numbers beside it — median, IQR, and counts above and below thresholds — rather than a sentence describing them.

Then the two tables, exactly the columns the spec names, sortable and filterable client-side (`itables`, or a plain `DT`-style HTML table if `itables` is unavailable in CI — decide now and pin it in `pyproject.toml`). Each ICAO links to `airports/<ICAO>.html`; each column header links to its `metrics.qmd` anchor.

- [ ] **Step 3: Render and verify the numbers on the page match the CSV**

```bash
cd site && quarto render index.qmd 2>&1 | tail -10
.venv/bin/python -c "
import pandas as pd, re
a = pd.read_csv('../data/ranking_tier_a.csv')
html = open('_site/index.html').read()
assert a.icao.iloc[0] in html, 'top-ranked aerodrome missing from page'
print('top:', a.icao.iloc[0], a.coverage_index.iloc[0].round(4))
"
```

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "Ranking page: two tiers, fleet distributions, linked columns"
```

---

### Task 10: Per-aerodrome pages

**Files:**
- Create: `site/_airport_template.qmd.j2` (or a plain-format template), `scripts/gen_pages.py`, `tests/test_gen_pages.py`

**Interfaces:**
- Consumes: `data/ranking_tier_{a,b}.csv`, `data/flight_offsets_*.parquet`.
- Produces: `site/airports/<ICAO>.qmd`, one per qualifying aerodrome, plus `site/airports/index.qmd` listing them.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_gen_pages.py
import pandas as pd
from scripts.gen_pages import pages_for


def test_one_page_per_qualifying_aerodrome_and_none_below_threshold():
    tbl = pd.DataFrame([
        dict(icao="EBBR", name="Brussels", t_source="apdf", n_gt=500),
        dict(icao="LFXX", name="Small", t_source="nm_inferred", n_gt=50),
        dict(icao="TINY", name="Tiny", t_source="nm_inferred", n_gt=5),
    ])
    got = {p.icao for p in pages_for(tbl)}
    assert got == {"EBBR", "LFXX"}


def test_tier_is_carried_into_the_page_header_not_a_footnote():
    tbl = pd.DataFrame([dict(icao="LFXX", name="Small",
                             t_source="nm_inferred", n_gt=50)])
    page = list(pages_for(tbl))[0]
    assert page.tier == "B"
    assert "NM-inferred" in page.header
```

- [ ] **Step 2: Run to verify it fails, then implement `scripts/gen_pages.py`**

`pages_for(tbl)` yields a small dataclass per aerodrome (`icao`, `name`, `tier`, `header`, `n_gt`) after applying `MIN_N`. The writer renders the template per page. Generated `.qmd` files are gitignored — they are build output, and committing 520 generated files would bury every real diff.

Each page carries, per the spec: the header line; `off_s` and `land_s` histograms with zero marked and x clipped at ±1800 s with the overflow counted in the caption; `dep_capture`/`arr_capture` ECDFs with the fleet-median ECDF behind as a reference; `off_s` p50 by hour of day; the full percentile table with the 2024→2025 delta; this aerodrome's value against the fleet median and its percentile rank within its tier; segmentation quality; and the counts including `n_capture_excluded`.

- [ ] **Step 3: Generate and render**

```bash
.venv/bin/python scripts/gen_pages.py
ls site/airports/*.qmd | wc -l
cd site && quarto render 2>&1 | tail -20
```

Expected: 400–520 pages, and a clean render. A Quarto failure on one page fails the whole render — fix the template, do not skip the aerodrome.

- [ ] **Step 4: Spot-check a big hub and a thin aerodrome**

Open `_site/airports/EBBR.html` and one Tier B page. Confirm the Tier B page shows **no** capture charts (it has no AIBT) and says so in its header.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "Per-aerodrome pages: distributions, percentiles, fleet comparison"
```

---

### Task 11: GitHub Actions and publication

**Files:**
- Create: `.github/workflows/pages.yml`

- [ ] **Step 1: Write the workflow**

Note `pip install -e .` and **not** `.[cluster]`: CI has no pyspark and must not
need it. If this step ever has to install pyspark, something under `site/` or
`oac.aggregate` has grown an import it should not have.

```yaml
# .github/workflows/pages.yml
name: Render and deploy site

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: true

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"
      - run: pip install -e .
      - uses: quarto-dev/quarto-actions/setup@v2
      - name: Generate per-aerodrome pages
        run: python scripts/gen_pages.py
      - name: Render
        run: quarto render site
      - uses: actions/upload-pages-artifact@v3
        with:
          path: site/_site

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
```

- [ ] **Step 2: Prove it renders without the cluster**

```bash
cd /tmp && rm -rf coverage-ci && git clone /home/jupyter/work/opdi-workspace/opensky-airport-coverage coverage-ci
cd coverage-ci && python3 -m venv .venv && .venv/bin/pip install -q -e .
.venv/bin/python scripts/gen_pages.py && quarto render site 2>&1 | tail -10
```

This is the real test of the whole architecture: a clone with no `opdi`, no `.env`, no Spark, no S3. If it renders, Actions will. If it fails on an `opdi` import, something under `site/` or `oac.aggregate` imported it — find it and move the import behind `oac.offsets`.

- [ ] **Step 3: Commit and push the branch**

```bash
cd /home/jupyter/work/opdi-workspace/opensky-airport-coverage
git add -A && git commit -m "GitHub Actions: render and deploy to Pages"
git push -u origin design/airport-coverage
```

- [ ] **Step 4: Report what the user must do by hand**

The repo's default branch is `main` and Pages must build from it, but pushing to `main` is not something to do unasked. Report: the branch name, the exact command to land it on `main`, and that Pages needs enabling at Settings → Pages → Source: **GitHub Actions**. `gh` is not installed here, so neither step can be scripted.
