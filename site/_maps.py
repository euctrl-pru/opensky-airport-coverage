"""Interactive coverage maps: H3 hexagons and example trajectories on a basemap.

One map per aerodrome, for the **latest period only**. That is a measured
decision, not a shortcut: Brussels' ground layer alone is 1.26 MB of GeoJSON at
resolution 11, and three periods across two layers for 430 aerodromes projects
to 3.3 GB against GitHub Pages' ~1 GB limit. The year-on-year comparison is
already carried, numerically and with deltas, by the tables -- two extra maps
per page would add weight and clutter without adding a finding.

Most aerodromes are cheap: the median aerodrome-layer has **182** cells, not
Brussels' 3,163. So resolution 11 is kept -- resolving individual taxiways is
the point of the ground map -- and only aerodromes above `MAX_CELLS` are rolled
up, which bounds the worst pages without coarsening the typical one.

`plotly.js` is loaded from a CDN rather than inlined; inlining it would add
~3 MB to every one of 430 pages.
"""

# Imported at module level, not inside the functions that use them. A lazy
# import defers the failure to call time, which is why a missing `plotly`
# survived every dependency check and only surfaced in CI, mid-build, on the
# first aerodrome. Importing here means `import _maps` fails immediately and
# `tests/test_imports.py` catches it.
import h3
import numpy as np
import pandas as pd
import plotly.graph_objects as go

#: Roll a layer up one resolution beyond this many cells. Chosen so the median
#: aerodrome (182 cells) is untouched and only large hubs are coarsened.
MAX_CELLS = 2500

DISPLAY_RES = 11
COARSE_RES = 10

#: Same hues as the static charts: blue for the surface, orange for the air.
GROUND_SCALE = [[0.0, "#cde2fb"], [0.35, "#6da7ec"], [0.7, "#2a78d6"],
                [1.0, "#0d366b"]]
LOW_SCALE = [[0.0, "#fbe0d3"], [0.35, "#f09b73"], [0.7, "#eb6834"],
             [1.0, "#7d3315"]]

#: Trajectory colours by how well that movement was observed. Deliberately not
#: the layer hues -- these are a different kind of thing on the same canvas.
TRACK_COLORS = {"best": "#1baf7a", "median": "#eda100", "worst": "#e34948"}
TRACK_LABELS = {"best": "best observed", "median": "typical",
                "worst": "worst observed"}

__all__ = ["MAX_CELLS", "coverage_map"]


def _rollup(df, res):
    if df.empty:
        return df
    parent = [c if h3.h3_get_resolution(c) <= res else h3.h3_to_parent(c, res)
              for c in df["h3"]]
    return (df.assign(h3=parent).groupby("h3", as_index=False)["n"].sum())


def _geojson(cells):
    """GeoJSON for a set of H3 cells, coordinates rounded to ~1 m.

    Six decimals is ~0.1 m, finer than the position data and a third of the
    payload for nothing.
    """
    feats = []
    for c in cells:
        b = h3.h3_to_geo_boundary(c)
        ring = [[round(lon, 5), round(lat, 5)] for lat, lon in b]
        ring.append(ring[0])
        feats.append({"type": "Feature", "id": c, "properties": {},
                      "geometry": {"type": "Polygon", "coordinates": [ring]}})
    return {"type": "FeatureCollection", "features": feats}


def _log_colorbar(zmax, x, title):
    """Ticks at powers of ten, labelled with real counts.

    The colour axis is log10 because one apron cell holds thousands of reports
    while a runway threshold holds tens. The reader should never have to undo
    that in their head, so the bar is labelled 1 / 10 / 100 / ... rather than
    0 / 1 / 2.
    """
    decades = list(range(0, int(np.ceil(zmax)) + 1))
    return dict(
        title=dict(text=title, side="right", font=dict(size=11)),
        tickvals=decades,
        ticktext=[f"{10 ** d:,}" for d in decades],
        thickness=12, len=0.75, x=x, xanchor="left",
        tickfont=dict(size=10), outlinewidth=0,
    )


