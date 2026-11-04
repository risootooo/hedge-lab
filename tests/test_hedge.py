"""Hedge Lab test suite.

Three layers:
  * pricing/Greeks correctness against bump-and-reprice;
  * marking and book construction against the committed REAL window
    (premiums must equal the bhavcopy prints in data/book_window.csv);
  * engine + attribution identities on synthetic states whose true
    P&L is known analytically, and accounting identities on the real
    window.
"""

import os
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from hedge import attribution, book, data, engine, greeks
from hedge.book import Position, mark_day, synthetic_state
from hedge.engine import Interval, Strategy
from hedge.pricing import bs_price, implied_vol

HERE = os.path.dirname(__file__)
WINDOW = os.path.join(HERE, "..", "data", "book_window.csv")
R, Q = 0.065, 0.0
S0, K0, T0, SIG = 22_800.0, 22_800.0, 19 / 365, 0.15


@pytest.fixture(scope="module")
def window():
    return data.load_window(WINDOW)


@pytest.fixture(scope="module")
def real(window):
    days = data.window_days(window)
    positions = book.build_book(data.day_chain(window, days[0]))
    states = book.build_states(positions, window, days)
    return positions, states


# ------------------------------------------------------------- pricing

def test_bs_put_call_parity():
    c = bs_price(S0, K0, T0, R, Q, SIG, "CE")
    p = bs_price(S0, K0, T0, R, Q, SIG, "PE")
    forward_parity = S0 * np.exp(-Q * T0) - K0 * np.exp(-R * T0)
    assert c - p == pytest.approx(forward_parity, abs=1e-8)


def test_iv_round_trip():
    for kind in ("CE", "PE"):
        px = bs_price(S0, 23_100.0, T0, R, Q, 0.183, kind)
        iv = implied_vol(px, S0, 23_100.0, T0, R, Q, kind)
        assert iv == pytest.approx(0.183, abs=1e-6)


def test_iv_below_intrinsic_is_nan():
    # A call print below intrinsic has no arbitrage-consistent vol.
    px = max(S0 - 21_000.0, 0.0) - 5.0
    assert np.isnan(implied_vol(px, S0, 21_000.0, T0, R, Q, "CE"))


@pytest.mark.parametrize("name", ["delta", "gamma", "theta", "vega"])
@pytest.mark.parametrize("kind", ["CE", "PE"])
def test_greeks_match_finite_difference(name, kind):
    analytic = getattr(greeks, name)(S0, K0, T0, R, Q, SIG, kind)
    bumped = greeks.finite_diff_greek(name, S0, K0, T0, R, Q, SIG, kind)
    assert analytic == pytest.approx(bumped, rel=2e-4, abs=1e-8)


# ------------------------------------------------- book on real data

def test_book_construction_matches_real_prints(real, window):
    positions, states = real
    day0 = data.day_chain(window, data.window_days(window)[0])
    spot = float(day0["spot"].iloc[0])
    by_key = {(p.strike, p.kind): p for p in positions}
    assert by_key[(22_800.0, "CE")].lots == -10
    assert by_key[(22_800.0, "PE")].lots == -10
    assert by_key[(23_250.0, "CE")].lots == 5
    assert by_key[(22_350.0, "PE")].lots == 5
    # Premiums must be the file's own settlement prints.
    marks = states[0].marks
    assert marks[(22_800.0, "CE")].premium == pytest.approx(297.90)
    assert marks[(22_800.0, "PE")].premium == pytest.approx(311.10)
    assert marks[(23_250.0, "CE")].premium == pytest.approx(123.15)
    assert marks[(22_350.0, "PE")].premium == pytest.approx(146.70)
    assert states[0].lot_size == 65
    # Net credit: 10 lots x 609.00 pts collected, 5 lots x 269.85 paid.
    assert states[0].net_credit_rs == pytest.approx(
        (609.00 * 10 - 269.85 * 5) * 65, rel=1e-9)
    assert abs(spot - 22_811.35) < 1e-9


def test_all_window_marks_are_real(real):
    _, states = real
    types = [m.mark_type for st in states for m in st.marks.values()]
    assert len(types) == 40
    assert set(types) == {book.MARK_REAL}


def test_short_vol_book_greek_signs(real):
    _, states = real
    s0 = states[0]
    assert s0.gamma_per_point < 0       # short gamma
    assert s0.theta_rs_day > 0          # collects decay
    assert s0.vega_rs_point < 0         # short vol


