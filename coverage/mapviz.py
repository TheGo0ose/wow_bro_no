"""Interactive HTML coverage map built with folium (Leaflet).

Layers are plain folium FeatureGroups; the docked panel (coverage/panel.py) switches
them through coverage/assets/map_theme.js instead of Leaflet's default layer control.
Theme-dependent colours (rings, outlines, markers) are set by CSS classes.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Iterable

import folium
from folium.plugins import HeatMap

from coverage import ru
from coverage.grid import Cell, Level
from coverage.panel import LayerRefs, build_panel
from coverage.placement import COVERAGE_RADIUS_M
from coverage.pipeline import Analysis
from coverage.timeofday import CellChange

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
FONTS_URL = "https://fonts.googleapis.com/css2?family=Golos+Text:wght@400;500;600;700&display=swap"

# Zone colours stay fixed in both themes: they carry the meaning required by the task.
LEVEL_COLORS = {
    Level.GOOD: "#2E9B5F",
    Level.FAIR: "#E5B532",
    Level.WEAK: "#D8432F",
}
BETTER_AT_NIGHT = "#14898A"
WORSE_AT_NIGHT = "#C2456B"
DELTA_FULL_SCALE_DB = 10.0  # |night - day| at which the delta colour is fully opaque

# Heatmap weight: 0 at -90 dBm (good signal) up to 1 at -120 dBm and below.
HEAT_ZERO_DBM = -90.0
HEAT_FULL_DBM = -120.0
HEAT_GRADIENT = {0.2: "#E5B532", 0.5: "#D8432F", 0.8: "#8E1F3F", 1.0: "#4A0F25"}

LEVEL_NAMES = {Level.GOOD: "хороший", Level.FAIR: "средний", Level.WEAK: "слабый"}

# Lattice mast glyph used for every station marker.
_MAST_SVG = (
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5.5 8 20.5M12 5.5l4 15'
    'M9.2 16h5.6M10.3 11.5h3.4"/><circle cx="12" cy="4" r="1.7"/></svg>'
)


def _cell_tooltip(cell: Cell) -> str:
    return (
        f"{cell.cell_id}: медиана {ru.number(cell.median_dbm)} дБм, "
        f"{ru.count(cell.samples, ru.MEASUREMENTS)}"
    )


def _corners(analysis: Analysis, cell: Cell) -> list[tuple[float, float]]:
    return list(analysis.bounds.grid.cell_corners(cell.ix, cell.iy))


def _station_icon(kind: str, label: str = "") -> folium.DivIcon:
    label_html = f'<span class="cov-pin-label">{html.escape(label)}</span>' if label else ""
    return folium.DivIcon(
        html=f'<div class="cov-pin cov-pin--{kind}">{_MAST_SVG}{label_html}</div>',
        icon_size=(28, 28),
        icon_anchor=(14, 14),
        class_name="cov-pin-wrap",
    )


# ---------- coverage layers (one visible at a time) ----------

def _cells_layer(analysis: Analysis, cells: Iterable[Cell], show: bool) -> folium.FeatureGroup:
    layer = folium.FeatureGroup(show=show)
    for cell in cells:
        color = LEVEL_COLORS[cell.level]
        folium.Rectangle(
            bounds=_corners(analysis, cell),
            color=color,
            weight=0.4,
            fill=True,
            fill_color=color,
            fill_opacity=0.58,
            tooltip=_cell_tooltip(cell),
        ).add_to(layer)
    return layer


def _delta_layer(analysis: Analysis, changes: Iterable[CellChange]) -> folium.FeatureGroup:
    layer = folium.FeatureGroup(show=False)
    for change in changes:
        delta = change.delta_db
        color = BETTER_AT_NIGHT if delta > 0 else WORSE_AT_NIGHT
        strength = min(1.0, abs(delta) / DELTA_FULL_SCALE_DB)
        tooltip = (
            f"{change.cell_id}: днём {ru.number(change.day.median_dbm)} "
            f"({LEVEL_NAMES[change.day.level]}), ночью {ru.number(change.night.median_dbm)} "
            f"({LEVEL_NAMES[change.night.level]}), разница {ru.number(delta, signed=True)} дБм"
        )
        # cells whose zone colour changed get an outline (CSS class, theme-aware)
        outline = {"class_name": "cov-delta-changed"} if change.level_shift else {}
        folium.Rectangle(
            bounds=_corners(analysis, change.day),
            color=color,
            weight=0.4,
            fill=True,
            fill_color=color,
            fill_opacity=0.12 + 0.68 * strength,
            tooltip=tooltip,
            **outline,
        ).add_to(layer)
    return layer


def _heat_layer(analysis: Analysis) -> folium.FeatureGroup:
    layer = folium.FeatureGroup(show=False)
    span = HEAT_ZERO_DBM - HEAT_FULL_DBM
    points = [
        [m.lat, m.lon, min(1.0, (HEAT_ZERO_DBM - m.rsrp_dbm) / span)]
        for m in analysis.cleaning.measurements
        if m.rsrp_dbm < HEAT_ZERO_DBM
    ]
    HeatMap(points, radius=18, blur=22, min_opacity=0.25, max_zoom=16,
            gradient=HEAT_GRADIENT).add_to(layer)
    return layer


# ---------- objects ----------

def _sparse_layer(analysis: Analysis) -> folium.FeatureGroup:
    layer = folium.FeatureGroup(show=False)
    for cell in analysis.grid.sparse_cells:
        folium.Rectangle(
            bounds=_corners(analysis, cell),
            class_name="cov-sparse",
            weight=1,
            dash_array="3 3",
            fill=True,
            fill_opacity=0.15,
            tooltip=f"{_cell_tooltip(cell)}: меньше 5, не учитывается",
        ).add_to(layer)
    return layer


def _worst_layer(analysis: Analysis) -> folium.FeatureGroup:
    layer = folium.FeatureGroup()
    for rank, cell in enumerate(analysis.worst, start=1):
        tooltip = f"{rank}-й худший. {_cell_tooltip(cell)}"
        folium.Rectangle(
            bounds=_corners(analysis, cell), class_name="cov-worst", weight=2, fill=False,
            tooltip=tooltip,
        ).add_to(layer)
        folium.Marker(
            location=(cell.center_lat, cell.center_lon),
            icon=folium.DivIcon(html=f'<div class="cov-rank">{rank}</div>', icon_size=(18, 18),
                                icon_anchor=(9, 9), class_name="cov-pin-wrap"),
            tooltip=tooltip,
        ).add_to(layer)
    return layer


def _towers_layer(analysis: Analysis) -> folium.FeatureGroup:
    layer = folium.FeatureGroup()
    for tower in analysis.towers:
        folium.Marker(
            location=(tower.lat, tower.lon),
            icon=_station_icon("tower"),
            tooltip=f"Действующая станция {tower.id}",
        ).add_to(layer)
    return layer


def _candidates_layer(analysis: Analysis) -> folium.FeatureGroup:
    layer = folium.FeatureGroup()
    chosen = set(analysis.placement.site_ids)
    for cand in analysis.candidates:
        if cand.id in chosen:
            continue
        if cand.id in analysis.eligibility.rejected:
            distance = analysis.eligibility.rejected[cand.id]
            tooltip = f"{cand.id}: {ru.number(distance, 0)} м до станции, нужно от 500 м"
            css = "cov-cand is-rejected"
        else:
            covered = len(analysis.coverage.get(cand.id, ()))
            tooltip = f"{cand.id}: покрыла бы {ru.count(covered, ru.CELLS)}"
            css = "cov-cand"
        folium.Marker(
            location=(cand.lat, cand.lon),
            icon=folium.DivIcon(html=f'<div class="{css}"></div>', icon_size=(14, 14),
                                icon_anchor=(7, 7), class_name="cov-pin-wrap"),
            tooltip=tooltip,
        ).add_to(layer)
    return layer


def _sites_layer(analysis: Analysis, site_ids: Iterable[str], kind: str, show: bool) -> folium.FeatureGroup:
    layer = folium.FeatureGroup(show=show)
    by_id = {cand.id: cand for cand in analysis.candidates}
    for site_id in site_ids:
        cand = by_id[site_id]
        covered = len(analysis.coverage.get(site_id, ()))
        folium.Circle(
            location=(cand.lat, cand.lon),
            radius=COVERAGE_RADIUS_M,
            class_name=f"cov-ring cov-ring--{kind}",
            weight=2,
            fill=kind == "new",
            fill_opacity=0.07,
            interactive=False,
        ).add_to(layer)
        prefix = "Новая станция" if kind == "new" else "Жадный выбор"
        folium.Marker(
            location=(cand.lat, cand.lon),
            icon=_station_icon(kind, site_id),
            tooltip=f"{prefix} {site_id}: в радиусе 1 км {ru.count(covered, ru.CELLS)} слабых",
            z_index_offset=1000 if kind == "new" else 500,
        ).add_to(layer)
    return layer


def _add_assets(fmap: folium.Map) -> None:
    css = (ASSETS_DIR / "map_theme.css").read_text(encoding="utf-8")
    js = (ASSETS_DIR / "map_theme.js").read_text(encoding="utf-8")
    header = fmap.get_root().header
    header.add_child(folium.Element(
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        f'<link rel="stylesheet" href="{FONTS_URL}">'
    ))
    header.add_child(folium.Element(f"<style>{css}</style>"))
    header.add_child(folium.Element(f"<script>{js}</script>"))


def build_map(analysis: Analysis) -> folium.Map:
    b = analysis.bounds
    dn = analysis.day_night
    # OpenStreetMap refuses tiles when the HTML is opened from disk (file://, no Referer).
    # Serve the map over http(s): GitHub Pages or `python -m http.server`.
    fmap = folium.Map(location=b.center, zoom_start=14, control_scale=True, tiles="OpenStreetMap",
                      zoom_control=True)
    folium.Rectangle(
        bounds=[(b.lat_min, b.lon_min), (b.lat_max, b.lon_max)],
        class_name="cov-bounds", weight=1.5, fill=False, interactive=False,
    ).add_to(fmap)

    layers = {
        "all_cells": _cells_layer(analysis, analysis.grid.cells, show=True),
        "day_cells": _cells_layer(analysis, dn.day.cells, show=False),
        "night_cells": _cells_layer(analysis, dn.night.cells, show=False),
        "delta": _delta_layer(analysis, dn.common),
        "heat": _heat_layer(analysis),
        "sparse": _sparse_layer(analysis),
        "worst": _worst_layer(analysis),
        "candidates": _candidates_layer(analysis),
        "towers": _towers_layer(analysis),
        "greedy": _sites_layer(analysis, analysis.greedy.site_ids, "greedy", show=False),
        "exact": _sites_layer(analysis, analysis.placement.site_ids, "new", show=True),
    }
    for layer in layers.values():
        layer.add_to(fmap)

    refs = LayerRefs(map=fmap.get_name(), **{key: layer.get_name() for key, layer in layers.items()})
    fmap.get_root().html.add_child(folium.Element(build_panel(analysis, refs)))
    _add_assets(fmap)
    fmap.fit_bounds([(b.lat_min, b.lon_min), (b.lat_max, b.lon_max)])
    return fmap


def render_map(analysis: Analysis, path: Path) -> None:
    build_map(analysis).save(str(path))
