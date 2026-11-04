"""The book, its daily marks, and its aggregate Greeks.

Book (opened at day-0 real settlement prints, held for the window):

  * short 10 lots ATM straddle  (strike nearest day-0 spot)
  * long  5 lots wing call      (listed strike nearest 1.02 x day-0 spot)
  * long  5 lots wing put       (listed strike nearest 0.98 x day-0 spot)

That is an iron-fly-like short-volatility book: it collects the
straddle premium, pays some of it back for wings that cap the tail,
and bleeds or earns through gamma as spot moves.

MARKING RULE (one rule, applied identically every day, stated here and
in the README):

  1. REAL  -- the day's own settlement print (ClsPric) for that
     strike/kind/expiry, when a row exists with premium > 0 and
     open interest > 0.
  2. MODEL -- otherwise, a Black-Scholes price using the IV
     interpolated from that day's own OTM smile (log-moneyness
     interpolation, flat extrapolation), when the smile has >= 3
     solvable points.
  3. STALE -- otherwise, the position's last available mark carried
     forward.

Every mark carries its type, and the report counts how many marks of
each type the study used.

GREEKS IV RULE: Greeks (and therefore hedging and attribution) always
use the IV of a smoothed smile fitted to the day's OTM prints
(quadratic in log-moneyness, least squares) evaluated at the
position's strike -- never the IV of a single settlement print.
Individual prints on this feed are not arbitrage-consistent: deep-ITM
prints imply vols several points away from the smile around them (on
2 Nov 2026 the 23,250 call printed a 7.6% IV while the smile around it
sat near 19%), and put-call parity breaks by several vol points at the
money, which makes raw per-print IVs whipsaw as spot crosses the kink.
Desks compute risk off a smoothed surface for exactly this reason; the
premium P&L, however, is always the real print's P&L.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np

from . import greeks as _g
from .pricing import bs_price, implied_vol

DEFAULT_RATE = 0.065
DEFAULT_DIV = 0.0

MARK_REAL, MARK_MODEL, MARK_STALE = "REAL", "MODEL", "STALE"


@dataclass(frozen=True)
class Position:
    strike: float
    kind: str          # 'CE' or 'PE'
    lots: float        # signed: + long, - short
    label: str = ""

    @property
    def key(self):
        return (self.strike, self.kind)


@dataclass
class Mark:
    premium: float
    iv: float
    mark_type: str     # REAL / MODEL / STALE
    iv_source: str     # 'own print' / 'smile interp' / 'carried'


@dataclass
class DayState:
    """Everything known at one day's close: marks + aggregate Greeks."""
    day: date
    spot: float
    T: float                       # years to expiry (calendar days / 365)
    days_to_expiry: int
    lot_size: float
    marks: dict                    # Position.key -> Mark
    greeks: dict                   # per Position.key -> per-unit greeks
    delta_units: float             # book delta in underlying units
    gamma_per_point: float         # change in delta-units per index point
    theta_rs_day: float            # book theta, ₹ per calendar day
    vega_rs_point: float           # book vega, ₹ per vol point
    book_value_rs: float           # liquidation value Σ qty x premium (₹)
    net_credit_rs: float = 0.0     # day-0 only: premium collected (₹)


def build_book(day0_chain, straddle_lots=10, wing_lots=5, wing_pct=0.02):
    """Construct the book from day 0's listed strikes.

    ATM = listed strike nearest day-0 spot; wings = listed strikes
    nearest (1 +/- wing_pct) x day-0 spot on their respective sides.
    """
    spot = float(day0_chain["spot"].iloc[0])
    strikes = np.sort(day0_chain["strike"].unique())

    def nearest(target):
        return float(strikes[np.argmin(np.abs(strikes - target))])

    atm = nearest(spot)
    wing_up = nearest(spot * (1 + wing_pct))
    wing_dn = nearest(spot * (1 - wing_pct))
    positions = [
        Position(atm, "CE", -float(straddle_lots), "short ATM call"),
        Position(atm, "PE", -float(straddle_lots), "short ATM put"),
        Position(wing_up, "CE", float(wing_lots), "long wing call"),
        Position(wing_dn, "PE", float(wing_lots), "long wing put"),
    ]
    return positions


