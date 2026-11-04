"""Extract the committed window sample from the raw NSE bhavcopy archive.

Reads the dated fo_YYYYMMDD.zip files in the source directory and
pulls the chain slices for ONE expiry (default 2026-11-09) across the
consecutive trading days of the study window (default 21 Oct - 3 Nov
2026), keeping strikes within +/-7% of each day's spot. The output is
data/book_window.csv -- small enough to commit, complete enough to
replay the whole study offline.

Usage:
    python tools/build_window.py [BHAVCOPY_DIR] [OUTPUT_CSV]
"""

from __future__ import annotations

import os
import sys
from datetime import date

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from hedge.data import load_bhavcopy, extract_slice  # noqa: E402

EXPIRY = date(2026, 11, 9)
DAYS = ["20261021", "20261022", "20261023", "20261026", "20261027",
        "20261028", "20261029", "20261030", "20261102", "20261103"]
DEFAULT_SRC = os.path.expanduser(
    "~/workspace/trading/india-options-paper/data/bhavcopy")
DEFAULT_OUT = os.path.join(os.path.dirname(__file__), "..", "data",
                           "book_window.csv")


def main(src_dir=DEFAULT_SRC, out_path=DEFAULT_OUT):
    frames = []
    for d in DAYS:
        path = os.path.join(src_dir, f"fo_{d}.zip")
        df = load_bhavcopy(path)
        frames.append(extract_slice(df, EXPIRY))
        print(f"{d}: {len(frames[-1])} rows")
    window = pd.concat(frames, ignore_index=True)
    window = window.sort_values(["trade_date", "strike", "kind"])
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    window.to_csv(out_path, index=False)
    print(f"wrote {out_path}: {len(window)} rows, "
          f"{window['trade_date'].nunique()} days, expiry {EXPIRY}")
    return window


if __name__ == "__main__":
    main(*sys.argv[1:])