def test_marking_falls_back_to_model_when_print_missing(window):
    days = data.window_days(window)
    positions = book.build_book(data.day_chain(window, days[0]))
    states = book.build_states(positions, window, days[:5])
    day5 = data.day_chain(window, days[5])
    real_premium = float(day5[(day5["strike"] == 23_250.0)
                              & (day5["kind"] == "CE")]["premium"].iloc[0])
    broken = day5[~((day5["strike"] == 23_250.0)
                    & (day5["kind"] == "CE"))].reset_index(drop=True)
    st = mark_day(positions, broken, prev_state=states[-1])
    m = st.marks[(23_250.0, "CE")]
    assert m.mark_type == book.MARK_MODEL
    assert m.premium > 0
    # The smile-fit model mark should sit in the neighbourhood of the
    # print it replaced -- same order of magnitude, not a fantasy.
    assert m.premium == pytest.approx(real_premium, rel=0.6)
    others = [st.marks[p.key].mark_type for p in positions
              if p.key != (23_250.0, "CE")]
    assert set(others) == {book.MARK_REAL}


def test_marking_falls_back_to_stale_without_smile():
    pos_a = Position(20_000.0, "CE", 1.0)
    pos_b = Position(19_500.0, "PE", 1.0)
    prev = synthetic_state([pos_a, pos_b], date(2026, 1, 1), 20_000.0,
                           30 / 365, {pos_a.key: 0.15, pos_b.key: 0.15})
    # A chain with only pos_a's row: 1 smile point (< 3), so pos_b
    # cannot be model-marked and must carry its last mark.
    chain = pd.DataFrame({
        "trade_date": [date(2026, 1, 2)], "expiry": [date(2026, 1, 31)],
        "strike": [20_000.0], "kind": ["CE"], "premium": [310.0],
        "spot": [20_100.0], "oi": [1_000.0], "volume": [10.0],
        "lot_size": [65.0]})
    st = mark_day([pos_a, pos_b], chain, prev_state=prev)
    assert st.marks[pos_a.key].mark_type == book.MARK_REAL
    assert st.marks[pos_b.key].mark_type == book.MARK_STALE
    assert st.marks[pos_b.key].premium == prev.marks[pos_b.key].premium


def test_smile_curve_is_sane_on_real_chain(window):
    days = data.window_days(window)
    chain = data.day_chain(window, days[0])
    spot = float(chain["spot"].iloc[0])
    T = (chain["expiry"].iloc[0] - days[0]).days / 365
    xs, ys = book.smile_points(chain, spot, T)
    assert len(xs) >= 20
    curve = book.smile_curve(xs, ys)
    assert curve is not None
    for K in (0.97 * spot, spot, 1.03 * spot):
        assert 0.05 < curve(K, spot) < 0.60


# ------------------------------------------------------- hedge engine

def _flat_states():
    pos = Position(20_000.0, "CE", -10.0)
    ivs = {pos.key: 0.15}
    d0 = synthetic_state([pos], date(2026, 1, 1), 20_000.0, 30 / 365, ivs)
    d1 = synthetic_state([pos], date(2026, 1, 2), 20_000.0, 30 / 365, ivs)
    return [pos], [d0, d1]


def test_flat_market_hedged_book_has_zero_pnl():
    positions, states = _flat_states()
    strat = Strategy("daily-free", "daily", slippage_bps=0.0)
    sim = engine.simulate(states, strat)
    assert sim.option_pnl == pytest.approx(0.0, abs=1e-8)
    assert sim.hedge_pnl == pytest.approx(0.0, abs=1e-8)
    assert sim.total_pnl == pytest.approx(0.0, abs=1e-8)


def test_flat_market_costs_are_the_only_drag():
    positions, states = _flat_states()
    sim = engine.simulate(states, Strategy("daily", "daily"))
    assert sim.total_pnl == pytest.approx(-sim.total_costs, abs=1e-8)
    assert sim.total_costs > 0


def test_band_does_not_trade_inside_band():
    pos = Position(20_000.0, "CE", -1.0)   # |delta| ~ 32 units < band
    ivs = {pos.key: 0.15}
    states = [synthetic_state([pos], date(2026, 1, 1) + timedelta(days=i),
                              20_000.0, 30 / 365, ivs) for i in range(3)]
    sim = engine.simulate(states, Strategy("band", "band",
                                           band_units=100.0))
    assert sim.trades == []
    assert sim.turnover_units == 0.0


def test_band_trades_when_delta_breaches():
    pos = Position(20_000.0, "CE", -10.0)  # |book delta| ~ 318 > band
    ivs = {pos.key: 0.15}
    states = [synthetic_state([pos], date(2026, 1, 1) + timedelta(days=i),
                              20_000.0, 30 / 365, ivs) for i in range(2)]
    sim = engine.simulate(states, Strategy("band", "band",
                                           band_units=100.0))
    assert len(sim.trades) >= 1
    assert sim.intervals[0].hedge_held == pytest.approx(
        -states[0].delta_units)


