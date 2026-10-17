#!/usr/bin/env python3
"""Upload the synthetic CSVs (or pipeline results) to the Fabric Lakehouse Files area via OneLake.
Prerequisite: run in Azure Cloud Shell (already signed in) as the account that is a member of the Fabric workspace.
  python scripts/01_upload_to_onelake.py            # uploads data/*.csv  -> Files/stocktruth/data/
  python scripts/01_upload_to_onelake.py --results  # uploads outputs/*.csv -> Files/stocktruth/results/
If this fails, use the manual fallback in the runbook (Lakehouse > Files > Upload).
WHEN : RUNBOOK Step 8, after the Fabric workspace and lakehouse exist and their IDs are in ~/stocktruth.env.
       Run once without flags (data), and again with --results after each pipeline run you want in Power BI.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stocktruth.config import Settings  # noqa: E402
from stocktruth.data_access import GUID, get_credential  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", action="store_true")
    a = ap.parse_args()
    s = Settings()
    if not (s.fabric_workspace and s.fabric_lakehouse):
        sys.exit("Set FABRIC_WORKSPACE_ID and FABRIC_LAKEHOUSE_ID in your env file first (see runbook).")
    from azure.storage.filedatalake import DataLakeServiceClient
    svc = DataLakeServiceClient("https://onelake.dfs.fabric.microsoft.com", credential=get_credential())
    fs = svc.get_file_system_client(s.fabric_workspace)
    lh = s.fabric_lakehouse
    root = f"{lh}/Files/stocktruth" if GUID.match(lh) else f"{lh}.Lakehouse/Files/stocktruth"
    src, dst = (s.out_dir, f"{root}/results") if a.results else (s.data_dir, f"{root}/data")
    files = sorted(src.glob("*.csv"))
    if not files:
        sys.exit(f"No CSV files in {src}")
    for f in files:
        fc = fs.get_file_client(f"{dst}/{f.name}")
        fc.upload_data(f.read_bytes(), overwrite=True)
        print(f"uploaded {f.name} -> {dst}/{f.name}")
    print("Done. Next: run the notebook in fabric/notebook_load_tables.py to create Delta tables.")
