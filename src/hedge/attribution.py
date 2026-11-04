"""Greeks P&L attribution: explaining a hedged book's P&L, Greek by Greek.

For each interval (close t -> close t+1) the option book's P&L is
expanded around the *start-of-interval* state -- that day's real
Greeks, computed from that day's real smile:

  delta   = Δ_t x (S_{t+1} - S_t)                    [₹]
  gamma   = 1/2 Γ_t x (S_{t+1} - S_t)^2              [₹]
  theta   = Θ_t x (calendar days in the interval)    [₹]
  vega    = Σ_positions ν_t x (σ_{t+1} - σ_t)        [₹, per-position IVs]

where Δ_t, Γ_t, Θ_t are book aggregates in ₹-consistent units (delta
in underlying units, gamma in delta-units per point, theta in ₹/day)
and ν is per vol point. The hedge's own P&L is then netted against
the delta term -- ``delta_net = delta + hedge P&L`` -- which is
exactly 0 for a book re-hedged to flat at close t, and is the
band strategy's leftover directional bet otherwise:

  total P&L = delta_net + gamma + theta + vega - costs + residual

The residual is whatever the second-order Taylor expansion cannot
explain: smile reshaping (each strike's IV moving differently),
cross terms (vanna: delta changing *because* vol moved), gamma
changing as spot travels, and settlement-print noise. It is reported,
never swept away -- its size relative to |P&L| is the honesty metric
of the whole attribution.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AttributionRow:
    day_from: object
    day_to: object
    spot_move: float
    days: int
    delta_gross: float      # option-book delta P&L before the hedge
    hedge_pnl: float
    delta_net: float        # delta_gross + hedge_pnl
    gamma: float
    theta: float
    vega: float
    costs: float
    residual: float
    total: float            # actual interval P&L (from the engine)

    @property
    def explained(self):
        return self.delta_net + self.gamma + self.theta + self.vega \
            - self.costs


def attribute_interval(state_t, state_t1, interval, positions):
    """Decompose one interval of one strategy's P&L."""
    dS = state_t1.spot - state_t.spot
    days = (state_t1.day - state_t.day).days
    lot = state_t.lot_size
    vega = 0.0
    for pos in positions:
        qty_units = pos.lots * lot
        m0, m1 = state_t.marks[pos.key], state_t1.marks[pos.key]
        vega += qty_units * state_t.greeks[pos.key]["vega"] \
            * (m1.iv - m0.iv) * 100.0     # IV change in vol points
    delta_gross = state_t.delta_units * dS
    gamma = 0.5 * state_t.gamma_per_point * dS**2
    theta = state_t.theta_rs_day * days
    delta_net = delta_gross + interval.hedge_pnl
    total = interval.total_pnl
    residual = total - (delta_net + gamma + theta + vega - interval.costs)
    return AttributionRow(
        day_from=state_t.day, day_to=state_t1.day, spot_move=dS, days=days,
        delta_gross=delta_gross, hedge_pnl=interval.hedge_pnl,
        delta_net=delta_net, gamma=gamma, theta=theta, vega=vega,
        costs=interval.costs, residual=residual, total=total)


def attribute_strategy(states, sim_result, positions):
    """Attribute every interval of a simulation; returns (rows, totals)."""
    rows = [attribute_interval(states[i], states[i + 1],
                               sim_result.intervals[i], positions)
            for i in range(len(sim_result.intervals))]
    fields = ["delta_gross", "hedge_pnl", "delta_net", "gamma", "theta",
              "vega", "costs", "residual", "total"]
    totals = {f: sum(getattr(r, f) for r in rows) for f in fields}
    return rows, totals