def _layer_trace(df, name, scale, visible, cbar_x, cbar_title):
    z = np.log10(df["n"].clip(lower=1))
    return go.Choroplethmap(
        geojson=_geojson(df["h3"]), locations=df["h3"], z=z,
        colorscale=scale, marker_line_width=0, marker_opacity=0.7,
        # A legend entry as well as a colourbar: the colourbar says what the
        # shades mean, the legend entry is what lets a reader switch the layer
        # off to see the basemap underneath it.
        name=name, visible=visible, showlegend=True, legendgroup=name,
        showscale=True, colorbar=_log_colorbar(float(z.max()), cbar_x, cbar_title),
        customdata=df["n"],
        hovertemplate="%{customdata:,} position reports<extra>" + name + "</extra>",
    )


def _hover_rows(g):
    """Per-report hover fields: who, when, and how high.

    Built as a list rather than a template over the frame because a missing
    column must degrade to a dash rather than raise -- the identity join is a
    left join, and an example track whose flight row is absent should still
    draw.
    """
    def _get(col, default="—"):
        return g[col] if col in g.columns else pd.Series([default] * len(g),
                                                         index=g.index)

    icao24 = _get("icao24").fillna("unknown")
    adep = _get("gt_adep").fillna("?")
    ades = _get("gt_ades").fillna("?")
    who = [f"{a} · {d} → {s}" for a, d, s in zip(icao24, adep, ades)]

    when = pd.to_datetime(g["event_time"]).dt.strftime("%Y-%m-%d %H:%M:%S")

    on_gnd = _get("on_ground", False).fillna(False).astype(bool)
    alt_m = pd.to_numeric(_get("baro_altitude_c", np.nan), errors="coerce")
    where = [
        "on the ground" if og else
        ("airborne, altitude unknown" if pd.isna(a)
         else f"{a * 3.28084:,.0f} ft")
        for og, a in zip(on_gnd, alt_m)
    ]

    tid = _get("track_id").astype(str).str.slice(0, 12)
    return list(zip(who, when, where, tid))


def coverage_map(cells, tracks=None, height=520):
    """An interactive map of one aerodrome's observed coverage.

    `cells` has `h3`, `layer`, `n`. `tracks` optionally has `lat`, `lon`,
    `track_id`, `label`, `side`. Returns an HTML fragment, or None when there
    is nothing to draw.

    What is shown on opening: the ground hexagons and the example flights. The
    airborne layer starts hidden because it covers ten times the area and,
    drawn on top, hides the surface detail the map exists for. The example
    flights start shown -- six thin paths do not crowd the hexagons, and a
    layer that starts hidden is a layer most readers never discover. Each
    flight is its own legend entry, so any of them can be switched off
    individually.
    """
    cells = cells[cells["layer"].isin(("ground", "low"))]
    if cells.empty and (tracks is None or tracks.empty):
        return None

    fig = go.Figure()
    lats, lons = [], []

    for layer, scale in (("ground", GROUND_SCALE), ("low", LOW_SCALE)):
        sub = cells[cells["layer"] == layer][["h3", "n"]]
        if sub.empty:
            continue
        if len(sub) > MAX_CELLS:
            sub = _rollup(sub, COARSE_RES)
        name = ("On the ground" if layer == "ground"
                else "Airborne below 1,500 ft")
        # The airborne layer starts hidden. It covers ten times the area, so
        # drawn on top it hides the surface detail that the map exists for; a
        # legend click brings it back.
        # Two colourbars would otherwise sit on top of each other; the second
        # is offset so both are readable when both layers are shown.
        cbar_x = 1.01 if layer == "ground" else 1.13
        title = "reports on ground" if layer == "ground" else "reports airborne"
        fig.add_trace(_layer_trace(
            sub, name, scale,
            True if layer == "ground" else "legendonly", cbar_x, title))
        for c in sub["h3"]:
            la, lo = h3.h3_to_geo(c)
            lats.append(la)
            lons.append(lo)

    if tracks is not None and not tracks.empty:
        for (tid, label), g in tracks.groupby(["track_id", "label"], sort=False):
            g = g.sort_values("event_time")
            colour = TRACK_COLORS.get(label, "#52514e")
            band = TRACK_LABELS.get(label, label)

            # One trace per flight: a solid line through its reports with the
            # reports drawn on it. One trace rather than two because each
            # flight gets its own legend entry -- a separate line and marker
            # trace would need two clicks to switch one flight off.
            icao24 = (g["icao24"].dropna().iloc[0]
                      if "icao24" in g.columns and g["icao24"].notna().any()
                      else str(tid)[:8])
            side = (g["side"].iloc[0] if "side" in g.columns else "")
            name = f"{band} · {icao24}" + (f" ({side})" if side else "")

            fig.add_trace(go.Scattermap(
                lat=g["lat"].round(5), lon=g["lon"].round(5),
                mode="lines+markers",
                line=dict(width=2, color=colour),
                marker=dict(size=8, color=colour, opacity=0.9),
                name=name, showlegend=True,
                customdata=_hover_rows(g),
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"      # icao24 . route
                    "%{customdata[1]}<br>"             # time
                    "%{customdata[2]}<br>"             # altitude / on ground
                    "track %{customdata[3]}"
                    f"<extra>{name}</extra>"
                ),
            ))
        lats += list(tracks["lat"])
        lons += list(tracks["lon"])

    if not lats:
        return None

    fig.update_layout(
        map=dict(style="carto-positron",
                 center=dict(lat=float(np.median(lats)),
                             lon=float(np.median(lons))),
                 zoom=11.5),
        margin=dict(l=0, r=0, t=0, b=0), height=height,
        legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0,
                    font=dict(size=11), itemsizing="constant"),
        showlegend=True,
    )
    return fig.to_html(full_html=False, include_plotlyjs="cdn",
                       config={"displayModeBar": False, "scrollZoom": True})