def smile_points(chain, spot, T, r=DEFAULT_RATE, q=DEFAULT_DIV):
    """Solvable OTM IVs of one day's chain, as (log-moneyness, IV).

    OTM convention: calls with strike >= spot, puts with strike <=
    spot -- the strikes whose prints carry genuine time value.
    """
    xs, ys = [], []
    for row in chain.itertuples():
        otm = (row.kind == "CE" and row.strike >= spot) or \
              (row.kind == "PE" and row.strike <= spot)
        if not otm or row.premium <= 0 or row.oi <= 0:
            continue
        iv = implied_vol(row.premium, spot, row.strike, T, r, q, row.kind)
        if np.isfinite(iv) and iv > 0:
            xs.append(np.log(row.strike / spot))
            ys.append(iv)
    if not xs:
        return np.array([]), np.array([])
    order = np.argsort(xs)
    xs, ys = np.array(xs)[order], np.array(ys)[order]
    # Collapse duplicate log-moneyness (CE/PE at the same strike).
    uniq, idx = np.unique(xs, return_index=True)
    return uniq, ys[idx]


def smile_iv_at(xs, ys, spot, strike):
    """Smile IV at a strike: log-moneyness interp, flat extrapolation."""
    if len(xs) == 0:
        return float("nan")
    return float(np.interp(np.log(strike / spot), xs, ys))


def smile_curve(xs, ys):
    """A smoothed smile: quadratic in log-moneyness, least-squares
    fit through the day's OTM IV points (the standard desk smile
    fit -- a parametric curve through the prints, not the prints
    themselves).

    Returns a function strike -> IV, or None when there are too few
    points to fit (< 6), in which case callers use raw interpolation.
    The fit is what keeps a fixed strike's risk IV from whipsawing
    when spot crosses the put/call parity kink at the money: the raw
    prints jump several vol points there, the fitted curve does not.
    """
    if len(xs) < 6:
        return None
    coef = np.polyfit(xs, ys, 2)

    def iv_at(strike, spot):
        v = float(np.polyval(coef, np.log(strike / spot)))
        return min(max(v, 0.02), 2.0)

    return iv_at


