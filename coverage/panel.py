"""HTML of the docked side panel: RSRP scale, layer modes, chosen sites, map objects.

The panel is plain HTML; coverage/assets/map_theme.js wires its inputs to the Leaflet
layers whose JS variable names are passed in LayerRefs.
"""

from __future__ import annotations

import html
import math
from dataclasses import dataclass

from coverage import ru
from coverage.charts import Bin, Marker, bin_values, histogram_svg
from coverage.grid import GOOD_THRESHOLD_DBM, WEAK_THRESHOLD_DBM, GridResult, Level, classify
from coverage.pipeline import Analysis
from coverage.timeofday import DAY_START_HOUR, NIGHT_START_HOUR

RSRP_BIN_DB = 2.0
DELTA_BIN_DB = 1.0
LEVEL_CLASS = {Level.WEAK: "is-weak", Level.FAIR: "is-fair", Level.GOOD: "is-good"}
DAY_LABEL = f"{DAY_START_HOUR}:00–{NIGHT_START_HOUR}:00"
NIGHT_LABEL = f"{NIGHT_START_HOUR}:00–{DAY_START_HOUR}:00"


@dataclass(frozen=True)
class LayerRefs:
    """JS variable names of the folium layers the panel controls."""

    map: str
    all_cells: str
    day_cells: str
    night_cells: str
    delta: str
    heat: str
    worst: str
    sparse: str
    towers: str
    candidates: str
    exact: str
    greedy: str


_ICON_MOON = (
    '<svg class="cov-icon-moon" viewBox="0 0 24 24" aria-hidden="true">'
    '<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/></svg>'
)
_ICON_SUN = (
    '<svg class="cov-icon-sun" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/>'
    '<path d="M12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5M5.3 5.3l1.8 1.8M16.9 16.9l1.8 1.8'
    'M5.3 18.7l1.8-1.8M16.9 7.1l1.8-1.8"/></svg>'
)
_ICON_CHEVRON = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 15l6-6 6 6"/></svg>'


def _rsrp_domain(grids: list[GridResult]) -> tuple[float, float]:
    """One x-range for all, day and night scales so they can be compared by eye."""
    medians = [c.median_dbm for g in grids for c in g.cells] or [WEAK_THRESHOLD_DBM]
    lo = min(math.floor((min(medians) - 2) / RSRP_BIN_DB) * RSRP_BIN_DB, WEAK_THRESHOLD_DBM - 10)
    hi = max(math.ceil((max(medians) + 2) / RSRP_BIN_DB) * RSRP_BIN_DB, GOOD_THRESHOLD_DBM + 6)
    return lo, hi


