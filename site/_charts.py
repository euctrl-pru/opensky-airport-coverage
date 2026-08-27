"""Chart primitives, shared by every page so ~500 of them read as one system.

**Palette.** The three categorical slots are the reference theme's first three
(blue, orange, aqua), which are the slots documented to clear the all-pairs
floors in both modes -- and all-pairs is the right list here because the period
series are overlaid on one plot, not stacked. Validated rather than eyeballed:

    node scripts/validate_palette.js "#2a78d6,#eb6834,#1baf7a" --mode light --pairs all
    node scripts/validate_palette.js "#3987e5,#d95926,#199e70" --mode dark  --pairs all

Both report ALL CHECKS PASS. Light mode raises one contrast WARN -- aqua at
2.74:1 against the light surface -- which obliges relief rather than being
dismissable. Relief is satisfied twice over: every chart on this site sits
beside the percentile table it summarises, and each series is direct-labelled
in the legend.

**Static SVG, not an interactive layer.** A deliberate trade-off, stated rather
than defaulted into: the site generates about 500 aerodrome pages, and shipping
a plotting runtime on each would dominate the page weight for charts whose exact
values are already printed in the adjacent table. The interaction that matters
for this data -- sort and filter a ranking -- lives on the ranking tables, which
are interactive.

Colour follows the **period**, never its rank, so a chart missing one period
does not repaint the others.
"""

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

#: Categorical slots, keyed by period so colour follows the entity.
PERIOD_COLORS = {"2026": "#2a78d6", "2025": "#eb6834", "2024": "#1baf7a"}

#: Recessive ink. Text wears text tokens, never a series colour.
INK = "#0b0b0b"
INK_MUTED = "#52514e"
GRID = "#e3e3e0"
#: The fleet reference line: neutral by design. It is context, not a category,
#: and giving it a categorical hue would imply it is another period.
REFERENCE = "#8a8a84"

FIGSIZE = (7.2, 3.4)
DPI = 110


def _style(ax, xlabel="", ylabel=""):
    """Recessive grid and axes; no chartjunk."""
    ax.grid(True, color=GRID, linewidth=0.6, alpha=0.9)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK_MUTED, labelsize=8.5, length=3)
    ax.set_xlabel(xlabel, color=INK_MUTED, fontsize=9)
    ax.set_ylabel(ylabel, color=INK_MUTED, fontsize=9)
    return ax


def _legend(ax):
    leg = ax.legend(frameon=False, fontsize=8.5, loc="upper right")
    for t in leg.get_texts():
        t.set_color(INK)
    return leg


def signed_histogram(series_by_period, clip=1800, bins=48, xlabel="seconds",
                     zero_label=None):
    """Step histograms of a signed quantity, one outline per period.

    Outlines rather than filled bars: three filled histograms on one axis
    occlude each other, and which one is hidden depends on draw order rather
    than on the data.

    `clip` bounds the x-axis. Values beyond it are **excluded from the plot and
    counted**, and the caller prints the count in the caption -- a silently
    truncated tail is exactly where a coverage failure lives.

    Excluded rather than clipped into the edge bin, which is what an earlier
    version did: clipping stacks every outlier onto one bar, and a reader sees
    a tall spike at exactly +/-`clip` that looks like a real mode in the data
    rather than the edge of the axis. Density therefore normalises over the
    in-range values, which is why the count is stated rather than implied.

    Returns `(fig, overflow)` where overflow maps period -> (n_below, n_above).
    """
    fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
    edges = np.linspace(-clip, clip, bins + 1)
    overflow = {}
    for period, values in series_by_period.items():
        v = np.asarray(values, dtype=float)
        v = v[~np.isnan(v)]
        if v.size == 0:
            overflow[period] = (0, 0)
            continue
        overflow[period] = (int((v < -clip).sum()), int((v > clip).sum()))
        inside = v[(v >= -clip) & (v <= clip)]
        if inside.size == 0:
            continue
        ax.hist(inside, bins=edges, histtype="step",
                linewidth=2.0, color=PERIOD_COLORS.get(period, REFERENCE),
                label=period, density=True)
    # Zero is the whole point of a signed axis: it is where "before" becomes
    # "after". Drawn as a reference, in ink rather than a series colour.
    ax.axvline(0, color=INK, linewidth=1.2, linestyle=(0, (4, 3)), alpha=0.7)
    if zero_label:
        ax.annotate(zero_label, xy=(0, 1.0), xycoords=("data", "axes fraction"),
                    xytext=(4, -10), textcoords="offset points",
                    fontsize=8, color=INK_MUTED)
    _style(ax, xlabel=xlabel, ylabel="density")
    _legend(ax)
    fig.tight_layout()
    return fig, overflow