def mark_day(positions, chain, prev_state=None, r=DEFAULT_RATE, q=DEFAULT_DIV):
    """Mark every position on one day's chain and aggregate the Greeks.

    ``chain`` is one day's slice (see data.day_chain); ``prev_state``
    is yesterday's DayState, used only for the STALE fallback.
    """
    day = chain["trade_date"].iloc[0]
    expiry = chain["expiry"].iloc[0]
    spot = float(chain["spot"].iloc[0])
    lot = float(chain["lot_size"].iloc[0])
    days = (expiry - day).days
    T = days / 365.0
    xs, ys = smile_points(chain, spot, T, r, q)
    curve = smile_curve(xs, ys)

    def smile_at(strike):
        return curve(strike, spot) if curve is not None \
            else smile_iv_at(xs, ys, spot, strike)

    lookup = {(float(row.strike), row.kind): row for row in chain.itertuples()}

    marks, per_pos_greeks = {}, {}
    delta_units = gamma_pp = theta_rs = vega_rs = value_rs = 0.0
    for pos in positions:
        row = lookup.get(pos.key)
        # Greeks IV: the day's fitted smile at this strike (see docstring).
        if len(xs) >= 3:
            greek_iv, greek_iv_src = smile_at(pos.strike), "smile fit"
        elif row is not None and row.premium > 0 and row.oi > 0:
            own = implied_vol(row.premium, spot, pos.strike, T, r, q,
                              pos.kind)
            greek_iv, greek_iv_src = own, "own print (no smile)"
        else:
            greek_iv, greek_iv_src = float("nan"), "none"
        if row is not None and row.premium > 0 and row.oi > 0:
            premium, mtype = float(row.premium), MARK_REAL
            iv, iv_src = greek_iv, greek_iv_src
        elif len(xs) >= 3:
            iv = smile_at(pos.strike)
            premium, mtype, iv_src = bs_price(spot, pos.strike, T, r, q, iv,
                                              pos.kind), MARK_MODEL, "smile fit"
        elif prev_state is not None and pos.key in prev_state.marks:
            prev = prev_state.marks[pos.key]
            premium, iv, mtype, iv_src = prev.premium, prev.iv, MARK_STALE, "carried"
        else:
            raise ValueError(f"cannot mark {pos.key} on {day}: no print, "
                             "no smile, no prior mark")
        marks[pos.key] = Mark(premium=premium, iv=iv, mark_type=mtype,
                              iv_source=iv_src)
        gk = _g.all_greeks(spot, pos.strike, T, r, q, iv, pos.kind)
        per_pos_greeks[pos.key] = gk
        qty_units = pos.lots * lot
        delta_units += qty_units * gk["delta"]
        gamma_pp += qty_units * gk["gamma"]
        theta_rs += qty_units * gk["theta"]
        vega_rs += qty_units * gk["vega"]
        value_rs += qty_units * premium
    return DayState(day=day, spot=spot, T=T, days_to_expiry=days,
                    lot_size=lot, marks=marks, greeks=per_pos_greeks,
                    delta_units=delta_units, gamma_per_point=gamma_pp,
                    theta_rs_day=theta_rs, vega_rs_point=vega_rs,
                    book_value_rs=value_rs)


def build_states(positions, window_df, days):
    """Mark the book across the whole window, in order (STALE needs it)."""
    from .data import day_chain
    states, prev = [], None
    for d in days:
        state = mark_day(positions, day_chain(window_df, d), prev_state=prev)
        states.append(state)
        prev = state
    if states:
        # Opening the book at day-0 prints: shorts collect, longs pay.
        states[0].net_credit_rs = -states[0].book_value_rs
    return states


def synthetic_state(positions, day, spot, T, iv_by_key, lot_size=65.0,
                    days_to_expiry=None):
    """A DayState priced entirely from Black-Scholes at given IVs.

    Used by the test suite (and synthetic sanity checks) so the engine
    and attribution can be exercised on data whose true P&L is known
    analytically, with no bhavcopy involved.
    """
    marks, per_pos_greeks = {}, {}
    delta_units = gamma_pp = theta_rs = vega_rs = value_rs = 0.0
    r, q = DEFAULT_RATE, DEFAULT_DIV
    for pos in positions:
        iv = iv_by_key[pos.key]
        premium = bs_price(spot, pos.strike, T, r, q, iv, pos.kind)
        marks[pos.key] = Mark(premium=premium, iv=iv, mark_type="SYNTH",
                              iv_source="synthetic")
        gk = _g.all_greeks(spot, pos.strike, T, r, q, iv, pos.kind)
        per_pos_greeks[pos.key] = gk
        qty_units = pos.lots * lot_size
        delta_units += qty_units * gk["delta"]
        gamma_pp += qty_units * gk["gamma"]
        theta_rs += qty_units * gk["theta"]
        vega_rs += qty_units * gk["vega"]
        value_rs += qty_units * premium
    return DayState(day=day, spot=spot, T=T,
                    days_to_expiry=(days_to_expiry if days_to_expiry
                                    is not None else int(round(T * 365))),
                    lot_size=lot_size, marks=marks, greeks=per_pos_greeks,
                    delta_units=delta_units, gamma_per_point=gamma_pp,
                    theta_rs_day=theta_rs, vega_rs_point=vega_rs,
                    book_value_rs=value_rs)
