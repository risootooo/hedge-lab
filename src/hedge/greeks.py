"""Analytic Black-Scholes Greeks in desk units.

Units (stated once, used everywhere in this repo):
  delta  per 1.00 move in the underlying (index point)
  gamma  change in delta per 1.00 move in the underlying
  theta  per *calendar day* of time passing (negative for long premium)
  vega   per 1 volatility *point* (sigma 0.15 -> 0.16)

``finite_diff_greek`` bump-and-reprices with Black-Scholes; the test
suite asserts analytic vs bumped agreement for delta, gamma, theta and
vega, so a wrong sign or a wrong 365/100 scaling cannot slip through.
"""

from __future__ import annotations

import numpy as np
from scipy.stats import norm

from .pricing import bs_price, d1_d2, _check_kind

__all__ = ["delta", "gamma", "theta", "vega", "all_greeks",
           "finite_diff_greek"]


def delta(S, K, T, r, q, sigma, kind):
    kind = _check_kind(kind)
    d1, _ = d1_d2(S, K, T, r, q, sigma)
    out = (np.exp(-q * T) * norm.cdf(d1) if kind == "CE"
           else -np.exp(-q * T) * norm.cdf(-d1))
    return float(out) if np.ndim(out) == 0 else out


def gamma(S, K, T, r, q, sigma, kind=None):
    """Gamma is identical for calls and puts at the same strike."""
    d1, _ = d1_d2(S, K, T, r, q, sigma)
    out = np.exp(-q * T) * norm.pdf(d1) / (S * sigma * np.sqrt(T))
    return float(out) if np.ndim(out) == 0 else out


def theta(S, K, T, r, q, sigma, kind):
    """Theta per calendar day (the desk convention)."""
    kind = _check_kind(kind)
    d1, d2 = d1_d2(S, K, T, r, q, sigma)
    common = -S * np.exp(-q * T) * norm.pdf(d1) * sigma / (2.0 * np.sqrt(T))
    if kind == "CE":
        per_year = (common - r * K * np.exp(-r * T) * norm.cdf(d2)
                    + q * S * np.exp(-q * T) * norm.cdf(d1))
    else:
        per_year = (common + r * K * np.exp(-r * T) * norm.cdf(-d2)
                    - q * S * np.exp(-q * T) * norm.cdf(-d1))
    out = per_year / 365.0
    return float(out) if np.ndim(out) == 0 else out


def vega(S, K, T, r, q, sigma, kind=None):
    """Vega per 1 volatility point (sigma + 0.01)."""
    d1, _ = d1_d2(S, K, T, r, q, sigma)
    out = S * np.exp(-q * T) * norm.pdf(d1) * np.sqrt(T) / 100.0
    return float(out) if np.ndim(out) == 0 else out


def all_greeks(S, K, T, r, q, sigma, kind):
    return {
        "delta": delta(S, K, T, r, q, sigma, kind),
        "gamma": gamma(S, K, T, r, q, sigma),
        "theta": theta(S, K, T, r, q, sigma, kind),
        "vega": vega(S, K, T, r, q, sigma),
    }


def finite_diff_greek(name, S, K, T, r, q, sigma, kind, bump=None):
    """Bump-and-reprice Greek, in the same units as the analytic ones."""
    name = name.lower()
    if name == "delta":
        h = bump or max(1e-4 * S, 1e-6)
        return (bs_price(S + h, K, T, r, q, sigma, kind)
                - bs_price(S - h, K, T, r, q, sigma, kind)) / (2 * h)
    if name == "gamma":
        h = bump or max(1e-3 * S, 1e-5)
        return (bs_price(S + h, K, T, r, q, sigma, kind)
                - 2 * bs_price(S, K, T, r, q, sigma, kind)
                + bs_price(S - h, K, T, r, q, sigma, kind)) / h**2
    if name == "theta":  # per calendar day, time passing
        h = bump or (0.5 / 365.0)
        return (bs_price(S, K, T - h, r, q, sigma, kind)
                - bs_price(S, K, T + h, r, q, sigma, kind)) / (2 * h * 365.0)
    if name == "vega":  # per 1 vol point
        h = bump or 1e-4
        return (bs_price(S, K, T, r, q, sigma + h, kind)
                - bs_price(S, K, T, r, q, sigma - h, kind)) / (2 * h) / 100.0
    raise ValueError(f"unknown greek {name!r}")