def ecdf(series_by_period, reference=None, xlabel="fraction",
         reference_label="all aerodromes"):
    """Empirical CDFs, one line per period, with an optional neutral reference.

    An ECDF rather than a histogram because capture is bounded in [0, 1] and
    piles up at both ends: the reader's question is "what share of movements
    were at least half captured", which an ECDF answers by inspection.

    `reference` is the whole fleet's distribution, drawn neutral and dashed
    behind the series. A curve **below** the reference is better -- fewer of
    its movements fall below any given capture level. The label says "all
    aerodromes" and not "fleet median", which an earlier version used and which
    described a single number rather than the distribution actually drawn.
    """
    fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
    if reference is not None:
        r = np.sort(np.asarray(reference, dtype=float))
        r = r[~np.isnan(r)]
        if r.size:
            ax.plot(r, np.arange(1, r.size + 1) / r.size, linewidth=1.6,
                    color=REFERENCE, linestyle=(0, (5, 3)),
                    label=reference_label, zorder=1)
    for period, values in series_by_period.items():
        v = np.sort(np.asarray(values, dtype=float))
        v = v[~np.isnan(v)]
        if v.size == 0:
            continue
        ax.plot(v, np.arange(1, v.size + 1) / v.size, linewidth=2.0,
                color=PERIOD_COLORS.get(period, REFERENCE), label=period,
                zorder=2)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    _style(ax, xlabel=xlabel, ylabel="cumulative share of movements")
    _legend(ax)
    fig.tight_layout()
    return fig


def by_hour(series_by_period, ylabel="median off_s (s)", zero_line=True):
    """A quantity against hour of day, one line per period.

    Where a receiver outage or a night-movement effect lives -- a single daily
    median hides both.
    """
    fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
    for period, s in series_by_period.items():
        if s is None or len(s) == 0:
            continue
        ax.plot(list(s.index), list(s.values), linewidth=2.0, marker="o",
                markersize=4.5, color=PERIOD_COLORS.get(period, REFERENCE),
                label=period)
    if zero_line:
        ax.axhline(0, color=INK, linewidth=1.2, linestyle=(0, (4, 3)), alpha=0.7)
    ax.set_xticks(range(0, 24, 3))
    ax.set_xlim(-0.5, 23.5)
    _style(ax, xlabel="hour of day (UTC)", ylabel=ylabel)
    _legend(ax)
    fig.tight_layout()
    return fig


def fleet_distribution(values, xlabel, bins=30, highlight=None,
                       highlight_label=None):
    """One aerodrome against the fleet: a histogram with an optional marker.

    Answers the question a bare number cannot -- whether 200 s is good here --
    by putting the aerodrome's own value on the fleet's distribution.
    """
    fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
    v = np.asarray(values, dtype=float)
    v = v[~np.isnan(v)]
    ax.hist(v, bins=bins, color=PERIOD_COLORS["2026"], alpha=0.85,
            edgecolor="white", linewidth=0.8)
    if highlight is not None and not np.isnan(highlight):
        ax.axvline(highlight, color=PERIOD_COLORS["2025"], linewidth=2.4)
        ax.annotate(highlight_label or "this aerodrome",
                    xy=(highlight, 1.0), xycoords=("data", "axes fraction"),
                    xytext=(5, -12), textcoords="offset points",
                    fontsize=8.5, color=INK)
    _style(ax, xlabel=xlabel, ylabel="aerodromes")
    fig.tight_layout()
    return fig