# --- the ingested area, and where the ranked aerodromes are ---------------

#: The colours the rating bands take on the overview map. A sequential ramp,
#: because the bands are ordered magnitudes of one quantity, not identities.
RATING_COLORS = {
    "Excellent": "#0d366b",
    "Good": "#2a78d6",
    "Partial": "#6da7ec",
    "Poor": "#eda100",
    "None": "#e34948",
    # Aerodromes whose ground coverage cannot be measured at all. Grey, and
    # last in the legend, because this is an absence of information rather
    # than a poor result -- putting it on the same ramp would read as "worse
    # than None", which is a different and wrong statement.
    "—": "#b6b5ae",
}
RATING_ORDER = ["Excellent", "Good", "Partial", "Poor", "None", "—"]
RATING_LEGEND = {"—": "ground coverage not measured"}


def overview_map(airports, bbox, height=560):
    """Every ranked aerodrome on the map, inside the box that was sampled.

    Two things at once, and deliberately: the boundary of what was ingested --
    which is why an aerodrome outside it is absent rather than ranked last --
    and how coverage is distributed across the aerodromes inside it.

    `airports` needs `lat`, `lon`, `icao`, `name`, `rating`, `n_gt`,
    `coverage_index`.
    """
    df = airports.dropna(subset=["lat", "lon"])
    if df.empty:
        return None

    min_lon, min_lat, max_lon, max_lat = bbox
    fig = go.Figure()

    # The box first, so the aerodromes draw over it.
    fig.add_trace(go.Scattermap(
        lat=[min_lat, min_lat, max_lat, max_lat, min_lat],
        lon=[min_lon, max_lon, max_lon, min_lon, min_lon],
        mode="lines", line=dict(width=2, color="#52514e"),
        name="ingested area", hoverinfo="skip",
    ))

    for band in RATING_ORDER:
        sub = df[df["rating"] == band]
        if sub.empty:
            continue
        fig.add_trace(go.Scattermap(
            lat=sub["lat"], lon=sub["lon"], mode="markers",
            marker=dict(size=5 if band == "—" else 7,
                        color=RATING_COLORS[band],
                        opacity=0.6 if band == "—" else 0.85),
            name=RATING_LEGEND.get(band, band),
            customdata=np.stack([
                sub["icao"], sub["name"].fillna(""),
                sub["n_gt"].fillna(0).astype(int),
                sub["coverage_index"].round(3).fillna(-1),
            ], axis=-1),
            hovertemplate=(
                "<b>%{customdata[0]}</b> %{customdata[1]}<br>"
                "%{customdata[2]} movements<br>"
                "coverage index %{customdata[3]}"
                f"<extra>{RATING_LEGEND.get(band, band)}</extra>"
            ),
        ))

    fig.update_layout(
        map=dict(style="carto-positron",
                 center=dict(lat=(min_lat + max_lat) / 2,
                             lon=(min_lon + max_lon) / 2),
                 zoom=2.4),
        margin=dict(l=0, r=0, t=0, b=0), height=height,
        legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0,
                    font=dict(size=11), itemsizing="constant"),
    )
    return fig.to_html(full_html=False, include_plotlyjs="cdn",
                       config={"displayModeBar": False, "scrollZoom": True})
