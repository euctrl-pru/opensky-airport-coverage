"""Generate one `.qmd` per aerodrome from the ranking tables.

    python scripts/gen_pages.py

Generated pages are **not committed** -- they are build output, and five
hundred generated files would bury every real diff. `.gitignore` excludes
`site/airports/*.qmd` apart from the index.

Each page is three lines that call `site/_airport.py:render`, so the layout is
one edit rather than five hundred.
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

import pandas as pd  # noqa: E402

from oac.aggregate import MIN_N  # noqa: E402

DATA = REPO / "data"
OUT = REPO / "site" / "airports"

TEMPLATE = '''---
title: "{icao}{dash}{name}"
subtitle: "{subtitle}"
---

```{{python}}
#| echo: false
import sys
sys.path.insert(0, ".")
import _airport
_airport.render("{icao}")
```

[← back to rankings](../index.qmd)
'''


@dataclass(frozen=True)
class Page:
    icao: str
    name: str
    tier: str
    n_gt: int

    @property
    def header(self) -> str:
        if self.tier == "A":
            return (f"Tier A · {self.n_gt:,} movements · milestones measured "
                    f"from APDF")
        return (f"Tier B · {self.n_gt:,} movements · NM-inferred milestones, "
                f"no capture metrics")


def pages_for(tbl: pd.DataFrame):
    """One `Page` per aerodrome above the threshold, best-ranked first.

    The same `MIN_N` the ranking tables apply. An aerodrome below it gets no
    page at all rather than a page of empty charts: a per-aerodrome percentile
    over single-digit movements is noise wearing the same formatting as a
    finding.
    """
    for _, r in tbl.iterrows():
        n = r.get("n_gt")
        if pd.isna(n) or n < MIN_N:
            continue
        name = r.get("name")
        name = "" if pd.isna(name) else str(name)
        yield Page(
            icao=str(r["icao"]),
            name=name,
            tier="A" if r.get("t_source") == "apdf" else "B",
            n_gt=int(n),
        )


def _load_tables(period: str) -> pd.DataFrame:
    frames = []
    for tier in ("a", "b"):
        p = DATA / f"ranking_tier_{tier}_{period}.csv"
        if p.is_file():
            frames.append(pd.read_csv(p))
    if not frames:
        raise SystemExit(
            f"No ranking tables for {period} in {DATA}. Run scripts/aggregate.py."
        )
    return pd.concat(frames, ignore_index=True)


def latest_period() -> str:
    found = sorted(
        (p.stem.split("_")[-1] for p in DATA.glob("ranking_tier_a_*.csv")),
        reverse=True,
    )
    if not found:
        raise SystemExit(f"No ranking_tier_a_*.csv in {DATA}.")
    return found[0]


def write_pages(pages, out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("*.qmd"):
        if stale.name != "index.qmd":
            stale.unlink()
    n = 0
    listing = []
    for pg in pages:
        (out_dir / f"{pg.icao}.qmd").write_text(TEMPLATE.format(
            icao=pg.icao,
            dash=" — " if pg.name else "",
            name=pg.name,
            subtitle=pg.header,
        ))
        listing.append(pg)
        n += 1

    rows = "\n".join(
        f"| [{p.icao}]({p.icao}.qmd) | {p.name} | {p.tier} | {p.n_gt:,} |"
        for p in listing
    )
    (out_dir / "index.qmd").write_text(
        "---\ntitle: \"Aerodromes\"\n---\n\n"
        f"{len(listing)} aerodromes with at least {MIN_N} movements.\n\n"
        "| ICAO | Name | Tier | Movements |\n|---|---|---|---|\n" + rows + "\n"
    )
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--period", default=None, help="default: the newest")
    ap.add_argument("--limit", type=int, default=None,
                    help="generate only the first N pages (for a quick render)")
    args = ap.parse_args()

    period = args.period or latest_period()
    tbl = _load_tables(period)
    pages = list(pages_for(tbl))
    if args.limit:
        pages = pages[: args.limit]
    n = write_pages(pages, OUT)
    tier_a = sum(1 for p in pages if p.tier == "A")
    print(f"{n} pages for {period}: {tier_a} tier A, {n - tier_a} tier B")


if __name__ == "__main__":
    main()
