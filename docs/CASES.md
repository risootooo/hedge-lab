# Cases — Hedge Lab on real NSE chains

**The window.** 10 consecutive real trading days, Wed 21 Oct → Tue
3 Nov 2026, one expiry (Mon 9 Nov 2026), lot size 65 read from the
file. Spot: 22,811.35 → 23,810.85 (**+999.50 pts, +4.38%**) — a steady
grind up for a week, then two big rally days (+388, +370) into the
3 Nov expiry weekend. Every premium below is that day's real
settlement print; all 40 position marks in the study are REAL (the
MODEL/STALE fallbacks exist in code and are unit-tested, but this
window never needed them).

**The book** (opened at day-0 prints, iron-fly-like short vol):

| Leg | Position | Day-0 print |
|---|---|---|
| 22,800 CE | short 10 lots | 297.90 |
| 22,800 PE | short 10 lots | 311.10 |
| 23,250 CE | long 5 lots | 123.15 |
| 22,350 PE | long 5 lots | 146.70 |

Net credit collected: **₹308,149**. Day-0 book Greeks (Greeks off the
day's fitted smile): delta −48 units, gamma −0.391/pt,
theta +₹5,966/day, vega −₹15,349/vol pt.

---

## Case A — the headline: hedging is the whole P&L

Same book, same real marks, three hedging policies:

| Strategy | Option P&L | Hedge P&L | Costs | **Total** | Worst day | Daily σ |
|---|---|---|---|---|---|---|
| Unhedged | −₹139,912 | — | — | **−₹139,912** | −₹121,371 (→ 3 Nov) | ₹47,364 |
| Daily delta hedge | −₹139,912 | +₹175,945 | ₹3,849 | **+₹32,183** | −₹19,512 (→ 23 Oct) | ₹13,592 |
| Band hedge (±100u) | −₹139,912 | +₹166,685 | ₹2,774 | **+₹23,998** | −₹19,841 (→ 23 Oct) | ₹16,332 |

The option book lost ₹139,912 on its own — spot rallied 1,000 points
against a short-gamma, short-delta-drift book, and the final day alone
(2 → 3 Nov, +370 pts with the straddle now deep in the money) cost
₹121,371 unhedged. The daily futures hedge earned ₹175,945 against
that loss: hedging didn't just reduce the damage, it *was* the P&L —
the difference between −₹139,912 and +₹32,183 on identical option
marks. Hedge cost drag was small but real: ₹3,849 of slippage on
827 units of turnover (10 trades, 2 bps per trade). Daily hedging cut
daily P&L volatility by 71% (σ ₹47,364 → ₹13,592).

## Case B — attribution verdict: theta earned it, gamma and vega spent it

Daily-hedged book, second-order Taylor attribution around each day's
real starting Greeks (₹):

| Interval | Δ spot | Theta | Gamma | Vega | Delta net | Costs | Residual | Total |
|---|---|---|---|---|---|---|---|---|
| 21 → 22 Oct | −124 | +5,966 | −2,993 | −2,259 | 0 | 218 | −1,291 | −796 |
| 22 → 23 Oct | −88 | +6,044 | −1,577 | −16,817 | 0 | 247 | −6,916 | −19,512 |
| 23 → 26 Oct | +153 | +19,182 | −4,549 | −16,320 | 0 | 154 | +11,648 | +9,806 |
| 26 → 27 Oct | −3 | +8,029 | −2 | +16,283 | 0 | 251 | +552 | +24,611 |
| 27 → 28 Oct | −51 | +7,963 | −598 | +1,708 | 0 | 14 | −4,078 | +4,981 |
| 28 → 29 Oct | +238 | +8,196 | −13,953 | +17,948 | 0 | 123 | −5,021 | +7,046 |
| 29 → 30 Oct | +116 | +8,126 | −3,569 | −3,445 | 0 | 597 | +13,275 | +13,791 |
| 30 Oct → 2 Nov | +388 | +23,946 | −34,952 | −33,529 | 0 | 300 | +51,336 | +6,502 |
| 2 → 3 Nov | +370 | +5,850 | −10,908 | −18,648 | 0 | 1,945 | +11,406 | −14,245 |
| **Total** | **+1,000** | **+93,302** | **−73,102** | **−55,080** | **0** | **3,849** | **+70,912** | **+32,183** |

The verdict, in desk language:

* **Theta is the salary**: +₹93,302 collected for holding short
  premium through 13 calendar days (the two weekend intervals pay
  roughly triple theta: +₹19,182 and +₹23,946).
* **Gamma is the rent on the rally**: −₹73,102. The two big up days
  cost −₹34,952 and −₹10,908 of pure ½Γ(ΔS)² — realised movement
  overwhelmed the decay those days bought.
* **Vega was a second, quieter enemy**: −₹55,080 net. The smile kept
  repricing *up* into the rally (30 Oct → 2 Nov: −₹33,529) — the book
  was short a vol that refused to fall. Note the worst hedged day of
  the window (22 → 23 Oct, −₹19,512) had a spot move of only −88 pts:
  it was a vega day (−₹16,817), not a delta day. Delta hedging does
  nothing for it.
* **Delta net is exactly ₹0** — by construction, and that is the
  check that the hedge accounting is right: the +₹175,945 hedge P&L
  cancels the book's −₹175,945 gross delta P&L to the rupee.
* **The residual (+₹70,912, 31.5% of the gross Greek P&L) is
  concentrated, not diffuse.** One interval — 30 Oct → 2 Nov, the
  weekend into the 3 Nov expiry — owns ₹51,336, 49% of the window's
  total absolute residual: settlement prints repriced away from any
  smooth smile that weekend (the ATM call print's own IV jumped
  12.1% → 19.1%). On every other interval the residual stays within
  ₹13,275. Attribution on exchange settlement data is exact except
  where the prints themselves leave the model — and the study says
  where.

## Case C — hedging frequency: the band slept, then woke up in time

| | Daily hedge | Band hedge (±100 units) |
|---|---|---|
| Trades | 10 | 3 |
| Turnover | 827 units | 589 units (**−28.7%**) |
| Slippage | ₹3,849 | ₹2,774 (**−₹1,075**) |
| Daily P&L σ | ₹13,592 | ₹16,332 (**+20.2%**) |
| Total P&L | +₹32,183 | +₹23,998 (**−₹8,185**) |

The band's trade log is the story: book delta stayed inside ±100
units for the first six closes, so the band held *no hedge at all*
while the book drifted — its daily P&L is tick-for-tick the unhedged
book's through 29 Oct. Delta breached the band only when the rally
accelerated (closes of 30 Oct and 2 Nov), putting the hedge on just
before the two largest up days. That timing was luck, not design —
the same band in a market that gaps first and grinds later leaves the
book naked for the gap. What the band genuinely bought: 29% less
turnover, ₹1,075 less slippage, and a simpler book to run. What it
cost here: ₹8,185 of P&L and 20% more daily volatility. On this
window, daily hedging was worth its extra seven trades.
