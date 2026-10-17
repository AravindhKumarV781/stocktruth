#!/usr/bin/env python3
"""PHASE 2 | Turn CCTV video clips into product events with the vision model deployed in Foundry.
WHEN : after Phase 1 works (RUNBOOK Phase 2, step P2-3), and again whenever you add clips.
WHERE: Azure Cloud Shell, from the project folder. Needs LLM_MODE=azure (set by azure_setup.sh) and:
         pip install --user -r requirements-cctv.txt
INPUT: cctv/manifest.csv (columns: clip_id,location,camera,start_ts,file) and the clips in cctv/videos/
USAGE: python3 scripts/11_cctv_analyze.py [--manifest cctv/manifest.csv] [--every-sec 2]
OUTPUT: cctv/cctv_events.csv  (replaces the sample events everywhere; redeploy the web app to ship it)
Frames stay in memory and are never saved. Only product events are written."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from stocktruth.cctv import EVENT_COLS, analyze_clip, extract_frames  # noqa: E402
from stocktruth.config import Settings  # noqa: E402
from stocktruth.llm import LLM  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default=str(ROOT / "cctv" / "manifest.csv"))
    ap.add_argument("--every-sec", type=float, default=2.0)
    a = ap.parse_args()
    s = Settings()
    if s.llm_mode != "azure":
        sys.exit("LLM_MODE is not 'azure'. Finish RUNBOOK Step 5 first (the vision model must be deployed).")
    mf = Path(a.manifest)
    if not mf.exists():
        sys.exit(f"Missing {mf}. Copy cctv/manifest.example.csv to cctv/manifest.csv and edit it.")
    products = pd.read_csv(s.data_dir / "products.csv")
    llm = LLM(s)
    events, dropped = [], 0
    for r in pd.read_csv(mf).itertuples():
        vid = ROOT / "cctv" / "videos" / r.file
        if not vid.exists():
            print(f"[SKIP] {r.clip_id}: {vid.name} not found")
            continue
        frames = extract_frames(vid, every_sec=a.every_sec)
        evs, d = analyze_clip(llm, frames, products)
        dropped += d
        start = pd.Timestamp(r.start_ts)
        for e in evs:
            events.append(dict(clip_id=r.clip_id, location=r.location, camera=r.camera,
                               ts=str(start + pd.Timedelta(seconds=e["t_sec"])), sku=e["sku"], action=e["action"],
                               qty=e["qty"], shelf_expected=e["shelf_expected"], shelf_seen=e["shelf_seen"],
                               confidence=e["confidence"]))
        print(f"[OK] {r.clip_id}: {len(frames)} frames -> {len(evs)} events")
    df = pd.DataFrame(events, columns=[c for c in EVENT_COLS if c != "event_id"])
    df.insert(0, "event_id", [f"EV{n + 1:03d}" for n in range(len(df))])
    df.to_csv(ROOT / "cctv" / "cctv_events.csv", index=False)
    print(f"wrote cctv/cctv_events.csv: {len(df)} events ({dropped} malformed model outputs dropped)")
    print(f"model calls={llm.calls} tokens in/out={llm.tokens_in}/{llm.tokens_out}")
    print("Next: python3 scripts/12_cctv_reconcile.py")
