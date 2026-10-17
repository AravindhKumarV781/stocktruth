#!/usr/bin/env python3
"""PHASE 2 | Compare CCTV events with billing and print the findings.
WHEN : after 11_cctv_analyze.py (or straight away, using the sample events). Safe to repeat any time.
WHERE: Azure Cloud Shell, from the project folder (the web app does the same from its "CCTV" tab).
USAGE: python3 scripts/12_cctv_reconcile.py
OUTPUT: outputs/cctv_findings.csv. The next `run_pipeline.py` / "Run investigation now" also refreshes it
        automatically, and the agents then see the findings as extra evidence."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from stocktruth.cctv import reconcile_to_file  # noqa: E402
from stocktruth.config import Settings  # noqa: E402
from stocktruth.data_access import DataStore  # noqa: E402

if __name__ == "__main__":
    s = Settings()
    df, src = reconcile_to_file(s, DataStore.load(s))
    if df is None:
        sys.exit("No CCTV events found (cctv/sample_events.csv or cctv/cctv_events.csv).")
    print(f"events source: {src} | findings: {len(df)}")
    with pd.option_context("display.width", 200, "display.max_colwidth", 60):
        print(df.drop(columns=["ref", "clip_id"]).to_string(index=False))
    print(f"unbilled units: {int(df.loc[df['type'] == 'UNBILLED_PICK', 'qty'].sum())} | "
          f"value INR: {int(df.loc[df['type'] == 'UNBILLED_PICK', 'value_inr'].sum())}")
