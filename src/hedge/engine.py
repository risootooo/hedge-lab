"""Delta-hedging simulation across the real window.

Three strategies run over the SAME day states (same marks, same real
premiums) so the comparison is purely about hedging policy:

  * ``none``  -- no hedge at all. The book eats its full delta.
  * ``daily`` -- rebalance the hedge to exactly -book delta at every
    close.
  * ``band``  -- rebalance to exactly -book delta only when the net
    delta (book delta + hedge held) breaches +/- ``band_units`` at a
    close; otherwise hold. This is the standard desk compromise:
    fewer trades, some delta left on.

Hedge instrument: NIFTY futures as the tradable proxy for the index,
executed at the day's real index print (basis ignored -- stated in
the README), in exact underlying units (fractional-lot simplification,
also stated). Every hedge trade pays slippage of ``slippage_bps``
basis points of notional. Option entry/exit are at the real
settlement prints with no added cost (the window opens and closes by
marking, not by crossing a spread).

Timeline, per interval (close t -> close t+1):
  option P&L  = book value change (marks are real prints)
  hedge P&L   = hedge units held during the interval x (S_{t+1} - S_t)
  costs       = slippage on the trade executed at close t (the
                rebalance that sets up the interval); the final
                close flattens any residual hedge and its cost lands
                in the last interval.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

DEFAULT_SLIPPAGE_BPS = 2.0
DEFAULT_BAND_UNITS = 100.0   # ~1.5 lots of 65


@dataclass
class Strategy:
    name: str
    mode: str                       # 'none' | 'daily' | 'band'
    band_units: float = DEFAULT_BAND_UNITS
    slippage_bps: float = DEFAULT_SLIPPAGE_BPS


STRATEGIES = [
    Strategy("Unhedged", "none"),
    Strategy("Daily delta hedge", "daily"),
    Strategy("Band hedge (±100 units)", "band"),
]


@dataclass
class Interval:
    day_from: object
    day_to: object
    spot_from: float
    spot_to: float
    option_pnl: float
    hedge_pnl: float
    costs: float
    hedge_held: float               # units held during the interval
    delta_start: float              # book delta at close t (units)

    @property
    def total_pnl(self):
        return self.option_pnl + self.hedge_pnl - self.costs


@dataclass
class SimResult:
    strategy: Strategy
    intervals: list = field(default_factory=list)
    trades: list = field(default_factory=list)   # (day, units, cost_rs)
    turnover_units: float = 0.0
    total_costs: float = 0.0

    @property
    def total_pnl(self):
        return sum(iv.total_pnl for iv in self.intervals)

    @property
    def option_pnl(self):
        return sum(iv.option_pnl for iv in self.intervals)

    @property
    def hedge_pnl(self):
        return sum(iv.hedge_pnl for iv in self.intervals)

    @property
    def max_adverse_day(self):
        """Worst single-interval P&L (₹) and the interval it fell in."""
        worst = min(self.intervals, key=lambda iv: iv.total_pnl)
        return worst.total_pnl, worst.day_from, worst.day_to

    def daily_pnl_std(self):
        if len(self.intervals) < 2:
            return 0.0
        return float(np.std([iv.total_pnl for iv in self.intervals],
                            ddof=1))

    def cumulative(self):
        """Cumulative P&L at each close, starting at 0 on day 0."""
        out = [0.0]
        for iv in self.intervals:
            out.append(out[-1] + iv.total_pnl)
        return out


def target_hedge(strategy: Strategy, book_delta: float, hedge_held: float):
    """Hedge position (underlying units) wanted after this close."""
    if strategy.mode == "none":
        return 0.0
    if strategy.mode == "daily":
        return -book_delta
    if strategy.mode == "band":
        net = book_delta + hedge_held
        return -book_delta if abs(net) > strategy.band_units else hedge_held
    raise ValueError(f"unknown strategy mode {strategy.mode!r}")


def simulate(states, strategy: Strategy) -> SimResult:
    """Run one hedging strategy over pre-computed day states."""
    res = SimResult(strategy=strategy)
    n = len(states)
    hedge = 0.0
    held_after_close = []       # hedge units in force after each close
    close_cost = [0.0] * n      # slippage paid at each close
    for i, st in enumerate(states):
        last = i == n - 1
        target = 0.0 if last else target_hedge(strategy, st.delta_units,
                                               hedge)
        trade = target - hedge
        if abs(trade) > 1e-9:
            cost = abs(trade) * st.spot * strategy.slippage_bps / 10_000.0
            res.trades.append((st.day, trade, cost))
            res.turnover_units += abs(trade)
            res.total_costs += cost
            close_cost[i] = cost
            hedge = target
        held_after_close.append(hedge)
    for i in range(1, n):
        prev, st = states[i - 1], states[i]
        held = held_after_close[i - 1]
        costs = close_cost[i - 1] + (close_cost[i] if i == n - 1 else 0.0)
        res.intervals.append(Interval(
            day_from=prev.day, day_to=st.day,
            spot_from=prev.spot, spot_to=st.spot,
            option_pnl=st.book_value_rs - prev.book_value_rs,
            hedge_pnl=held * (st.spot - prev.spot),
            costs=costs, hedge_held=held, delta_start=prev.delta_units))
    return res
