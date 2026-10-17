#!/usr/bin/env python3
"""Run the full StockTruth pipeline: python scripts/run_pipeline.py [--reset]
WHEN : RUNBOOK Step 3 (offline proof), Step 7 (with the real model), Step 8 (with DATA_BACKEND=onelake), and before any
       demo. The web app runs the same code from its "Run investigation now" button.
WHERE: Azure Cloud Shell, from the project folder.
"""
import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stocktruth.config import Settings  # noqa: E402
from stocktruth.orchestrator import run_pipeline  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="clear outputs/ (cases, audit, actions) first")
    a = ap.parse_args()
    s = Settings()
    if a.reset:
        for p in s.out_dir.iterdir():
            shutil.rmtree(p) if p.is_dir() else p.unlink()
        print("outputs/ cleared")
    res = run_pipeline(s)
    from collections import Counter
    print("\nSummary:", dict(Counter(r["status"] for r in res)))
    print("Total LLM cost (USD): ", round(sum(r["cost_usd"] for r in res), 4))