def _ticks(lo: float, hi: float, step: float) -> list[float]:
    first = math.ceil(lo / step) * step
    return [first + i * step for i in range(int((hi - first) // step) + 1)]


def _rsrp_scale(key: str, title: str, grid: GridResult, domain: tuple[float, float], hidden: bool) -> str:
    lo, hi = domain
    bins = bin_values((c.median_dbm for c in grid.cells), lo, hi, RSRP_BIN_DB)
    chart = histogram_svg(
        bins,
        bar_class=lambda b: f"cov-bar {LEVEL_CLASS[classify(b.center)]}",
        ticks=[t for t in _ticks(lo, hi, 10) if t not in (WEAK_THRESHOLD_DBM, GOOD_THRESHOLD_DBM)],
        markers=[
            Marker(WEAK_THRESHOLD_DBM, ru.number(WEAK_THRESHOLD_DBM, 0)),
            Marker(GOOD_THRESHOLD_DBM, ru.number(GOOD_THRESHOLD_DBM, 0)),
        ],
        title=title,
    )
    levels = grid.level_counts()
    zones = [
        (Level.WEAK, "слабый", f"ниже {ru.number(WEAK_THRESHOLD_DBM, 0)}"),
        (Level.FAIR, "средний", f"{ru.number(WEAK_THRESHOLD_DBM, 0)}…{ru.number(GOOD_THRESHOLD_DBM, 0)}"),
        (Level.GOOD, "хороший", f"от {ru.number(GOOD_THRESHOLD_DBM, 0)}"),
    ]
    zone_items = "".join(
        f'<li class="{LEVEL_CLASS[level]}"><span class="cov-zone-n">{levels[level]}</span>'
        f'<span class="cov-zone-name">{name}</span><span class="cov-zone-range">{rng}</span></li>'
        for level, name, rng in zones
    )
    return (
        f'<figure class="cov-scale" data-scale="{key}"{" hidden" if hidden else ""}>'
        f'<figcaption class="cov-scale-title">{html.escape(title)}</figcaption>'
        f"{chart}<ul class=\"cov-zones\">{zone_items}</ul></figure>"
    )


def _delta_scale(analysis: Analysis) -> str:
    dn = analysis.day_night
    deltas = [c.delta_db for c in dn.common]
    if not deltas:
        return (
            '<figure class="cov-scale" data-scale="delta" hidden>'
            '<figcaption class="cov-scale-title">Ночь и день</figcaption>'
            '<p class="cov-note">Нет квадратов, где хватает замеров и днём, и ночью.</p></figure>'
        )
    reach = min(20.0, max(6.0, math.ceil(max(abs(d) for d in deltas))))
    bins = bin_values(deltas, -reach, reach, DELTA_BIN_DB)

    def bar_class(b: Bin) -> str:
        return "cov-bar is-better" if b.center > 0 else "cov-bar is-worse"

    median = dn.median_delta_db or 0.0
    chart = histogram_svg(
        bins,
        bar_class=bar_class,
        ticks=_ticks(-reach, reach, 5),
        markers=[Marker(median, f"медиана {ru.number(median, 1, signed=True)}", "cov-chart-marker is-median")],
        title="Разница ночь минус день",
    )
    better, worse = len(dn.better_at_night), len(dn.worse_at_night)
    return (
        '<figure class="cov-scale" data-scale="delta" hidden>'
        f'<figcaption class="cov-scale-title">Ночь минус день, дБм, в {ru.count(len(deltas), ru.CELLS_IN)} '
        "с данными в обе половины суток</figcaption>"
        f"{chart}"
        '<div class="cov-delta-ends"><span class="is-worse">ночью слабее</span>'
        '<span class="is-better">ночью сильнее</span></div>'
        f'<p class="cov-note">Зона стала лучше в {ru.count(better, ru.CELLS_IN)}, хуже в {worse}. '
        "Обведены квадраты, сменившие цвет.</p></figure>"
    )


def _heat_scale() -> str:
    return (
        '<figure class="cov-scale" data-scale="heat" hidden>'
        '<figcaption class="cov-scale-title">Где чаще всего слабый сигнал</figcaption>'
        '<div class="cov-heat-bar" aria-hidden="true"></div>'
        f'<div class="cov-heat-ends"><span>{ru.number(-90, 0)} дБм</span>'
        f"<span>{ru.number(-120, 0)} и ниже</span></div>"
        '<p class="cov-note">Учтены отдельные замеры слабее −90 дБм. Чем слабее замер, '
        "тем больше его вес.</p></figure>"
    )


def _mode(value: str, layer: str, label: str, checked: bool = False) -> str:
    return (
        f'<label class="cov-mode"><input type="radio" name="cov-mode" value="{value}" '
        f'data-layer="{layer}"{" checked" if checked else ""}><span>{html.escape(label)}</span></label>'
    )


def _toggle(layer: str, label: str, aside: str = "", checked: bool = True) -> str:
    aside_html = f'<span class="cov-toggle-aside">{html.escape(aside)}</span>' if aside else ""
    return (
        f'<label class="cov-toggle"><input type="checkbox" data-layer="{layer}"'
        f'{" checked" if checked else ""}><span class="cov-toggle-box" aria-hidden="true"></span>'
        f'<span class="cov-toggle-label">{html.escape(label)}</span>{aside_html}</label>'
    )


def _sites_text(analysis: Analysis) -> str:
    exact, greedy, coverage = analysis.placement, analysis.greedy, analysis.coverage
    weak_total = len(analysis.grid.weak_cells)
    if len(exact.site_ids) < 2:
        return '<p class="cov-text">Допустимых площадок меньше двух, пару выбрать нельзя.</p>'

    a, b = exact.site_ids
    lines = [
        f'<p class="cov-text"><strong>{a} и {b}</strong> вместе покрывают '
        f"<strong>{exact.covered_count} из {weak_total}</strong> "
        f"{ru.plural(weak_total, ru.WEAK_CELLS_OF)} в радиусе 1 км.</p>"
    ]
    if greedy.site_ids == exact.site_ids:
        lines.append('<p class="cov-text is-quiet">Жадный выбор здесь совпал с полным перебором.</p>')
    elif len(greedy.steps) == 2:
        first, second = greedy.steps
        overlap = len(coverage[first.site_id] & coverage[second.site_id])
        lines.append(
            f'<p class="cov-text is-quiet">Жадный выбор начал бы с {first.site_id}, лучшей в одиночку '
            f"({ru.count(first.new_cells, ru.CELLS)}), добавил бы {second.site_id} и покрыл бы "
            f"{greedy.covered_count}: у их зон {ru.count(overlap, ('общий квадрат', 'общих квадрата', 'общих квадратов'))}.</p>"
        )
    return "".join(lines)


def build_panel(analysis: Analysis, refs: LayerRefs) -> str:
    dn = analysis.day_night
    cleaning = analysis.cleaning
    domain = _rsrp_domain([analysis.grid, dn.day, dn.night])
    allowed, total_candidates = len(analysis.eligibility.allowed), len(analysis.candidates)

    scales = "".join([
        _rsrp_scale("all", "Медиана RSRP в квадрате, дБм", analysis.grid, domain, hidden=False),
        _rsrp_scale("day", f"Днём, {DAY_LABEL}: медиана в квадрате, дБм", dn.day, domain, hidden=True),
        _rsrp_scale("night", f"Ночью, {NIGHT_LABEL}: медиана в квадрате, дБм", dn.night, domain, hidden=True),
        _delta_scale(analysis),
        _heat_scale(),
    ])
    modes = "".join([
        _mode("all", refs.all_cells, "Все замеры", checked=True),
        _mode("day", refs.day_cells, f"Днём, {DAY_LABEL}"),
        _mode("night", refs.night_cells, f"Ночью, {NIGHT_LABEL}"),
        _mode("delta", refs.delta, "Ночь против дня"),
        _mode("heat", refs.heat, "Тепловая карта"),
    ])
    objects = "".join([
        _toggle(refs.worst, "Худшие квадраты", "номера 1–3"),
        _toggle(refs.towers, "Действующие станции", str(len(analysis.towers))),
        _toggle(refs.candidates, "Площадки-кандидаты", f"{allowed} из {total_candidates} допустимы"),
        _toggle(refs.sparse, "Квадраты, где меньше 5 замеров", str(len(analysis.grid.sparse_cells)),
                checked=False),
    ])

    return f"""
    <aside id="cov-panel" class="cov-panel" data-map="{refs.map}" aria-label="Карта покрытия: управление">
      <header class="cov-head">
        <div class="cov-head-text">
          <h1 class="cov-title">Покрытие района</h1>
          <p class="cov-sub">Бишкек, {ru.count(len(cleaning.measurements), ru.MEASUREMENTS)} RSRP</p>
        </div>
        <button type="button" class="cov-iconbtn" id="cov-theme">{_ICON_MOON}{_ICON_SUN}</button>
        <button type="button" class="cov-iconbtn cov-sheet-btn" id="cov-sheet"
                aria-expanded="false" aria-controls="cov-panel-body">{_ICON_CHEVRON}</button>
      </header>
      <div class="cov-scales" aria-live="polite">{scales}</div>
      <div class="cov-body" id="cov-panel-body">
        <section class="cov-section">
          <h2 class="cov-h2">Что показать</h2>
          <div class="cov-modes" role="radiogroup" aria-label="Слой покрытия">{modes}</div>
        </section>
        <section class="cov-section">
          <h2 class="cov-h2">Новые станции</h2>
          {_sites_text(analysis)}
          {_toggle(refs.exact, "Зоны 1 км выбранной пары")}
          {_toggle(refs.greedy, "Жадный выбор для сравнения", checked=False)}
        </section>
        <section class="cov-section">
          <h2 class="cov-h2">На карте</h2>
          {objects}
        </section>
        <p class="cov-foot">Очистка отбросила {ru.count(cleaning.dropped_rows, ru.ROWS)} из {cleaning.total_rows}:
          дубли, пустые и битые значения, точки вне района. Квадрат 200 × 200 м учитывается,
          если в нём от 5 замеров.</p>
      </div>
    </aside>
    """
