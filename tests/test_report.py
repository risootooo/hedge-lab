"""Tests for hedge.report — the previously untested dashboard module.

Degenerate inputs (no strategies, an empty cumulative series) used to
crash _svg_lines: an empty series list died on max() of an empty
iterable, and a single empty series died on s[-1]. Both now render a
finite 'No data' chart / skip the empty series.
"""

from __future__ import annotations

import re

from hedge.report import _attr_bars_from_dicts, _svg_lines, render_dashboard


def _finite(svg: str) -> bool:
    return "nan" not in svg.lower() and "inf" not in svg.lower()


def test_svg_lines_empty_series_list_renders_no_data():
    svg = _svg_lines([], [], [])
    assert "No data" in svg and _finite(svg)


def test_svg_lines_all_empty_series_renders_no_data():
    svg = _svg_lines([[], []], ["2026-10-21"], ["#f87171", "#38bdf8"])
    assert "No data" in svg and _finite(svg)


def test_svg_lines_mixed_empty_and_data_series():
    svg = _svg_lines([[], [0.0, 100.0]], ["2026-10-21", "2026-10-22"],
                     ["#f87171", "#38bdf8"])
    assert "<polyline" in svg and svg.count("<circle") == 1 and _finite(svg)


def test_svg_lines_single_point_and_flat_series_are_finite():
    single = _svg_lines([[5.0]], ["2026-10-21"], ["#38bdf8"])
    flat = _svg_lines([[3.0, 3.0, 3.0]],
                      ["2026-10-21", "2026-10-22", "2026-10-23"], ["#38bdf8"])
    assert "<polyline" in single and _finite(single)
    assert "<polyline" in flat and _finite(flat)


def _minimal_res():
    row = {"day_from": "2026-10-21", "day_to": "2026-10-22",
           "spot_move": 10.0, "theta": 100.0, "gamma": -40.0,
           "vega": -10.0, "delta_net": 0.0, "costs": 5.0,
           "residual": 2.0, "total": 47.0}
    strat = {"name": "Daily delta hedge", "cumulative": [0.0, 47.0],
             "total_pnl": 47.0, "option_pnl": 50.0, "hedge_pnl": 2.0,
             "total_costs": 5.0, "turnover_units": 100.0, "n_trades": 1,
             "worst_day_pnl": -1.0, "worst_day_to": "2026-10-22",
             "daily_std": 10.0}
    totals = {k: row[k] for k in
              ("theta", "gamma", "vega", "delta_net", "costs", "residual", "total")}
    return {"days": ["2026-10-21", "2026-10-22"],
            "window_text": "test window", "book_text": "test book",
            "net_credit_rs": 1000.0,
            "mark_counts": {"REAL": 40, "MODEL": 0, "STALE": 0},
            "strategies": [strat],
            "attribution_daily": {"rows": [row], "totals": totals},
            "cases": {"A": "case a", "B": "case b", "C": "case c"}}


def test_render_dashboard_end_to_end_offline_and_finite():
    page = render_dashboard(_minimal_res())
    assert page.startswith("<!DOCTYPE html>")
    assert "Daily delta hedge" in page and "Case A" in page
    assert _finite(page)
    # Self-contained: no external references of any kind.
    assert not re.search(r'(?:src|href)\s*=\s*"https?://', page)
    assert _attr_bars_from_dicts([]) == ""