def test_hedge_pnl_is_units_times_spot_move():
    pos = Position(20_000.0, "CE", -10.0)
    ivs = {pos.key: 0.15}
    s0 = synthetic_state([pos], date(2026, 1, 1), 20_000.0, 30 / 365, ivs)
    s1 = synthetic_state([pos], date(2026, 1, 2), 20_250.0, 29 / 365, ivs)
    sim = engine.simulate([s0, s1], Strategy("d", "daily",
                                             slippage_bps=0.0))
    iv = sim.intervals[0]
    assert iv.hedge_held == pytest.approx(-s0.delta_units)
    assert iv.hedge_pnl == pytest.approx(iv.hedge_held * 250.0)
    assert iv.option_pnl == pytest.approx(
        s1.book_value_rs - s0.book_value_rs)


def test_engine_accounting_identity_real(real):
    positions, states = real
    for strat in engine.STRATEGIES:
        sim = engine.simulate(states, strat)
        assert sim.total_pnl == pytest.approx(
            sim.option_pnl + sim.hedge_pnl - sim.total_costs, abs=1e-6)
        cum = sim.cumulative()
        assert cum[-1] == pytest.approx(sim.total_pnl, abs=1e-6)
        assert len(cum) == len(states)


def test_band_turnover_below_daily_on_real_window(real):
    _, states = real
    daily = engine.simulate(states, engine.STRATEGIES[1])
    band = engine.simulate(states, engine.STRATEGIES[2])
    assert band.turnover_units < daily.turnover_units
    assert band.total_costs < daily.total_costs
    assert len(band.trades) < len(daily.trades)


def test_higher_slippage_never_helps(real):
    _, states = real
    cheap = engine.simulate(states, Strategy("c", "daily",
                                             slippage_bps=0.5))
    dear = engine.simulate(states, Strategy("d", "daily",
                                            slippage_bps=10.0))
    assert dear.total_pnl < cheap.total_pnl
    assert dear.total_costs > cheap.total_costs


# --------------------------------------------------------- attribution

def test_attribution_identity_on_synthetic_known_greeks():
    pos = Position(20_000.0, "CE", 1.0)
    iv0 = {pos.key: 0.150}
    iv1 = {pos.key: 0.155}
    s0 = synthetic_state([pos], date(2026, 1, 1), 20_000.0, 30 / 365, iv0)
    s1 = synthetic_state([pos], date(2026, 1, 2), 20_040.0, 29 / 365, iv1)
    held = -s0.delta_units                       # re-hedged flat at t
    hedge_pnl = held * 40.0
    option_pnl = s1.book_value_rs - s0.book_value_rs
    interval = Interval(day_from=s0.day, day_to=s1.day, spot_from=20_000.0,
                        spot_to=20_040.0, option_pnl=option_pnl,
                        hedge_pnl=hedge_pnl, costs=0.0, hedge_held=held,
                        delta_start=s0.delta_units)
    row = attribution.attribute_interval(s0, s1, interval, [pos])
    # Fully hedged: the delta term must cancel the hedge exactly.
    assert row.delta_net == pytest.approx(0.0, abs=1e-6)
    # Short-horizon Taylor remainder must be small vs the gross Greeks.
    gross = abs(row.theta) + abs(row.gamma) + abs(row.vega)
    assert gross > 0
    assert abs(row.residual) < 0.02 * gross
    assert row.explained + row.residual == pytest.approx(row.total,
                                                         abs=1e-6)


def test_attribution_sums_to_actual_on_real_window(real):
    positions, states = real
    sim = engine.simulate(states, engine.STRATEGIES[1])
    rows, totals = attribution.attribute_strategy(states, sim, positions)
    assert totals["total"] == pytest.approx(sim.total_pnl, abs=1e-6)
    for r in rows:
        assert r.explained + r.residual == pytest.approx(r.total,
                                                         abs=1e-6)
    # Daily hedging flattens delta at every close: net delta P&L = 0.
    assert totals["delta_net"] == pytest.approx(0.0, abs=1e-6)
    # The short-vol book's economics: theta earned, gamma paid.
    assert totals["theta"] > 0
    assert totals["gamma"] < 0


def test_unhedged_attribution_keeps_full_delta(real):
    positions, states = real
    sim = engine.simulate(states, engine.STRATEGIES[0])
    _, totals = attribution.attribute_strategy(states, sim, positions)
    assert totals["hedge_pnl"] == 0.0
    assert totals["delta_net"] == pytest.approx(totals["delta_gross"],
                                                abs=1e-9)
    assert totals["delta_gross"] != pytest.approx(0.0, abs=1.0)
