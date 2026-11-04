# Hedge Lab

![Python](https://img.shields.io/badge/python-3.11+-blue)
![Tests](https://img.shields.io/badge/tests-28%20passed-brightgreen)
![Data](https://img.shields.io/badge/data-real%20NSE%20bhavcopy-orange)
![License](https://img.shields.io/badge/license-MIT-green)

**A trading-desk simulator for the two jobs an options book actually
consists of: hedge it, then explain it.** Hedge Lab opens a real
short-volatility NIFTY book at real settlement prints, marks it on 10
consecutive real trading days, delta-hedges it three different ways
with futures at the real index level — and then attributes every
rupee of the hedged book's P&L to theta, gamma, vega, net delta and an
honestly-reported residual.

> Unhedged, the book lost **−₹139,912** as NIFTY rallied +4.38%.
> Daily delta-hedging turned that into **+₹32,183** on identical
> option marks. The attribution verdict: theta earned **+₹93,302**,
> gamma cost **−₹73,102**, vega cost **−₹55,080** — and the one
> interval no Greek model can explain is named, sized and dated.

Part of a derivatives research suite built on the same real NSE data:
[greeks-lab](https://github.com/risootooo/greeks-lab) (pricing &
chain analytics) · [vol-surface-atlas](https://github.com/risootooo/vol-surface-atlas)
(vol surface dynamics).

## The study

**Window** — 21 Oct → 3 Nov 2026, 10 consecutive real trading days,
one expiry (9 Nov 2026), lot 65 read from the file. Spot
22,811.35 → 23,810.85 (+999.50 pts). Source: NSE F&O bhavcopy,
extracted to `data/book_window.csv` (1,284 rows, provenance in
`data/PROVENANCE.md`); the whole study replays offline from it.

**Book** — opened at day-0 real prints, held throughout:

| Leg | Position | Day-0 print | Day-0 role |
|---|---|---|---|
| 22,800 CE | short 10 lots | 297.90 | straddle |
| 22,800 PE | short 10 lots | 311.10 | straddle |
| 23,250 CE | long 5 lots | 123.15 | wing (+2%) |
| 22,350 PE | long 5 lots | 146.70 | wing (−2%) |

Net credit **₹308,149**. Day-0 Greeks: delta −48 units,
gamma −0.391/pt, theta +₹5,966/day, vega −₹15,349/vol pt.

## Headline results

| Strategy | Total P&L | Hedge P&L | Costs | Turnover | Trades | Worst day | Daily σ |
|---|---|---|---|---|---|---|---|
| Unhedged | **−₹139,912** | — | — | 0 | 0 | −₹121,371 | ₹47,364 |
| Daily delta hedge | **+₹32,183** | +₹175,945 | ₹3,849 | 827 u | 10 | −₹19,512 | ₹13,592 |
| Band hedge (±100 u) | **+₹23,998** | +₹166,685 | ₹2,774 | 589 u | 3 | −₹19,841 | ₹16,332 |

Attribution of the daily-hedged book (totals, ₹): theta **+93,302** ·
gamma **−73,102** · vega **−55,080** · delta net of hedge **0**
(exactly — the hedge cancels gross delta P&L of −₹175,945 to the
rupee) · costs 3,849 · residual **+70,912** · total **+32,183**.
Full per-day table and the three cases are in
[docs/CASES.md](docs/CASES.md); the visual version is
[docs/dashboard.html](docs/dashboard.html).

## Methodology

**Marking (one rule, every day).** (1) REAL — the day's own
settlement print for that strike/kind/expiry when a row exists with
premium > 0 and OI > 0; (2) MODEL — a Black-Scholes price off that
day's fitted smile, when the smile has ≥ 3 points; (3) STALE — the
last mark carried. Every mark is typed and counted (this window:
40 REAL, 0 MODEL, 0 STALE).

**Greeks IV rule.** Greeks never come from a single settlement print.
Risk IVs are a smoothed smile — quadratic in log-moneyness,
least-squares through the day's OTM prints (calls above spot, puts
below) — evaluated at each strike. On this feed, individual prints
are not arbitrage-consistent (on 2 Nov the 23,250 call printed a 7.6%
IV against a ~19% smile; put-call parity breaks by several vol points
at the money on some days), and per-print IVs whipsaw as spot crosses
the parity kink. Premium P&L is always the real print's P&L; only the
risk sensitivities are smoothed — exactly how a desk runs it.

**Hedging.** Instrument: NIFTY futures as the tradable proxy, executed
at the day's real index print at each close, in exact underlying
units. Policies: none; daily (reset to −Δ every close); band (reset
to −Δ only when |book Δ + hedge| > 100 units at a close). Every hedge
trade pays 2 bps of notional slippage; the final close flattens the
residual hedge. Option entry/exit cross no spread (opened and closed
by marking).

**Attribution.** Per interval, around the start-of-day Greeks:

```
delta  = Δ_t × ΔS                 gamma = ½ Γ_t × (ΔS)²
theta  = Θ_t × calendar days      vega  = Σ ν_t × Δσ_strike (fitted smile)
delta_net = delta + hedge P&L     (≡ 0 when re-hedged flat)
total  = delta_net + gamma + theta + vega − costs + residual
```

The residual is what second order cannot explain — smile reshaping,
cross-Greeks (vanna/speed), gamma drift, settlement-print repricing —
and it is printed, per day, next to the numbers it failed to explain.

## Run it

```
pip install -r requirements.txt
python main.py            # full study -> console, docs/results.json,
                          # docs/dashboard.html
pytest                    # 28 tests
python tools/build_window.py   # regenerate data/book_window.csv
                               # from the raw bhavcopy archive
```

## Honest limitations

* **Settlement prints are not tradable ticks.** Bhavcopy closes are
  exchange marks (partly theoretical for illiquid strikes), so
  realised P&L here is mark-to-market P&L, not executable P&L. Entry
  and exit cross no bid/ask spread — real fills would be worse.
* **Parity breaks are in the data.** Settlement prints imply a
  forward away from spot on several days; the smile-fit Greeks rule
  contains the damage, and the attribution residual shows where it
  couldn't (one weekend interval owns 49% of the absolute residual).
* **Hedge proxy.** Futures are priced at the index print; the
  futures basis, margin funding and lot rounding (hedges are in exact
  units, ~1.5-lot granularity ignored) are all abstracted away.
  Costs are slippage only — no brokerage, STT or exchange fees.
* **One window, one book.** Ten days and a single short-vol structure
  is a case study in hedging mechanics, not a strategy backtest and
  not evidence about short-vol returns in general.
* The window ends 6 days before expiry; the book is marked out, not
  settled, so expiry pin risk never appears.

## Disclaimer

Research and education only. Nothing here is investment advice, a
recommendation, or an offer to trade any security or derivative.
Options hedging involves substantial risk; past mark-to-market
behaviour on one historical window says nothing about future results.
