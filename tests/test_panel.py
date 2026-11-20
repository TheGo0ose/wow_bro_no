import pytest

from conftest import DATA_DIR

from coverage import ru
from coverage.charts import Marker, bin_values, histogram_svg
from coverage.panel import LayerRefs, build_panel
from coverage.pipeline import InputPaths, run_analysis


@pytest.mark.parametrize("n, form", [
    (1, "квадрат"), (2, "квадрата"), (4, "квадрата"), (5, "квадратов"), (11, "квадратов"),
    (12, "квадратов"), (21, "квадрат"), (22, "квадрата"), (111, "квадратов"), (174, "квадрата"),
])
def test_plural(n, form):
    assert ru.plural(n, ru.CELLS) == form


@pytest.mark.parametrize("value, kwargs, text", [
    (-105, {"decimals": 0}, "−105"),
    (-120.75, {"decimals": 2}, "−120,75"),
    (1.2, {"signed": True}, "+1,2"),
    (-0.04, {}, "0"),
    (-124.5, {}, "−124,5"),
    (-90.0, {}, "−90"),
])
def test_number_uses_comma_and_real_minus(value, kwargs, text):
    assert ru.number(value, **kwargs) == text


def test_bin_values_counts_and_clamps():
    bins = bin_values([-130, -105, -104.5, -91, -40], lo=-110, hi=-90, width=10)
    assert [(b.start, b.end, b.count) for b in bins] == [(-110, -100, 3), (-100, -90, 2)]


def test_histogram_svg_has_bars_ticks_and_markers():
    bins = bin_values([-100, -100, -95], -110, -90, 5)
    svg = histogram_svg(bins, bar_class=lambda b: "cov-bar", ticks=[-100],
                        markers=[Marker(-105, "−105")], title="t")
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert svg.count('class="cov-bar"') == 2  # empty bins are not drawn
    assert ">−100<" in svg and "−105" in svg


def test_histogram_svg_empty():
    assert histogram_svg([], bar_class=lambda b: "", ticks=[]) == ""


def test_panel_on_open_data():
    analysis = run_analysis(InputPaths.from_dir(DATA_DIR))
    refs = LayerRefs(*(f"layer_{i}" for i in range(12)))
    html = build_panel(analysis, refs)
    assert 'data-map="layer_0"' in html
    assert html.count('name="cov-mode"') == 5
    assert html.count('data-scale="') == 5
    assert "C09 и C14" in html and "111 из 174" in html
    assert "слабых квадратов" in html
    assert "в 177 квадратах" in html
    assert "200 строк из 5000" in html
