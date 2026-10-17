#!/usr/bin/env python3
"""Compare pipeline output with the golden answer key. Writes outputs/eval.json for the dashboard.
WHEN : right after run_pipeline.py (RUNBOOK Steps 3 and 7). The web app has the same check as a button.
WHERE: Azure Cloud Shell, from the project folder.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stocktruth.config import Settings  # noqa: E402
from stocktruth.evaluation import run_eval  # noqa: E402

if __name__ == "__main__":
    df, result = run_eval(Settings())
    print(df.drop(columns=[c for c in ["expected_route", "expected_action"] if c in df]).to_string(index=False))
    print({k: v for k, v in result.items() if k != "rows"})
