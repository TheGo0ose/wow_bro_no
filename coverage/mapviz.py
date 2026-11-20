"""Interactive HTML coverage map built with folium (Leaflet).

Layer control has two groups:
  * "Слой покрытия" — one at a time (radio): all data, day, night, night-minus-day, heatmap;
  * "Объекты" — checkboxes: worst cells, sparse cells, towers, candidates, chosen sites.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Iterable

import folium
from folium.plugins import GroupedLayerControl, HeatMap

from coverage.grid import Cell, Level
from coverage.placement import COVERAGE_RADIUS_M
from coverage.pipeline import Analysis
from coverage.sites import Site
from coverage.timeofday import DAY_START_HOUR, NIGHT_START_HOUR, CellChange

LEVEL_COLORS = {
    Level.GOOD: "#2e9d4f",
    Level.FAIR: "#f2c230",
    Level.WEAK: "#d7301f",
}
LEVEL_LABELS = {
    Level.GOOD: "≥ −90 дБм — хорошее",
    Level.FAIR: "−105…−90 дБм — среднее",
    Level.WEAK: "< −105 дБм — слабая зона",
}
LEVEL_NAMES = {Level.GOOD: "зелёный", Level.FAIR: "жёлтый", Level.WEAK: "красный"}
SPARSE_COLOR = "#9e9e9e"
EXACT_COLOR = "#6a1b9a"
GREEDY_COLOR = "#ef6c00"
BETTER_AT_NIGHT = "#1e88e5"
WORSE_AT_NIGHT = "#e65100"
DELTA_FULL_SCALE_DB = 10.0  # |night - day| at which the delta colour is fully opaque

# Heatmap weight: 0 at -90 dBm (good signal) up to 1 at -120 dBm and below.
HEAT_ZERO_DBM = -90.0
HEAT_FULL_DBM = -120.0

ASSETS_DIR = Path(__file__).resolve().parent / "assets"

COVERAGE_GROUP = "Слой покрытия"
OBJECTS_GROUP = "Объекты"


def _cell_tooltip(cell: Cell) -> str:
    return f"{cell.cell_id}: медиана {cell.median_dbm:g} дБм, замеров {cell.samples}"


def _cells_layer(analysis: Analysis, name: str, cells: Iterable[Cell], show: bool) -> folium.FeatureGroup:
    grid = analysis.bounds.grid
    layer = folium.FeatureGroup(name=name, show=show)
    for cell in cells:
        color = LEVEL_COLORS[cell.level]
        folium.Rectangle(
            bounds=list(grid.cell_corners(cell.ix, cell.iy)),
            color=color,
            weight=0.5,
            fill=True,
            fill_color=color,
            fill_opacity=0.55,
            tooltip=_cell_tooltip(cell),
        ).add_to(layer)
    return layer


def _delta_layer(analysis: Analysis, changes: Iterable[CellChange]) -> folium.FeatureGroup:
    grid = analysis.bounds.grid
    layer = folium.FeatureGroup(name="Разница ночь − день", show=False)
    for change in changes:
        delta = change.delta_db
        color = BETTER_AT_NIGHT if delta > 0 else WORSE_AT_NIGHT
        strength = min(1.0, abs(delta) / DELTA_FULL_SCALE_DB)
        tooltip = (
            f"{change.cell_id}: день {change.day.median_dbm:g} дБм ({LEVEL_NAMES[change.day.level]}), "
            f"ночь {change.night.median_dbm:g} дБм ({LEVEL_NAMES[change.night.level]}), "
            f"разница {delta:+.1f} дБм"
        )
        folium.Rectangle(
            bounds=list(grid.cell_corners(change.day.ix, change.day.iy)),
            color="#555555" if change.level_shift else color,
            weight=2 if change.level_shift else 0.5,
            fill=True,
            fill_color=color,
            fill_opacity=0.1 + 0.7 * strength,
            tooltip=tooltip,
        ).add_to(layer)
    return layer


def _heat_layer(analysis: Analysis) -> folium.FeatureGroup:
    layer = folium.FeatureGroup(name="Тепловая карта слабого сигнала", show=False)
    span = HEAT_ZERO_DBM - HEAT_FULL_DBM
    points = [
        [m.lat, m.lon, min(1.0, (HEAT_ZERO_DBM - m.rsrp_dbm) / span)]
        for m in analysis.cleaning.measurements
        if m.rsrp_dbm < HEAT_ZERO_DBM
    ]
    HeatMap(points, radius=18, blur=22, min_opacity=0.3, max_zoom=16).add_to(layer)
    return layer


def _sparse_layer(analysis: Analysis) -> folium.FeatureGroup:
    grid = analysis.bounds.grid
    layer = folium.FeatureGroup(name="Мало замеров (< 5), не учитываются", show=False)
    for cell in analysis.grid.sparse_cells:
        folium.Rectangle(
            bounds=list(grid.cell_corners(cell.ix, cell.iy)),
            color=SPARSE_COLOR,
            weight=1,
            dash_array="4",
            fill=True,
            fill_opacity=0.2,
            tooltip=_cell_tooltip(cell),
        ).add_to(layer)
    return layer


def _worst_layer(analysis: Analysis) -> folium.FeatureGroup:
    grid = analysis.bounds.grid
    layer = folium.FeatureGroup(name="Топ-3 худших квадрата")
    for rank, cell in enumerate(analysis.worst, start=1):
        folium.Rectangle(
            bounds=list(grid.cell_corners(cell.ix, cell.iy)),
            color="#000000",
            weight=3,
            fill=False,
            tooltip=f"#{rank} худший — {_cell_tooltip(cell)}",
        ).add_to(layer)
        folium.Marker(
            location=(cell.center_lat, cell.center_lon),
            icon=folium.DivIcon(
                html=f'<div style="font:bold 13px sans-serif;color:#fff;'
                f'text-shadow:0 0 3px #000;transform:translate(-4px,-8px)">{rank}</div>'
            ),
        ).add_to(layer)
    return layer


def _towers_layer(analysis: Analysis) -> folium.FeatureGroup:
    layer = folium.FeatureGroup(name="Существующие БС")
    for tower in analysis.towers:
        folium.Marker(
            location=(tower.lat, tower.lon),
            tooltip=f"БС {tower.id}",
            icon=folium.Icon(color="blue", icon="wifi", prefix="fa"),
        ).add_to(layer)
    return layer


def _candidates_layer(analysis: Analysis) -> folium.FeatureGroup:
    layer = folium.FeatureGroup(name="Площадки-кандидаты")
    chosen_ids = set(analysis.placement.site_ids)
    for cand in analysis.candidates:
        if cand.id in chosen_ids:
            continue
        if cand.id in analysis.eligibility.rejected:
            distance = analysis.eligibility.rejected[cand.id]
            tooltip = f"{cand.id}: недопустима, до БС {distance:.0f} м (< 500 м)"
            color, fill = "#757575", "#ffffff"
        else:
            covered = len(analysis.coverage.get(cand.id, ()))
            tooltip = f"{cand.id}: покрывает {covered} красных квадратов"
            color, fill = "#37474f", "#90a4ae"
        folium.CircleMarker(
            location=(cand.lat, cand.lon),
            radius=6,
            color=color,
            weight=2,
            fill=True,
            fill_color=fill,
            fill_opacity=0.9,
            tooltip=tooltip,
        ).add_to(layer)
    return layer


def _sites_layer(
    analysis: Analysis,
    name: str,
    site_ids: Iterable[str],
    color: str,
    icon_color: str,
    label: str,
    show: bool,
    dashed: bool = False,
) -> folium.FeatureGroup:
    layer = folium.FeatureGroup(name=name, show=show)
    by_id: dict[str, Site] = {cand.id: cand for cand in analysis.candidates}
    for site_id in site_ids:
        cand = by_id[site_id]
        covered = len(analysis.coverage.get(site_id, ()))
        folium.Circle(
            location=(cand.lat, cand.lon),
            radius=COVERAGE_RADIUS_M,
            color=color,
            weight=2,
            dash_array="8 6" if dashed else None,
            fill=True,
            fill_opacity=0.06,
        ).add_to(layer)
        folium.Marker(
            location=(cand.lat, cand.lon),
            tooltip=f"{label} {site_id}: покрывает {covered} красных квадратов",
            icon=folium.Icon(color=icon_color, icon="star", prefix="fa"),
        ).add_to(layer)
    return layer


def _swatch(color: str, label: str) -> str:
    return f'<div class="cov-swatch"><i style="background:{color}"></i>{html.escape(label)}</div>'


def _stat(label: str, value: str, css_class: str = "") -> str:
    cls = f' class="{css_class}"' if css_class else ""
    return f"<dt{cls}>{html.escape(label)}</dt><dd{cls}>{html.escape(value)}</dd>"


def _legend_html(analysis: Analysis) -> str:
    exact, greedy, dn = analysis.placement, analysis.greedy, analysis.day_night
    weak_total = len(analysis.grid.weak_cells)
    levels = "".join(_swatch(LEVEL_COLORS[level], LEVEL_LABELS[level]) for level in Level)
    delta = dn.median_delta_db
    delta_text = f"{delta:+.1f} дБм" if delta is not None else "нет данных"
    pair = " + ".join(exact.site_ids) or "—"
    greedy_pair = " + ".join(greedy.site_ids) or "—"
    return f"""
    <div class="cov-legend">
      <div class="cov-legend-title">Сигнал RSRP, медиана</div>
      {levels}
      <div class="cov-divider"></div>
      <dl class="cov-stats">
        {_stat("Отброшено строк", str(analysis.cleaning.dropped_rows))}
        {_stat("Новые БС", pair)}
        {_stat("Покрыто слабых", f"{exact.covered_count} из {weak_total}")}
        {_stat("Жадный", f"{greedy_pair} → {greedy.covered_count}", "cov-greedy")}
      </dl>
      <div class="cov-extra">
        <div class="cov-divider"></div>
        <div class="cov-legend-title">День и ночь</div>
        <dl class="cov-stats">
          {_stat(f"Красных днём ({DAY_START_HOUR:02d}–{NIGHT_START_HOUR:02d})",
                 str(len(dn.day.weak_cells)))}
          {_stat(f"Красных ночью ({NIGHT_START_HOUR:02d}–{DAY_START_HOUR:02d})",
                 str(len(dn.night.weak_cells)))}
          {_stat("Ночь − день", delta_text)}
        </dl>
        {_swatch(BETTER_AT_NIGHT, "ночью лучше")}
        {_swatch(WORSE_AT_NIGHT, "ночью хуже (рамка — сменился цвет)")}
      </div>
    </div>
    """


_ICON_MOON = (
    '<svg class="cov-icon-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>'
)
_ICON_SUN = (
    '<svg class="cov-icon-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/>'
    '<path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2'
    'M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>'
)
_ICON_CHEVRON = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round"><path d="M18 15l-6-6-6 6"/></svg>'
)


def _panel_header_html() -> str:
    """Header that map_theme.js moves into the layer panel: title, theme and collapse buttons."""
    return f"""
    <template id="cov-header-template">
      <div class="cov-header">
        <div class="cov-title">
          <div class="cov-title-main">Карта покрытия</div>
          <div class="cov-title-sub">Бишкек · квадраты 200 × 200 м</div>
        </div>
        <button type="button" class="cov-icon-btn" id="cov-theme">{_ICON_MOON}{_ICON_SUN}</button>
        <button type="button" class="cov-icon-btn" id="cov-collapse">{_ICON_CHEVRON}</button>
      </div>
    </template>
    """


def _add_theme(fmap: folium.Map) -> None:
    css = (ASSETS_DIR / "map_theme.css").read_text(encoding="utf-8")
    js = (ASSETS_DIR / "map_theme.js").read_text(encoding="utf-8")
    root = fmap.get_root()
    root.header.add_child(folium.Element(f"<style>{css}</style>"))
    root.header.add_child(folium.Element(f"<script>{js}</script>"))
    root.html.add_child(folium.Element(_panel_header_html()))


def build_map(analysis: Analysis) -> folium.Map:
    b = analysis.bounds
    dn = analysis.day_night
    # Note: OpenStreetMap refuses tiles when the HTML is opened from disk (file://, no
    # Referer). Serve the map over http(s), e.g. GitHub Pages or `python -m http.server`.
    fmap = folium.Map(location=b.center, zoom_start=14, control_scale=True, tiles="OpenStreetMap")
    folium.Rectangle(
        bounds=[(b.lat_min, b.lon_min), (b.lat_max, b.lon_max)],
        color="#1565c0",
        weight=2,
        fill=False,
        tooltip="Граница района",
    ).add_to(fmap)

    coverage_layers = [
        _cells_layer(analysis, "Все замеры", analysis.grid.cells, show=True),
        _cells_layer(analysis, f"День {DAY_START_HOUR:02d}:00–{NIGHT_START_HOUR:02d}:00",
                     dn.day.cells, show=False),
        _cells_layer(analysis, f"Ночь {NIGHT_START_HOUR:02d}:00–{DAY_START_HOUR:02d}:00",
                     dn.night.cells, show=False),
        _delta_layer(analysis, dn.common),
        _heat_layer(analysis),
    ]
    object_layers = [
        _worst_layer(analysis),
        _sparse_layer(analysis),
        _towers_layer(analysis),
        _candidates_layer(analysis),
        _sites_layer(analysis, f"Полный перебор: {' + '.join(analysis.placement.site_ids)}",
                     analysis.placement.site_ids, EXACT_COLOR, "purple", "Новая БС", show=True),
        _sites_layer(analysis, f"Жадный: {' + '.join(analysis.greedy.site_ids)}",
                     analysis.greedy.site_ids, GREEDY_COLOR, "orange", "Жадный выбор",
                     show=False, dashed=True),
    ]
    for layer in coverage_layers + object_layers:
        layer.add_to(fmap)

    GroupedLayerControl(
        groups={COVERAGE_GROUP: coverage_layers, OBJECTS_GROUP: object_layers},
        exclusive_groups=False,
        exclusiveGroups=[COVERAGE_GROUP],  # radio buttons for the coverage group only
        collapsed=False,
    ).add_to(fmap)
    fmap.get_root().html.add_child(folium.Element(_legend_html(analysis)))
    _add_theme(fmap)
    fmap.fit_bounds([(b.lat_min, b.lon_min), (b.lat_max, b.lon_max)])
    return fmap


def render_map(analysis: Analysis, path: Path) -> None:
    build_map(analysis).save(str(path))
