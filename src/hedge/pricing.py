"""Black-Scholes-Merton pricing and an implied-volatility solver.

Conventions (used across the whole repo):
  S     spot of the underlying (NIFTY index level)
  K     strike
  T     time to expiry in years, actual calendar days / 365
  r     continuously compounded risk-free rate (0.065 throughout)
  q     continuously compounded dividend yield (0.0 for cash-settled
        index options in this study)
  sigma annualised implied volatility (decimal, e.g. 0.15)
  kind  'CE' (call) or 'PE' (put) -- NSE option-type codes
"""

from __future__ import annotations

import numpy as np
from scipy.stats import norm

__all__ = ["bs_price", "implied_vol", "d1_d2", "intrinsic"]

IV_FLOOR, IV_CAP = 1e-4, 4.0


def _check_kind(kind: str) -> str:
    k = str(kind).upper()
    if k in ("CE", "C", "CALL"):
        return "CE"
    if k in ("PE", "P", "PUT"):
        return "PE"
    raise ValueError(f"unknown option kind {kind!r}; use 'CE' or 'PE'")


def intrinsic(S: float, K: float, kind: str) -> float:
    kind = _check_kind(kind)
    return max(S - K, 0.0) if kind == "CE" else max(K - S, 0.0)


def d1_d2(S, K, T, r, q, sigma):
    """Black-Scholes d1 and d2 (array-safe)."""
    S, K, T, sigma = (np.asarray(x, dtype=float) for x in (S, K, T, sigma))
    vol_sqrt_t = sigma * np.sqrt(T)
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / vol_sqrt_t
    d2 = d1 - vol_sqrt_t
    return d1, d2


def bs_price(S, K, T, r, q, sigma, kind):
    """Black-Scholes-Merton European option price."""
    kind = _check_kind(kind)
    S = np.asarray(S, dtype=float)
    K = np.asarray(K, dtype=float)
    T = np.asarray(T, dtype=float)
    sigma = np.asarray(sigma, dtype=float)
    intr = np.maximum(S - K, 0.0) if kind == "CE" else np.maximum(K - S, 0.0)
    live = (T > 0) & (sigma > 0)
    if not np.any(live):
        return float(intr) if np.ndim(intr) == 0 else intr
    d1, d2 = d1_d2(np.where(live, S, 1.0), np.where(live, K, 1.0),
                   np.where(live, T, 1.0), r, q, np.where(live, sigma, 1.0))
    if kind == "CE":
        price = (S * np.exp(-q * T) * norm.cdf(d1)
                 - K * np.exp(-r * T) * norm.cdf(d2))
    else:
        price = (K * np.exp(-r * T) * norm.cdf(-d2)
                 - S * np.exp(-q * T) * norm.cdf(-d1))
    price = np.where(live, price, intr)
    return float(price) if np.ndim(price) == 0 else price


def implied_vol(price, S, K, T, r, q, kind, tol=1e-10, max_iter=100):
    """Implied vol of one option, or NaN when no arbitrage-consistent
    Black-Scholes vol exists for the print.

    NSE settlement prints *do* violate the no-arbitrage lower bound on
    some strikes (documented in the sibling greeks-lab repo). Returning
    NaN there -- instead of a fantasy vol -- is deliberate: callers fall
    back to smile interpolation and the mark is flagged.
    """
    kind = _check_kind(kind)
    if price is None or not np.isfinite(price) or T <= 0:
        return float("nan")
    lower = max(intrinsic(S * np.exp(-q * T), K * np.exp(-r * T), kind), 0.0)
    if price < lower - 1e-9:
        return float("nan")
    if price <= lower + 1e-12:
        return 0.0
    # Newton from a Brenner-Subrahmanyam style seed.
    sigma = max(np.sqrt(2 * np.pi / T) * price / S, 0.05) if S > 0 else 0.2
    sigma = min(max(sigma, IV_FLOOR), IV_CAP)
    from .greeks import vega as _vega  # local import: greeks imports pricing
    for _ in range(max_iter):
        diff = bs_price(S, K, T, r, q, sigma, kind) - price
        if abs(diff) < tol:
            return float(sigma)
        v = _vega(S, K, T, r, q, sigma) * 100.0  # per 1.00 of sigma
        if v < 1e-10:
            break
        sigma -= diff / v
        if sigma <= IV_FLOOR or sigma >= IV_CAP or not np.isfinite(sigma):
            break
    # Bisection fallback: BS price is monotone in sigma, so this brackets.
    lo, hi = IV_FLOOR, IV_CAP
    p_lo = bs_price(S, K, T, r, q, lo, kind)
    p_hi = bs_price(S, K, T, r, q, hi, kind)
    if not (p_lo <= price <= p_hi):
        return float("nan")
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if bs_price(S, K, T, r, q, mid, kind) < price:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-10:
            break
    return float(0.5 * (lo + hi))
