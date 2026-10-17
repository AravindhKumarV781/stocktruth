#!/usr/bin/env python3
"""PHASE 2 | OPTIONAL | Create synthetic CCTV events (no video needed) that line up with the Phase-1 data.
WHEN : only if you want to regenerate cctv/sample_events.csv (a ready-made copy is already in the zip).
WHERE: Azure Cloud Shell, from the project folder.
USAGE: python3 scripts/10_cctv_make_sample.py
OUTPUT: cctv/sample_events.csv"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from stocktruth.cctv import make_sample_events  # noqa: E402

if __name__ == "__main__":
    pos = pd.read_csv(ROOT / "data" / "pos_sales.csv")
    df = make_sample_events(pos)
    (ROOT / "cctv").mkdir(exist_ok=True)
    df.to_csv(ROOT / "cctv" / "sample_events.csv", index=False)
    print(f"wrote cctv/sample_events.csv with {len(df)} events")
