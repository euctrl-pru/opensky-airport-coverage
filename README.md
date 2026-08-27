# opensky-airport-coverage

ADS-B coverage per aerodrome, measured from OPDI track boundary error.

**Boundary error** is the signed distance from a track's true first and last
sample to the flight's actual take-off and landing. Read per aerodrome, it is a
coverage measurement: a track that begins fifteen minutes before wheels-off
means a receiver watched the aircraft push back and taxi; one that begins thirty
seconds *after* wheels-off means nothing on the ground was heard at all.

Sign conventions, which are the easiest thing here to misread:

- `off_s = trk_start − ATOT` — **negative is good** (track began before wheels-off)
- `land_s = trk_end − ALDT` — **positive is good** (track ran on past touchdown)

## Two stages, and why

The expensive half runs on the OSN cluster and writes a small table. Everything
after it renders offline, which is what lets GitHub Actions rebuild the site
with no credentials.

```
OSN state vectors (S3, ~10 GB/period)
  └─ scripts/run_offsets.py          cluster, Spark on K8s
       └─ data/flight_offsets_*.parquet   committed, a few MB
            └─ scripts/aggregate.py       laptop, pandas
                 └─ data/*.csv            committed, provenance-stamped
                      └─ site/            Quarto, offline
```

## Setup

Needs a sibling `opdi` checkout — this repo imports opdi's segmentation rule and
its ground-truth loaders rather than copying them, so there is one definition of
each.

```bash
python3.10 -m venv .venv
.venv/bin/pip install -e ".[dev,cluster]"
.venv/bin/pip install -e ../opdi          # brings h3, shapely, and opdi's runtime
.venv/bin/python -m pytest
```

Python 3.10 is not incidental: the OSN cluster's executors run 3.10.20, and a
driver on a different minor version fails at submit.

## Regenerating

```bash
# 1. Ground truth for a month -- WORK LAPTOP ONLY, needs PRISME/ROracle
Rscript scripts/fetch_reference.R 2026-06 --days 05,06,07

# 2. Mirror it to S3 so executors can read it (in the opdi checkout)
python benchmarks/mirror_reference.py --include '*_202606.parquet'

# 3. Per-flight offsets -- cluster, tens of minutes, one period at a time
.venv/bin/python scripts/run_offsets.py --period 2026

# 4. Everything below here is offline
.venv/bin/python scripts/aggregate.py
.venv/bin/python scripts/gen_pages.py
QUARTO_PYTHON=$PWD/.venv/bin/python quarto render site
```

Step 3 is the only one needing credentials. Steps 4 onward are what CI runs.

The full render is **424 aerodrome pages plus four top-level ones**, and takes
roughly half an hour in CI. Two things make that possible rather than
impossible: `execute: daemon: true` reuses one Jupyter kernel across pages
(without it Quarto starts a fresh one per file, which measured four pages in
seven minutes), and `scripts/gen_pages.py` writes a small per-aerodrome slice so
a page reads a few hundred rows rather than the whole per-flight table.

`QUARTO_PYTHON` is needed **locally only**. Quarto's Python engine otherwise
resolves `python3` from PATH, which here is 3.13 and lacks this project's
packages. CI installs into the runner's own `python3`, so the variable is not
set in the workflow.

## Tests

```bash
OPDI_REPO=../opdi .venv/bin/python -m pytest -q
```

One of them, `test_aggregate_does_not_import_spark_or_opdi`, runs a clean
subprocess and asserts the aggregation path pulls in neither pyspark nor opdi.
It is what keeps the site buildable in CI, so a failure there is a design
regression rather than a test problem.

## Publishing (two manual steps)

The site builds itself from committed data, but two things need a human.

**1. Activate the workflow.** It is committed at `ci/pages.yml`, not at
`.github/workflows/pages.yml`, because the token available here lacks GitHub's
`workflow` scope and the push is rejected outright when a workflow file is
added. Move it:

```bash
mkdir -p .github/workflows
git mv ci/pages.yml .github/workflows/pages.yml
git commit -m "Activate the Pages workflow"
git push
```

**2. Enable Pages.** Settings → Pages → Source: **GitHub Actions**. This needs
repository admin and has no CLI equivalent without `gh`.

After that every push to `main` regenerates and republishes the site. The build
needs no secrets: `pip install -e .`, `python scripts/gen_pages.py`,
`quarto render site`, roughly four minutes.
