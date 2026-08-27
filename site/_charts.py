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


def by_hour(series_by_period, ylabel="median off_s (s)", zero_line=True):
    """A quantity against hour of day, one line per period.

    Where a receiver outage or a night-movement effect lives -- a single daily
    median hides both.
    """
    fig, ax = plt.subplots(figsize=FIGSIZE, dpi=DPI)
    drawn = 0
    for period, s in series_by_period.items():
        if s is None or len(s) == 0:
            continue
        ax.plot(list(s.index), list(s.values), linewidth=2.0, marker="o",
                markersize=4.5, color=PERIOD_COLORS.get(period, REFERENCE),
                label=period)
        drawn += 1
    if not drawn:
        plt.close(fig)
        return None
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


# --- H3 surface coverage ---------------------------------------------------

#: Sequential ramps, light -> dark, from the reference palette's blue and
#: orange. Sequential because the quantity is magnitude, not identity; two
#: hues because two sequential contexts appear at once and the second takes
#: the next categorical slot's hue.
GROUND_RAMP = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#0d366b"]
LOW_RAMP = ["#fbe0d3", "#f6bfa4", "#f09b73", "#eb6834", "#c14e21", "#7d3315"]

LAYER_RAMPS = {"ground": GROUND_RAMP, "low": LOW_RAMP}
LAYER_TITLES = {
    "ground": "On the ground (apron, taxiway, runway)",
    "low": "Airborne below 1,500 ft (approach and climb)",
}

#: Resolution to draw each layer at. None keeps the stored resolution.
#: The airborne layer is coarsened because it covers an area ten times wider,
#: where a 28 m cell is a speck.
LAYER_DRAW_RES = {"ground": None, "low": 9}


def _scale_bar(ax, lat_scale, frac=0.25):
    """A distance bar, because the two panels are at different zooms."""
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    span_km = (x1 - x0) * lat_scale * 111.32
    target = span_km * frac
    nice = min([0.2, 0.5, 1, 2, 5, 10, 20, 50],
               key=lambda v: abs(v - target))
    dx = nice / 111.32 / lat_scale
    xs = x0 + (x1 - x0) * 0.06
    ys = y0 + (y1 - y0) * 0.06
    ax.plot([xs, xs + dx], [ys, ys], color=INK, linewidth=2.0,
            solid_capstyle="butt")
    ax.annotate(f"{nice:g} km", xy=(xs + dx / 2, ys), xytext=(0, 4),
                textcoords="offset points", ha="center", fontsize=8,
                color=INK_MUTED)


def _ramp(colors):
    from matplotlib.colors import LinearSegmentedColormap

    return LinearSegmentedColormap.from_list("oac", colors, N=256)


def h3_map(cells, layers=("ground", "low"), title=None):
    """Observed H3 cells over an aerodrome, one panel per layer.

    `cells` is a frame with `h3`, `layer`, `n`. Real hexagons via
    `h3.h3_to_geo_boundary` -- the v3 API, which is what this project pins;
    see the packaging notes. Returns None when there is nothing to draw, so
    the page omits the figure rather than showing an empty axis.

    **Log-scaled fill.** One apron cell can hold thousands of reports while a
    runway threshold holds tens; on a linear ramp everything but the stand
    renders as empty, which is exactly the detail the map exists to show.

    A colourbar is present because this is the one chart on the site where
    colour carries the value rather than the series identity.
    """
    import h3
    from matplotlib.collections import PolyCollection
    from matplotlib.colors import LogNorm

    have = [lay for lay in layers
            if not cells[cells["layer"] == lay].empty]
    if not have:
        return None

    fig, axes = plt.subplots(
        1, len(have), figsize=(5.9 * len(have), 4.9), dpi=DPI, squeeze=False,
    )
    axes = axes[0]

    for ax, lay in zip(axes, have):
        sub = cells[cells["layer"] == lay]

        # The airborne layer is rolled up before drawing. It spans an approach
        # some tens of kilometres across, where a 28 m cell is a speck: the
        # panel renders as scattered dust rather than as a corridor. The
        # surface layer is left at its stored resolution, because resolving
        # individual taxiways is the whole point of it.
        draw_res = LAYER_DRAW_RES.get(lay)
        if draw_res is not None:
            rolled = {}
            for cell, n in zip(sub["h3"], sub["n"]):
                if h3.h3_get_resolution(cell) <= draw_res:
                    parent = cell
                else:
                    parent = h3.h3_to_parent(cell, draw_res)
                rolled[parent] = rolled.get(parent, 0) + int(n)
            pairs = list(rolled.items())
        else:
            pairs = [(c, int(n)) for c, n in zip(sub["h3"], sub["n"])]

        polys, vals, lats, lons = [], [], [], []
        for cell, n in pairs:
            b = h3.h3_to_geo_boundary(cell)
            polys.append([(lon, lat) for lat, lon in b])
            vals.append(max(n, 1))
            for la, lo in b:
                lats.append(la)
                lons.append(lo)

        # **Each panel gets its own extent.** A shared one was tried and is
        # wrong here: the approach spans ~30 km and the surface ~3 km, so one
        # extent squeezes the aerodrome into a few pixels in the corner --
        # losing exactly what the map exists to show. The scale bar on each
        # panel is what stops the different zooms from misleading.
        lat0, lat1 = min(lats), max(lats)
        lon0, lon1 = min(lons), max(lons)
        pad_y = (lat1 - lat0) * 0.06 or 0.002
        pad_x = (lon1 - lon0) * 0.06 or 0.002
        lat_scale = np.cos(np.radians((lat0 + lat1) / 2))

        cmap = _ramp(LAYER_RAMPS.get(lay, GROUND_RAMP))
        norm = LogNorm(vmin=1, vmax=max(vals))
        pc = PolyCollection(polys, array=np.array(vals), cmap=cmap, norm=norm,
                            edgecolors="none")
        ax.add_collection(pc)
        ax.set_xlim(lon0 - pad_x, lon1 + pad_x)
        ax.set_ylim(lat0 - pad_y, lat1 + pad_y)
        # Degrees of longitude shrink with latitude; without this the map is
        # stretched east-west and a runway looks like the wrong shape.
        ax.set_aspect(1.0 / lat_scale)
        ax.set_title(LAYER_TITLES.get(lay, lay), fontsize=9.5, color=INK)
        ax.set_xticks([])
        ax.set_yticks([])
        for s in ax.spines.values():
            s.set_color(GRID)
        _scale_bar(ax, lat_scale)

        cb = fig.colorbar(pc, ax=ax, shrink=0.82, aspect=22, pad=0.02)
        cb.set_label("position reports (log scale)", fontsize=8.5,
                     color=INK_MUTED)
        cb.ax.tick_params(labelsize=8, colors=INK_MUTED)
        cb.outline.set_visible(False)

    if title:
        fig.suptitle(title, fontsize=10.5, color=INK)
    fig.tight_layout()
    return fig
