"""Bhavcopy loading and window handling.

Two entry points:

* ``load_bhavcopy`` reads a raw NSE F&O bhavcopy (a ``.csv`` or one of
  the dated ``fo_YYYYMMDD.zip`` archives) -- used by
  ``tools/build_window.py`` to extract the committed sample.
* ``load_window`` reads the committed ``data/book_window.csv``: the
  chain slices for ONE expiry across consecutive trading days. Every
  other module works off this frame, so the whole study replays
  offline from the sample alone.

Window CSV columns: trade_date, expiry, strike, kind, premium, spot,
oi, volume, lot_size. ``premium`` is the exchange close / settlement
print (ClsPric) and ``spot`` the underlying print (UndrlygPric) of the
same file -- both are that day's official marks, not traded ticks.
"""

from __future__ import annotations

import io
import zipfile
from datetime import date

import pandas as pd

BHAV_COLUMNS = ["TradDt", "FinInstrmTp", "TckrSymb", "XpryDt", "StrkPric",
                "OptnTp", "ClsPric", "UndrlygPric", "OpnIntrst",
                "TtlTradgVol", "NewBrdLotQty"]

WINDOW_COLUMNS = ["trade_date", "expiry", "strike", "kind", "premium",
                  "spot", "oi", "volume", "lot_size"]


def load_bhavcopy(source):
    """Load a raw bhavcopy from a .csv path or a dated .zip archive."""
    if isinstance(source, (str, bytes)) and str(source).endswith(".zip"):
        with zipfile.ZipFile(source) as z:
            name = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
            raw = z.read(name)
        return pd.read_csv(io.BytesIO(raw),
                           usecols=lambda c: c in BHAV_COLUMNS)
    return pd.read_csv(source, usecols=lambda c: c in BHAV_COLUMNS)


def extract_slice(df, expiry: date, symbol="NIFTY", band=0.07):
    """One day's chain slice for a fixed expiry.

    Keeps strikes within +/- ``band`` (fraction of spot) so the sample
    carries the full smile around the book without carrying the whole
    300-strike weekly chain.
    """
    sub = df[(df["TckrSymb"] == symbol) & (df["FinInstrmTp"] == "IDO")].copy()
    if sub.empty:
        raise ValueError(f"no index options for {symbol!r} in frame")
    sub["TradDt"] = pd.to_datetime(sub["TradDt"]).dt.date
    sub["XpryDt"] = pd.to_datetime(sub["XpryDt"]).dt.date
    trade_date = sub["TradDt"].iloc[0]
    chain = sub[sub["XpryDt"] == expiry].copy()
    if chain.empty:
        raise ValueError(f"no rows for expiry {expiry} on {trade_date}")
    spot = float(chain["UndrlygPric"].iloc[0])
    chain = chain[(chain["StrkPric"] >= spot * (1 - band))
                  & (chain["StrkPric"] <= spot * (1 + band))]
    out = pd.DataFrame({
        "trade_date": trade_date,
        "expiry": expiry,
        "strike": chain["StrkPric"].astype(float),
        "kind": chain["OptnTp"],
        "premium": chain["ClsPric"].astype(float),
        "spot": spot,
        "oi": chain["OpnIntrst"].astype(float),
        "volume": chain["TtlTradgVol"].astype(float),
        "lot_size": chain["NewBrdLotQty"].astype(float),
    }).sort_values(["strike", "kind"]).reset_index(drop=True)
    return out


def load_window(path):
    """Load the committed window CSV into a tidy, sorted DataFrame."""
    df = pd.read_csv(path, parse_dates=["trade_date", "expiry"])
    df["trade_date"] = df["trade_date"].dt.date
    df["expiry"] = df["expiry"].dt.date
    missing = [c for c in WINDOW_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"window file missing columns {missing}")
    return df.sort_values(["trade_date", "strike", "kind"]).reset_index(drop=True)


def window_days(df):
    """Sorted list of trading days present in the window."""
    return sorted(df["trade_date"].unique())


def day_chain(df, day):
    """The slice for one trading day (one expiry, many strikes)."""
    out = df[df["trade_date"] == day]
    if out.empty:
        raise ValueError(f"no chain slice for {day}")
    return out.reset_index(drop=True)
