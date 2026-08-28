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

import numpy as np
import pandas as pd

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
    import h3

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
    import h3

    feats = []
    for c in cells:
        b = h3.h3_to_geo_boundary(c)
        ring = [[round(lon, 5), round(lat, 5)] for lat, lon in b]
        ring.append(ring[0])
        feats.append({"type": "Feature", "id": c, "properties": {},
                      "geometry": {"type": "Polygon", "coordinates": [ring]}})
    return {"type": "FeatureCollection", "features": feats}


def _layer_trace(df, name, scale, visible):
    import plotly.graph_objects as go

    z = np.log10(df["n"].clip(lower=1))
    return go.Choroplethmap(
        geojson=_geojson(df["h3"]), locations=df["h3"], z=z,
        colorscale=scale, marker_line_width=0, marker_opacity=0.7,
        showscale=False, name=name, visible=visible,
        # The colour axis is log; the hover shows the real count, because a
        # reader should never have to undo a transform in their head.
        customdata=df["n"],
        hovertemplate="%{customdata:,} position reports<extra>" + name + "</extra>",
    )


def coverage_map(cells, tracks=None, height=520):
    """An interactive map of one aerodrome's observed coverage.

    `cells` has `h3`, `layer`, `n`. `tracks` optionally has `lat`, `lon`,
    `track_id`, `label`, `side`. Returns an HTML fragment, or None when there
    is nothing to draw.
    """
    import h3
    import plotly.graph_objects as go

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
        fig.add_trace(_layer_trace(sub, name, scale,
                                   True if layer == "ground" else "legendonly"))
        for c in sub["h3"]:
            la, lo = h3.h3_to_geo(c)
            lats.append(la)
            lons.append(lo)

    if tracks is not None and not tracks.empty:
        for (tid, label), g in tracks.groupby(["track_id", "label"], sort=False):
            g = g.sort_values("event_time")
            fig.add_trace(go.Scattermap(
                lat=g["lat"].round(5), lon=g["lon"].round(5), mode="lines",
                line=dict(width=2.5, color=TRACK_COLORS.get(label, "#52514e")),
                name=TRACK_LABELS.get(label, label), legendgroup=label,
                showlegend=tid == tracks[tracks.label == label].track_id.iloc[0],
                hovertemplate=f"{TRACK_LABELS.get(label, label)}<extra></extra>",
                visible="legendonly",
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
        legend=dict(orientation="h", yanchor="bottom", y=1.01, x=0),
        showlegend=True,
    )
    return fig.to_html(full_html=False, include_plotlyjs="cdn",
                       config={"displayModeBar": False, "scrollZoom": True})
