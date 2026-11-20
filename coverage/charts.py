"""Small inline SVG histograms for the map panel (no JS chart library).

Colours come from CSS classes, so the charts follow the light/dark theme.
"""

from __future__ import annotations

import html
import math
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from coverage import ru

WIDTH = 288
HEIGHT = 124
PLOT_TOP = 22
PLOT_BOTTOM = 96
TICK_Y = 112


@dataclass(frozen=True)
class Bin:
    start: float
    end: float
    count: int

    @property
    def center(self) -> float:
        return (self.start + self.end) / 2


@dataclass(frozen=True)
class Marker:
    value: float
    label: str
    css_class: str = "cov-chart-marker"


def bin_values(values: Iterable[float], lo: float, hi: float, width: float) -> list[Bin]:
    """Histogram over [lo, hi); values outside the range are clamped into the edge bins."""
    n = max(1, math.ceil((hi - lo) / width - 1e-9))
    counts = [0] * n
    for v in values:
        index = min(max(math.floor((v - lo) / width), 0), n - 1)
        counts[index] += 1
    return [Bin(lo + i * width, lo + (i + 1) * width, c) for i, c in enumerate(counts)]


def histogram_svg(
    bins: Sequence[Bin],
    bar_class: Callable[[Bin], str],
    ticks: Sequence[float],
    markers: Sequence[Marker] = (),
    title: str = "",
) -> str:
    if not bins:
        return ""
    lo, hi = bins[0].start, bins[-1].end
    span = hi - lo

    def x(value: float) -> float:
        return (value - lo) / span * WIDTH

    peak = max(b.count for b in bins) or 1
    parts = [
        f'<svg class="cov-chart" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" '
        f'aria-label="{html.escape(title)}">'
    ]
    for b in bins:
        if not b.count:
            continue
        height = (PLOT_BOTTOM - PLOT_TOP) * b.count / peak
        left, right = x(b.start) + 0.6, x(b.end) - 0.6
        parts.append(
            f'<rect class="{bar_class(b)}" x="{left:.1f}" y="{PLOT_BOTTOM - height:.1f}" '
            f'width="{max(right - left, 0.8):.1f}" height="{height:.1f}">'
            f"<title>{ru.number(b.start, 0)}…{ru.number(b.end, 0)} дБм: "
            f"{ru.count(b.count, ru.CELLS)}</title></rect>"
        )
    parts.append(
        f'<line class="cov-chart-axis" x1="0" x2="{WIDTH}" y1="{PLOT_BOTTOM + 0.5}" '
        f'y2="{PLOT_BOTTOM + 0.5}"/>'
    )
    for tick in ticks:
        tx = x(tick)
        anchor = "start" if tx < 12 else "end" if tx > WIDTH - 12 else "middle"
        parts.append(
            f'<line class="cov-chart-axis" x1="{tx:.1f}" x2="{tx:.1f}" '
            f'y1="{PLOT_BOTTOM}" y2="{PLOT_BOTTOM + 4}"/>'
            f'<text class="cov-chart-tick" x="{tx:.1f}" y="{TICK_Y}" '
            f'text-anchor="{anchor}">{ru.number(tick, 0)}</text>'
        )
    for marker in markers:
        mx = x(marker.value)
        anchor = "start" if mx < 30 else "end" if mx > WIDTH - 30 else "middle"
        parts.append(
            f'<g class="{marker.css_class}"><line x1="{mx:.1f}" x2="{mx:.1f}" '
            f'y1="{PLOT_TOP - 6}" y2="{PLOT_BOTTOM + 4}"/>'
            f'<text x="{mx:.1f}" y="{PLOT_TOP - 9}" text-anchor="{anchor}">'
            f"{html.escape(marker.label)}</text></g>"
        )
    parts.append("</svg>")
    return "".join(parts)
