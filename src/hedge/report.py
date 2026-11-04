"""Self-contained dark dashboard (docs/dashboard.html).

Renders from the results dict produced by main.py: cumulative P&L
curves per strategy (inline SVG), the daily-hedged attribution as a
table plus per-day component bars, and the three case cards. Zero
external references -- no fonts, no scripts, no images; everything is
inline CSS/SVG so the file works offline forever.
"""

from __future__ import annotations

import html


def _fmt_rs(x):
    sign = "-" if x < 0 else ""
    return f"{sign}₹{abs(x):,.0f}"


def _svg_lines(series, labels, colors, width=880, height=300, pad=46):
    """Multi-series line chart as inline SVG."""
    all_y = [y for s in series for y in s]
    lo, hi = min(all_y + [0.0]), max(all_y + [0.0])
    span = (hi - lo) or 1.0
    lo -= 0.06 * span
    hi += 0.06 * span
    n = max(len(s) for s in series)

    def X(i):
        return pad + (width - pad - 8) * (i / (n - 1 if n > 1 else 1))

    def Y(v):
        return height - pad - (height - 2 * pad) * (v - lo) / (hi - lo)

    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" '
             f'xmlns="http://www.w3.org/2000/svg">']
    y0 = Y(0.0)
    parts.append(f'<line x1="{pad}" y1="{y0:.1f}" x2="{width - 8}" '
                 f'y2="{y0:.1f}" stroke="#334155" stroke-width="1"/>')
    for frac, lab in ((0.0, lo), (0.5, (lo + hi) / 2), (1.0, hi)):
        v = lo + frac * (hi - lo)
        y = Y(v)
        parts.append(f'<line x1="{pad}" y1="{y:.1f}" x2="{width - 8}" '
                     f'y2="{y:.1f}" stroke="#1e293b" stroke-width="1"/>')
        parts.append(f'<text x="2" y="{y + 4:.1f}" fill="#94a3b8" '
                     f'font-size="10">{_fmt_rs(v)}</text>')
    for s, color in zip(series, colors):
        pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(s))
        parts.append(f'<polyline points="{pts}" fill="none" '
                     f'stroke="{color}" stroke-width="2.2"/>')
        parts.append(f'<circle cx="{X(len(s) - 1):.1f}" '
                     f'cy="{Y(s[-1]):.1f}" r="3.5" fill="{color}"/>')
    for i, lab in enumerate(labels):
        parts.append(f'<text x="{X(i):.1f}" y="{height - 8}" fill="#94a3b8" '
                     f'font-size="9.5" text-anchor="middle">'
                     f'{html.escape(str(lab)[5:])}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _attr_bars(rows):
    """One horizontal stacked bar per interval for the attribution."""
    comps = [("theta", "#38bdf8"), ("gamma", "#f87171"),
             ("vega", "#a78bfa"), ("delta_net", "#fbbf24"),
             ("residual", "#64748b")]
    peak = max((sum(abs(getattr(r, k)) for k, _ in comps) for r in rows),
               default=1.0) or 1.0
    out = []
    for r in rows:
        segs, left = [], 50.0
        # build a diverging stack around the centre
        pos, neg = 50.0, 50.0
        for key, color in comps:
            v = getattr(r, key)
            w = abs(v) / peak * 50.0
            if v >= 0:
                segs.append((pos, w, color, key, v))
                pos += w
            else:
                neg -= w
                segs.append((neg, w, color, key, v))
        rects = "".join(
            f'<rect x="{x:.2f}%" y="3" width="{max(w, 0.35):.2f}%" '
            f'height="12" fill="{c}"><title>{k}: {_fmt_rs(v)}</title></rect>'
            for x, w, c, k, v in segs)
        out.append(
            f'<div class="attrrow"><span class="attrlab">'
            f'{html.escape(str(r.day_to)[5:])}</span>'
            f'<svg class="attrbar" viewBox="0 0 100 18" '
            f'preserveAspectRatio="none">{rects}'
            f'<line x1="50" y1="0" x2="50" y2="18" stroke="#475569"/></svg>'
            f'<span class="attrtot">{_fmt_rs(r.total)}</span></div>')
    return "".join(out)


def render_dashboard(res):
    days = res["days"]
    strats = res["strategies"]
    rows = res["attribution_daily"]["rows"]
    tot = res["attribution_daily"]["totals"]
    colors = ["#f87171", "#38bdf8", "#4ade80"]
    series = [s["cumulative"] for s in strats]
    chart = _svg_lines(series, days, colors)
    legend = "".join(
        f'<span class="lg"><i style="background:{c}"></i>'
        f'{html.escape(s["name"])}: <b>{_fmt_rs(s["total_pnl"])}</b></span>'
        for s, c in zip(strats, colors))
    strat_cards = "".join(
        f'<div class="card"><h3>{html.escape(s["name"])}</h3>'
        f'<div class="big">{_fmt_rs(s["total_pnl"])}</div>'
        f'<p>Option P&amp;L {_fmt_rs(s["option_pnl"])} · hedge P&amp;L '
        f'{_fmt_rs(s["hedge_pnl"])}<br>Costs {_fmt_rs(s["total_costs"])} · '
        f'turnover {s["turnover_units"]:,.0f} units · {s["n_trades"]} trades'
        f'<br>Worst day {_fmt_rs(s["worst_day_pnl"])} '
        f'({html.escape(str(s["worst_day_to"]))}) · daily σ '
        f'₹{s["daily_std"]:,.0f}</p></div>'
        for s in strats)
    attr_rows_html = "".join(
        f'<tr><td>{html.escape(str(r["day_from"]))} → '
        f'{html.escape(str(r["day_to"]))}</td>'
        f'<td>{r["spot_move"]:+,.2f}</td><td>{_fmt_rs(r["theta"])}</td>'
        f'<td>{_fmt_rs(r["gamma"])}</td><td>{_fmt_rs(r["vega"])}</td>'
        f'<td>{_fmt_rs(r["delta_net"])}</td><td>{_fmt_rs(r["costs"])}</td>'
        f'<td>{_fmt_rs(r["residual"])}</td><td><b>{_fmt_rs(r["total"])}'
        f'</b></td></tr>' for r in rows)
    a, b, c = res["cases"]["A"], res["cases"]["B"], res["cases"]["C"]
    cases_html = f"""
    <div class="card wide"><h3>Case A — the headline</h3><p>{html.escape(a)}</p></div>
    <div class="card wide"><h3>Case B — attribution verdict</h3><p>{html.escape(b)}</p></div>
    <div class="card wide"><h3>Case C — hedging frequency trade-off</h3><p>{html.escape(c)}</p></div>"""
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>Hedge Lab — NIFTY delta-hedging &amp; Greeks attribution</title>
<style>
body{{background:#0b1220;color:#e2e8f0;font-family:Georgia,serif;margin:0;
padding:28px 5vw}}
h1{{font-size:26px;margin:0 0 4px}} h2{{font-size:19px;margin:26px 0 8px;
color:#7dd3fc}} h3{{margin:0 0 6px;font-size:16px;color:#7dd3fc}}
.sub{{color:#94a3b8;margin:0 0 14px}}
.grid{{display:flex;flex-wrap:wrap;gap:14px}}
.card{{background:#111c30;border:1px solid #1e293b;border-radius:10px;
padding:14px 16px;flex:1 1 240px}}
.card.wide{{flex:1 1 100%}}
.big{{font-size:24px;font-weight:bold;margin:2px 0 6px}}
p{{color:#cbd5e1;line-height:1.45;margin:4px 0}}
table{{border-collapse:collapse;width:100%;font-size:13.5px}}
td,th{{border-bottom:1px solid #1e293b;padding:5px 7px;text-align:right}}
td:first-child,th:first-child{{text-align:left}}
.lg{{margin-right:18px;color:#cbd5e1}} .lg i{{display:inline-block;width:11px;
height:11px;border-radius:2px;margin-right:6px}}
.attrrow{{display:flex;align-items:center;gap:10px;margin:3px 0}}
.attrlab{{width:44px;color:#94a3b8;font-size:12px}}
.attrbar{{flex:1;height:18px;background:#0f172a;border-radius:3px}}
.attrtot{{width:86px;text-align:right;font-size:12.5px}}
.foot{{color:#64748b;font-size:12.5px;margin-top:22px;line-height:1.5}}
</style></head><body>
<h1>Hedge Lab — delta-hedging a real NIFTY short-vol book</h1>
<p class="sub">{html.escape(res["window_text"])} · book opened at real
settlement prints: {html.escape(res["book_text"])} · net credit collected
{_fmt_rs(res["net_credit_rs"])} · marks: {res["mark_counts"]["REAL"]} real /
{res["mark_counts"]["MODEL"]} model / {res["mark_counts"]["STALE"]} stale</p>
<h2>Cumulative P&amp;L by hedging strategy</h2>
<div>{legend}</div>
{chart}
<div class="grid">{strat_cards}</div>
<h2>Attribution — daily-hedged book, P&amp;L by Greek (₹)</h2>
<p><span style="color:#38bdf8">■</span> theta&nbsp; <span style="color:#f87171">■</span> gamma&nbsp;
<span style="color:#a78bfa">■</span> vega&nbsp; <span style="color:#fbbf24">■</span> delta net of hedge&nbsp;
<span style="color:#64748b">■</span> residual</p>
<div>{_attr_bars_from_dicts(rows)}</div>
<table><tr><th>Interval</th><th>Δ spot</th><th>Theta</th><th>Gamma</th>
<th>Vega</th><th>Delta net</th><th>Costs</th><th>Residual</th><th>Total</th></tr>
{attr_rows_html}
<tr><td><b>Total</b></td><td></td><td><b>{_fmt_rs(tot["theta"])}</b></td>
<td><b>{_fmt_rs(tot["gamma"])}</b></td><td><b>{_fmt_rs(tot["vega"])}</b></td>
<td><b>{_fmt_rs(tot["delta_net"])}</b></td><td><b>{_fmt_rs(tot["costs"])}</b></td>
<td><b>{_fmt_rs(tot["residual"])}</b></td><td><b>{_fmt_rs(tot["total"])}</b></td></tr>
</table>
<h2>Real cases</h2>
<div class="grid">{cases_html}</div>
<p class="foot">Method: marks are the exchange settlement prints of the
9 Nov 2026 NIFTY expiry on each real day; Greeks come from each day's own
real smile; the hedge is NIFTY futures at the real index print with 2 bps
slippage per trade. Attribution is a second-order Taylor expansion around
each day's starting Greeks; the residual column is what it cannot explain
and is reported, not hidden. Settlement prints are not tradable ticks --
see the README limitations. Research only, not investment advice.</p>
</body></html>"""


def _attr_bars_from_dicts(rows):
    class R:
        pass
    objs = []
    for r in rows:
        o = R()
        for k in ("theta", "gamma", "vega", "delta_net", "residual",
                  "total", "day_to"):
            setattr(o, k, r[k])
        objs.append(o)
    return _attr_bars(objs)
