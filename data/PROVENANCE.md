# Data provenance — book_window.csv

**What this file is.** The NIFTY option chain slices for one expiry
(2026-11-09) on 10 consecutive real trading days, 21 Oct – 3 Nov 2026,
strikes within ±7% of each day's spot: 1,284 rows. Columns:
`trade_date, expiry, strike, kind, premium, spot, oi, volume,
lot_size`, where `premium` is the bhavcopy close/settlement print
(`ClsPric`), `spot` the underlying print (`UndrlygPric`), `oi` open
interest (shares), `volume` contracts traded, `lot_size`
`NewBrdLotQty` (= 65 on every day of the window).

**Source.** NSE F&O daily bhavcopy archives
(`BhavCopy_NSE_FO_0_0_0_YYYYMMDD_F_0000.csv`, distributed as dated
`fo_YYYYMMDD.zip` files), the same 220-day archive (Nov 2025 – Nov
2026) used by the sibling greeks-lab and vol-surface-atlas repos.
Exchange-published end-of-day data; no scraping of live quotes, no
simulated prices anywhere in the study.

**Regeneration.** From the raw archive directory:

```
python tools/build_window.py [BHAVCOPY_DIR] [OUTPUT_CSV]
```

(defaults: the study window above; the extractor is
`src/hedge/data.py: extract_slice`). The committed CSV is the only
input `main.py` needs — the whole study replays offline from it.
