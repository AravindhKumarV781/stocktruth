# Run order: what to run, when, and where

Everything runs in **Azure Cloud Shell (Bash)** from the project folder (`cd ~/stocktruth`) unless the Where column says otherwise.
The numbered steps match `RUNBOOK.md`. Run top to bottom; skip rows marked optional.

| # | Runbook step | Command | Where | What it needs | What it produces | Repeat? |
|---|---|---|---|---|---|---|
| 1 | 3 | `pip install --user -r ~/req-cli.txt` | Cloud Shell | nothing | Python packages | once |
| 2 | 3 | `python3 scripts/run_pipeline.py --reset` then `python3 scripts/evaluate.py` | Cloud Shell | nothing (offline sample mode) | `outputs/` cases, audit, eval | once, as a smoke test |
| 3 | 4 | `bash scripts/azure_setup.sh <sfx> centralindia` | Cloud Shell | signed-in portal account | Search, Cosmos, Content Safety; keys in `~/stocktruth.env` | once; re-run is safe |
| 4 | 5 | Foundry portal: deploy model; then `bash scripts/azure_setup.sh <sfx> centralindia <foundry-name> rg-stocktruth` | Foundry portal, then Cloud Shell | step 3 done | model key and `LLM_MODE=azure` in `~/stocktruth.env` | once |
| 5 | 6 | `python3 scripts/00_check_env.py --create-cosmos` | Cloud Shell | steps 3, 4 | PASS/FAIL per service | whenever a key changes |
| 6 | 6 | `python3 scripts/02_index_knowledge.py` | Cloud Shell | Search PASS | Search index of SOPs and contracts | after editing `knowledge/` |
| 7 | 7 | `python3 scripts/run_pipeline.py --reset` then `python3 scripts/evaluate.py` | Cloud Shell | steps 4 to 6 | real model results, accuracy, cost | before each demo |
| 8 | 8 (optional) | `python3 scripts/01_upload_to_onelake.py` | Cloud Shell | Fabric workspace + lakehouse IDs in env file | data in the Lakehouse | once |
| 9 | 8 (optional) | Fabric notebook cells 1 to 3 | Fabric portal | step 8 | Delta tables, `case_results` | after step 10 |
| 10 | 8 (optional) | `DATA_BACKEND=onelake python3 scripts/run_pipeline.py --reset` then `python3 scripts/01_upload_to_onelake.py --results` | Cloud Shell | step 8 | results in the Lakehouse | when you want fresh Power BI data |
| 11 | 9 | `bash scripts/deploy_webapp.sh <sfx> centralindia` | Cloud Shell | steps 3 to 5 | public web app | re-run after any code or env change |
| 12 | 9 | Open the web app, click **Run investigation now** | Web app | step 11 | live cases for the demo | before each demo |
| 13 | 9b | Entra sign-in, Application Insights, GitHub push | Portal / Cloud Shell | step 11 | enterprise-readiness controls | once |
| 14 | 10 (optional) | Teams Workflows webhook into `TEAMS_WEBHOOK_URL`, then redeploy (row 11) | Teams, Cloud Shell | step 11 | cards in Teams | once |
| 15 | P2-1 | `python3 scripts/12_cctv_reconcile.py` (uses sample CCTV events) | Cloud Shell | nothing | `outputs/cctv_findings.csv` | any time |
| 16 | P2-2/3 | (sample clips are already in the zip, or `python3 scripts/13_cctv_render_samples.py`) upload your own clips; `pip install --user -r requirements-cctv.txt`; `python3 scripts/11_cctv_analyze.py` | Cloud Shell | step 4 (model must read images), clips + `cctv/manifest.csv` | `cctv/cctv_events.csv` | per new clip |
| 17 | P2-4 | row 15, then row 7 (pipeline), then row 11 (redeploy) | Cloud Shell | step 16 | agents use CCTV as evidence; shipped to web app | after new events |
| 18 | 13 | `az group delete -n rg-stocktruth --yes` | Cloud Shell | nothing | removes everything | at the end |

## The order logic in one line
Setup (rows 1 to 6) before the model run (row 7); Fabric (rows 8 to 10) is optional and never blocks the web app; the web app (row 11) comes after the model works; CCTV (rows 15 to 17) comes last, and after any CCTV change run the pipeline again (row 7) and redeploy (row 11).

## Two things that cause most rework
1. Run the pipeline **in the web app** for the demo. Cloud Shell and the web app keep separate case state.
2. After changing `~/stocktruth.env` or any file in the project, re-run `deploy_webapp.sh`; the web app does not see Cloud Shell changes on its own.
