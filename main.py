"""Hedge Lab CLI.

Replays the study end-to-end from data/book_window.csv:
  1. builds the short-vol book at day-0 real prints,
  2. marks it on every real day and computes Greeks from each day's
     real smile,
  3. runs the three hedging strategies,
  4. attributes the daily-hedged book's P&L Greek by Greek,
  5. writes docs/results.json and docs/dashboard.html.

    python main.py
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from hedge import attribution, book, data, engine  # noqa: E402
from hedge.report import render_dashboard  # noqa: E402

HERE = os.path.dirname(__file__)
WINDOW_CSV = os.path.join(HERE, "data", "book_window.csv")
RESULTS_JSON = os.path.join(HERE, "docs", "results.json")
DASHBOARD_HTML = os.path.join(HERE, "docs", "dashboard.html")


def rs(x):
    return f"₹{x:,.0f}"


def run():
    df = data.load_window(WINDOW_CSV)
    days = data.window_days(df)
    positions = book.build_book(data.day_chain(df, days[0]))
    states = book.build_states(positions, df, days)
    mark_counts = Counter(m.mark_type for st in states
                          for m in st.marks.values())

    sims = {s.mode: engine.simulate(states, s) for s in engine.STRATEGIES}
    rows_d, tot_d = attribution.attribute_strategy(
        states, sims["daily"], positions)
    rows_u, tot_u = attribution.attribute_strategy(
        states, sims["none"], positions)

    s0 = states[0]
    book_txt = "; ".join(
        f"{'+' if p.lots > 0 else '−'}{abs(p.lots):.0f} lots "
        f"{p.strike:,.0f} {p.kind} @ {s0.marks[p.key].premium:,.2f}"
        for p in positions)
    print("=" * 100)
    print("HEDGE LAB — delta-hedging a short-vol NIFTY book on real chains")
    print(f"Window: {days[0]} → {days[-1]} ({len(days)} real trading days), "
          f"expiry {df['expiry'].iloc[0]}, lot {s0.lot_size:.0f}")
    print(f"Spot: {states[0].spot:,.2f} → {states[-1].spot:,.2f} "
          f"({(states[-1].spot / states[0].spot - 1) * 100:+.2f}%)")
    print(f"Book (day-0 marks): {book_txt}")
    print(f"Net credit collected at open: {rs(s0.net_credit_rs)}")
    print(f"Marks used: {dict(mark_counts)}")
    print(f"Day-0 book Greeks: delta {s0.delta_units:+,.0f} units, "
          f"gamma {s0.gamma_per_point:+.3f}/pt, "
          f"theta {rs(s0.theta_rs_day)}/day, "
          f"vega {rs(s0.vega_rs_point)}/vol pt")

    print("\n--- Strategy comparison (real marks, real spot) ---")
    print(f"{'Strategy':<26}{'Total P&L':>14}{'Option':>14}{'Hedge':>14}"
          f"{'Costs':>10}{'Turnover':>12}{'Trades':>8}{'Worst day':>14}")
    strat_out = []
    for s in engine.STRATEGIES:
        sim = sims[s.mode]
        worst, _, worst_to = sim.max_adverse_day
        print(f"{s.name:<26}{rs(sim.total_pnl):>14}{rs(sim.option_pnl):>14}"
              f"{rs(sim.hedge_pnl):>14}{rs(sim.total_costs):>10}"
              f"{sim.turnover_units:>10,.0f}u{len(sim.trades):>8}"
              f"{rs(worst):>14}")
        strat_out.append({
            "name": s.name, "mode": s.mode, "total_pnl": sim.total_pnl,
            "option_pnl": sim.option_pnl, "hedge_pnl": sim.hedge_pnl,
            "total_costs": sim.total_costs,
            "turnover_units": sim.turnover_units,
            "n_trades": len(sim.trades), "worst_day_pnl": worst,
            "worst_day_to": str(worst_to),
            "daily_std": sim.daily_pnl_std(),
            "cumulative": sim.cumulative(),
            "daily": [iv.total_pnl for iv in sim.intervals],
        })

    print("\n--- Attribution: daily-hedged book (₹) ---")
    print(f"{'Interval':<24}{'Δspot':>9}{'Theta':>12}{'Gamma':>12}"
          f"{'Vega':>12}{'DeltaNet':>12}{'Costs':>9}{'Residual':>12}"
          f"{'Total':>12}")
    row_dicts = []
    for r in rows_d:
        print(f"{str(r.day_from) + ' → ' + str(r.day_to):<24}"
              f"{r.spot_move:>+9,.0f}{rs(r.theta):>12}{rs(r.gamma):>12}"
              f"{rs(r.vega):>12}{rs(r.delta_net):>12}{rs(r.costs):>9}"
              f"{rs(r.residual):>12}{rs(r.total):>12}")
        row_dicts.append({k: getattr(r, k) for k in
                          ("day_from", "day_to", "spot_move", "days",
                           "delta_gross", "hedge_pnl", "delta_net", "gamma",
                           "theta", "vega", "costs", "residual", "total")})
        row_dicts[-1]["day_from"] = str(r.day_from)
        row_dicts[-1]["day_to"] = str(r.day_to)
    print(f"{'TOTAL':<24}{'':>9}{rs(tot_d['theta']):>12}"
          f"{rs(tot_d['gamma']):>12}{rs(tot_d['vega']):>12}"
          f"{rs(tot_d['delta_net']):>12}{rs(tot_d['costs']):>9}"
          f"{rs(tot_d['residual']):>12}{rs(tot_d['total']):>12}")
    gross = sum(abs(tot_d[k]) for k in
                ("theta", "gamma", "vega", "delta_net")) + tot_d["costs"]
    resid_pct = abs(tot_d["residual"]) / max(gross, 1.0) * 100.0

    worst_res = max(rows_d, key=lambda r: abs(r.residual))
    abs_resid = sum(abs(r.residual) for r in rows_d)
    resid_share = abs(worst_res.residual) / abs_resid * 100 if abs_resid \
        else 0.0
    other_resid = max(abs(r.residual) for r in rows_d
                      if r is not worst_res)
    daily, band, none = sims["daily"], sims["band"], sims["none"]
    turn_red = (1 - band.turnover_units / daily.turnover_units) * 100 \
        if daily.turnover_units else 0.0
    var_change = (band.daily_pnl_std() / daily.daily_pnl_std() - 1) * 100 \
        if daily.daily_pnl_std() else 0.0
    worst_d, wf, wt = daily.max_adverse_day
    cases = {
        "A": (f"Over the {len(days)}-day window spot rallied "
              f"{(states[-1].spot / states[0].spot - 1) * 100:+.2f}%. "
              f"The unhedged book made {rs(none.total_pnl)}; daily "
              f"delta-hedging turned that into {rs(daily.total_pnl)}; "
              f"the ±100-unit band hedge made {rs(band.total_pnl)}. "
              f"The daily hedge's worst day was {rs(worst_d)} "
              f"({wf} → {wt}); its hedge trades cost "
              f"{rs(daily.total_costs)} in slippage on "
              f"{daily.turnover_units:,.0f} units of turnover."),
        "B": (f"Theta earned {rs(tot_d['theta'])}; gamma cost "
              f"{rs(tot_d['gamma'])} as spot realised its moves; vega "
              f"contributed {rs(tot_d['vega'])}; net delta after the "
              f"hedge was {rs(tot_d['delta_net'])}. The unexplained "
              f"residual is {rs(tot_d['residual'])} "
              f"({resid_pct:.1f}% of the gross Greek P&L), and it is "
              f"concentrated, not diffuse: the single interval "
              f"{worst_res.day_from} → {worst_res.day_to} (the weekend "
              f"into the 3 Nov expiry, spot {worst_res.spot_move:+,.0f}) "
              f"owns {rs(worst_res.residual)}, {resid_share:.0f}% of "
              f"the window's total absolute residual, as settlement "
              f"prints repriced away from any smooth smile; on every "
              f"other interval the residual stays within "
              f"{rs(other_resid)}."),
        "C": (f"The band cut hedge turnover from "
              f"{daily.turnover_units:,.0f} to "
              f"{band.turnover_units:,.0f} units "
              f"({turn_red:.1f}% less) and slippage from "
              f"{rs(daily.total_costs)} to {rs(band.total_costs)}, "
              f"while daily P&L volatility moved "
              f"{var_change:+.1f}% (σ ₹{daily.daily_pnl_std():,.0f} → "
              f"₹{band.daily_pnl_std():,.0f}) and total P&L moved from "
              f"{rs(daily.total_pnl)} to {rs(band.total_pnl)}."),
    }
    res = {
        "days": [str(d) for d in days],
        "window_text": (f"{days[0]} → {days[-1]}, {len(days)} consecutive "
                        f"real trading days, NIFTY expiry "
                        f"{df['expiry'].iloc[0]}"),
        "book_text": book_txt,
        "net_credit_rs": s0.net_credit_rs,
        "mark_counts": {k: mark_counts.get(k, 0)
                        for k in ("REAL", "MODEL", "STALE")},
        "spot_start": states[0].spot, "spot_end": states[-1].spot,
        "strategies": strat_out,
        "attribution_daily": {"rows": row_dicts, "totals": tot_d},
        "attribution_unhedged_totals": tot_u,
        "cases": cases,
    }
    os.makedirs(os.path.dirname(RESULTS_JSON), exist_ok=True)
    with open(RESULTS_JSON, "w") as f:
        json.dump(res, f, indent=1, default=str)
    with open(DASHBOARD_HTML, "w") as f:
        f.write(render_dashboard(res))
    print(f"\nWrote {RESULTS_JSON} and {DASHBOARD_HTML}")
    print("\n--- Cases ---")
    for k, v in cases.items():
        print(f"Case {k}: {v}")
    return res


if __name__ == "__main__":
    run()
