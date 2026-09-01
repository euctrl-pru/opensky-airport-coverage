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
    """A legend, but only when there is something to name.

    Calling `legend()` on an axis with no labelled artists emits a UserWarning
    and draws an empty box -- which happened wherever an aerodrome had no data
    for a side, and produced a blank figure with an empty legend rather than
    no figure.

    The legend is kept for a single series too, which departs from the usual
    "one series needs no legend" rule and does so deliberately: the series name
    here is the *period*, and the page title names the aerodrome, not the year.
    Dropping it would leave a chart whose year is nowhere on it.
    """
    handles, labels = ax.get_legend_handles_labels()
    if not labels:
        return None
    leg = ax.legend(frameon=False, fontsize=8.5, loc="upper right")
    for txt in leg.get_texts():
        txt.set_color(INK)
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
    drawn = 0
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
        drawn += 1
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
    if not drawn:
        # Nothing to show. Returning the figure anyway would put a blank,
        # axis-only chart on the page, which reads as "no coverage" rather
        # than "no data".
        plt.close(fig)
        return None, overflow
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


def flight_coverage(ex):
    """One flight as a timeline, with each taxi shaded by what arrived.

    **The shading is a proportion, not a plot of report times.** The committed
    example tracks are decimated to 30 s for the maps, so the real 5-second
    stream is not on disk and drawing individual ticks from what is would
    invent a pattern the data cannot support. The filled part of each bar is
    the fraction received; where inside the taxi the gaps fell is a question
    this figure deliberately does not answer, and `Taxi-out spanned` on the
    aerodrome pages is the column that does.
    """
    out_s, in_s = ex["taxi_out_s"], ex["taxi_in_s"]
    air_s = max((ex["t_land"] - ex["t_off"]).total_seconds(), 1.0)
    # The airborne leg is compressed: an hour of cruise drawn to scale leaves
    # the two taxis -- the whole subject -- as slivers a reader cannot see.
    air_draw = min(air_s, 0.45 * (out_s + in_s))

    fig, ax = plt.subplots(figsize=(7.2, 1.9), dpi=DPI)
    x = 0.0
    for label, width, frac in (
        ("taxi-out", out_s, min(ex["dep_signal"], 1.0)),
        ("airborne", air_draw, None),
        ("taxi-in", in_s, min(ex["arr_signal"], 1.0)),
    ):
        if frac is None:
            ax.barh(0, width, left=x, height=0.5, color=GRID,
                    edgecolor=GRID)
            ax.text(x + width / 2, 0, "airborne", ha="center", va="center",
                    color=INK_MUTED, fontsize=8.5)
        else:
            # The whole taxi, then the received share drawn over it.
            ax.barh(0, width, left=x, height=0.5, color="#ffffff",
                    edgecolor=REFERENCE, linewidth=0.8)
            ax.barh(0, width * frac, left=x, height=0.5,
                    color=PERIOD_COLORS["2026"], edgecolor="none")
            ax.text(x + width / 2, -0.42, f"{label}  {frac:.2f}",
                    ha="center", va="top", color=INK, fontsize=9)
        x += width

    for pos, name in ((0.0, "off stand"), (out_s, "wheels off"),
                      (out_s + air_draw, "wheels on"),
                      (out_s + air_draw + in_s, "on stand")):
        ax.plot([pos, pos], [-0.25, 0.25], color=INK_MUTED, linewidth=0.9)
        ax.text(pos, 0.42, name, ha="center", va="bottom",
                color=INK_MUTED, fontsize=8)

    ax.set_xlim(-0.04 * x, 1.04 * x)
    ax.set_ylim(-0.95, 0.95)
    ax.axis("off")
    fig.tight_layout()
    return fig
