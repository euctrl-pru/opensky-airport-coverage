"""Generate one `.qmd` per aerodrome from the ranking tables.

    python scripts/gen_pages.py

Generated pages are **not committed** -- they are build output, and five
hundred generated files would bury every real diff. `.gitignore` excludes
`site/airports/*.qmd` apart from the index.

Each page is three lines that call `site/_airport.py:render`, so the layout is
one edit rather than five hundred.
"""

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

import pandas as pd  # noqa: E402

sys.path.insert(0, str(REPO / "site"))

import _charts  # noqa: E402
import _maps  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

from oac.aggregate import MIN_N, capture  # noqa: E402
from oac.page import CLIP_S, build_page  # noqa: E402

DATA = REPO / "data"
OUT = REPO / "site" / "airports"
#: Per-aerodrome slices, written here and read by one page each.
SLICES = DATA / "pages"
#: Pre-rendered figures, one directory beside the generated pages.
FIGS = OUT / "figures"

#: Pure markdown -- no executable cell. See `oac.page` for why.
TEMPLATE = '''---
title: {title}
subtitle: {subtitle}
---

{body}
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
            return (f"Tier A (measured) · {self.n_gt:,} movements · milestones measured "
                    f"from APDF")
        return (f"Tier B (estimated) · {self.n_gt:,} movements · NM-inferred milestones, "
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
    # De-duplicate on ICAO. The all-aerodromes ranking deliberately includes
    # the measured aerodromes, so concatenating the two files lists those
    # twice -- which generated their pages twice and reported 138 measured
    # aerodromes where there are 69. The measured row is kept because it
    # carries the ground-coverage columns the page needs.
    return _dedupe_rankings(pd.concat(frames, ignore_index=True))


def _dedupe_rankings(out):
    """One row per aerodrome, preferring the measured one."""
    out = out.copy()
    out["_measured_first"] = (out["t_source"] != "apdf").astype(int)
    return (out.sort_values("_measured_first")
               .drop_duplicates("icao", keep="first")
               .drop(columns="_measured_first")
               .reset_index(drop=True))


def latest_period() -> str:
    found = sorted(
        (p.stem.split("_")[-1] for p in DATA.glob("ranking_tier_a_*.csv")),
        reverse=True,
    )
    if not found:
        raise SystemExit(f"No ranking_tier_a_*.csv in {DATA}.")
    return found[0]


def write_slices(pages, periods_present: list) -> None:
    """One small parquet per aerodrome, plus the fleet reference.

    Without this every page re-read the whole per-flight table -- six times,
    once per period per side -- and then recomputed fleet-wide capture to draw
    its ECDF reference line. That is O(all flights) per page, and there are
    hundreds of pages. Slicing once here turns the render from quadratic into
    linear, and each page reads a few hundred rows instead of a hundred
    thousand.

    Slices are build output and gitignored, like the pages themselves.
    """
    SLICES.mkdir(parents=True, exist_ok=True)
    for stale in SLICES.glob("*.parquet"):
        stale.unlink()

    wanted = {p.icao for p in pages}
    frames = []
    for period in periods_present:
        d = pd.read_parquet(DATA / f"flight_offsets_{period}.parquet")
        frames.append(capture(d))
    allf = pd.concat(frames, ignore_index=True)

    # The fleet reference for the capture ECDFs: the latest period only, since
    # that is what a page compares itself against.
    latest = periods_present[0]
    fleet = allf[allf["period"] == latest][["dep_continuity", "arr_continuity"]]
    fleet.to_parquet(SLICES / "_fleet.parquet", index=False)

    dep = allf[allf["gt_adep"].isin(wanted)]
    arr = allf[allf["gt_ades"].isin(wanted)]
    for icao in sorted(wanted):
        a = dep[dep["gt_adep"] == icao].assign(_side="dep")
        b = arr[arr["gt_ades"] == icao].assign(_side="arr")
        pd.concat([a, b], ignore_index=True).to_parquet(
            SLICES / f"{icao}.parquet", index=False
        )


def load_h3():
    """`period -> frame` of observed cells, or {} when none are committed."""
    out = {}
    for f in sorted(DATA.glob("h3_cells_*.parquet"), reverse=True):
        out[f.stem.replace("h3_cells_", "")] = pd.read_parquet(f)
    return out


def load_examples():
    """Example trajectories for the latest period, with flight identity.

    The extraction stores geometry and `track_id`; who was flying comes from
    the per-flight table, joined here rather than re-run on the cluster. The
    two share `track_id` exactly -- every example track is present in the
    offsets table -- so this is a lookup, not a match.
    """
    found = sorted(DATA.glob("example_tracks_*.parquet"), reverse=True)
    if not found:
        return pd.DataFrame(columns=["icao", "track_id", "label", "lat", "lon",
                                     "event_time"])
    ex = pd.read_parquet(found[0])
    period = found[0].stem.replace("example_tracks_", "")
    off_path = DATA / f"flight_offsets_{period}.parquet"
    if off_path.is_file():
        ident = (
            pd.read_parquet(off_path)[["track_id", "icao24", "gt_adep",
                                       "gt_ades", "flight_key"]]
            .dropna(subset=["track_id"])
            .drop_duplicates("track_id")
        )
        ex = ex.merge(ident, on="track_id", how="left")
    return ex


def _render_map(icao, cells_latest, examples):
    """The interactive coverage map for one aerodrome.

    Latest period only. Brussels' ground layer alone is 1.26 MB of GeoJSON at
    resolution 11; three periods across two layers for 430 aerodromes projects
    to 3.3 GB against a ~1 GB Pages limit, and the year-on-year comparison is
    already carried by the tables. Returns `(html, note)`.
    """
    sub = cells_latest[cells_latest["icao"] == icao][["h3", "layer", "n"]]
    tracks = examples[examples["icao"] == icao] if len(examples) else None
    if sub.empty and (tracks is None or tracks.empty):
        return None, None
    html = _maps.coverage_map(sub, tracks)
    note = None
    if tracks is None or tracks.empty:
        note = ("*Example flights are shown only where the reference data "
                "records real stand and runway times, so their coverage can be "
                "ranked. This aerodrome has none.*\n")
    return html, note


def _render_figures(icao, frames_by_side, tier, fleet) -> dict:
    """Draw and save this aerodrome's figures; return their filenames.

    Every figure is closed after saving. In one long-lived process drawing
    figures for hundreds of aerodromes, leaving them open is a memory leak with
    no error attached to it.
    """
    figs = {}
    for side, frames in frames_by_side.items():
        if not frames:
            continue
        off_col = "off_s" if side == "dep" else "land_s"
        cap_col = f"{side}_continuity"
        anchor = "t_off" if side == "dep" else "t_land"

        fig, over = _charts.signed_histogram(
            {p_: d[off_col].values for p_, d in frames.items()},
            clip=CLIP_S, xlabel=f"{off_col} (s)",
            zero_label="wheels-off" if side == "dep" else "touchdown",
        )
        figs[f"{side}_hist_overflow"] = over
        if fig is not None:
            name = f"{icao}_{side}_hist.svg"
            fig.savefig(FIGS / name, format="svg", bbox_inches="tight")
            plt.close(fig)
            figs[f"{side}_hist"] = name

        if tier == "A":
            cap = {p_: d[cap_col].dropna().values for p_, d in frames.items()}
            cap = {p_: v for p_, v in cap.items() if len(v)}
            if cap:
                fig = _charts.ecdf(
                    cap, reference=fleet.get(cap_col),
                    xlabel=f"{cap_col} (fraction of ground phase seen)",
                )
                name = f"{icao}_{side}_ecdf.svg"
                fig.savefig(FIGS / name, format="svg", bbox_inches="tight")
                plt.close(fig)
                figs[f"{side}_ecdf"] = name

        hourly = {}
        for p_, d in frames.items():
            s = d.dropna(subset=[off_col])
            if s.empty:
                continue
            g = s.assign(hour=pd.to_datetime(s[anchor]).dt.hour) \
                 .groupby("hour")[off_col].median()
            if len(g) > 1:
                hourly[p_] = g
        if hourly:
            fig = _charts.by_hour(hourly, ylabel=f"median {off_col} (s)")
            if fig is not None:
                name = f"{icao}_{side}_hour.svg"
                fig.savefig(FIGS / name, format="svg", bbox_inches="tight")
                plt.close(fig)
                figs[f"{side}_hour"] = name
    return figs


def write_pages(pages, out_dir: Path, stats_by_period=None,
                rankings=None, latest=None, fleet=None,
                cells_latest=None, examples=None, slices: Path = None) -> int:
    """Write one static-markdown page per aerodrome, with figures beside it.

    `stats_by_period` etc. default to empty, so the page-selection tests can
    call this without any data: they assert which pages exist, not what is on
    them. `slices` is a parameter rather than the module constant for the same
    reason -- a test asserting page *names* should not be reading whatever
    happens to be in `data/pages/`, which is build output and may predate the
    columns the page builder now expects.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    figs_dir = out_dir / "figures"
    figs_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("*.qmd"):
        if stale.name != "index.qmd":
            stale.unlink()
    for stale in figs_dir.glob("*.svg"):
        stale.unlink()

    stats_by_period = stats_by_period or {}
    rankings = rankings or {}
    fleet = fleet or {}
    examples = examples if examples is not None else pd.DataFrame(columns=["icao"])
    slices = SLICES if slices is None else slices

    n = 0
    listing = []
    for pg in pages:
        stats = {}
        for period, tbl in stats_by_period.items():
            hit = tbl[tbl.icao == pg.icao]
            if len(hit):
                stats[period] = hit.iloc[0]

        frames_by_side = {}
        slice_path = slices / f"{pg.icao}.parquet"
        if slice_path.is_file():
            sl = pd.read_parquet(slice_path)
            sl = sl[sl["detected"].fillna(False).astype(bool)]
            for side in ("dep", "arr"):
                s = sl[sl["_side"] == side]
                frames_by_side[side] = {
                    p_: g for p_, g in
                    sorted(s.groupby("period"), key=lambda kv: kv[0], reverse=True)
                }

        figs = (_render_figures(pg.icao, frames_by_side, pg.tier, fleet)
                if frames_by_side else {})
        if cells_latest is not None:
            figs["map_html"], figs["tracks_note"] = _render_map(
                pg.icao, cells_latest, examples)
            # Distinguishes "we have H3 data and this aerodrome has none"
            # from "no H3 data was computed at all" -- only the first is a
            # statement about coverage.
            figs["map_expected"] = True
        body = build_page(
            tier=pg.tier, stats=stats, frames_by_side=frames_by_side,
            ranking=rankings.get("a" if pg.tier == "A" else "b"),
            latest=latest, figs=figs,
        ) if stats else "*No statistics for this aerodrome.*\n"

        # YAML scalars via json.dumps. Aerodrome names are free text from
        # OurAirports and contain characters YAML treats as syntax: Rhodes is
        # literally `Rhodes International Airport "Diagoras"`, whose embedded
        # quotes ended the title early and failed the whole project render.
        title = pg.icao + (f" -- {pg.name}" if pg.name else "")
        (out_dir / f"{pg.icao}.qmd").write_text(TEMPLATE.format(
            title=json.dumps(title, ensure_ascii=False),
            subtitle=json.dumps(pg.header, ensure_ascii=False),
            body=body,
        ))
        listing.append(pg)
        n += 1

    def _cell(name: str) -> str:
        """A pipe in a name would end the markdown cell; escape it.

        Hoisted out of the f-string because Python 3.10 rejects a backslash
        inside an f-string expression, and 3.10 is what the cluster runs.
        """
        return name.replace("|", "\\|")

    rows = "\n".join(
        f"| [{p.icao}]({p.icao}.qmd) | {_cell(p.name)} | "
        f"{p.tier} | {p.n_gt:,} |"
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

    periods_present = sorted(
        (f.stem.replace("flight_offsets_", "")
         for f in DATA.glob("flight_offsets_*.parquet")),
        reverse=True,
    )
    write_slices(pages, periods_present)

    stats_by_period = {}
    for p_ in periods_present:
        f = DATA / f"airport_stats_{p_}.csv"
        if f.is_file():
            stats_by_period[p_] = pd.read_csv(f)
    rankings = {}
    for tier in ("a", "b"):
        f = DATA / f"ranking_tier_{tier}_{period}.csv"
        if f.is_file():
            rankings[tier] = pd.read_csv(f)
    fleet_path = SLICES / "_fleet.parquet"
    fleet = {}
    if fleet_path.is_file():
        fl = pd.read_parquet(fleet_path)
        fleet = {c: fl[c].dropna().values for c in fl.columns}

    h3_by_period = load_h3()
    cells_latest = h3_by_period.get(periods_present[0])
    if cells_latest is not None:
        print(f"  H3 cells ({periods_present[0]}): {len(cells_latest):,} rows, "
              f"{cells_latest.icao.nunique()} aerodromes")
    examples = load_examples()
    if len(examples):
        print(f"  example tracks: {examples.track_id.nunique():,} across "
              f"{examples.icao.nunique()} aerodromes")

    n = write_pages(pages, OUT, stats_by_period=stats_by_period,
                    rankings=rankings, latest=periods_present[0], fleet=fleet,
                    cells_latest=cells_latest, examples=examples)
    tier_a = sum(1 for p in pages if p.tier == "A")
    print(f"{n} pages for {period}: {tier_a} tier A, {n - tier_a} tier B")


if __name__ == "__main__":
    main()
