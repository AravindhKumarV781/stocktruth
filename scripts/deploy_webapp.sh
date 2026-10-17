#!/usr/bin/env bash
# Deploy the approval console as an Azure App Service web app. Run in Azure Cloud Shell (bash).
# WHEN : RUNBOOK Step 9 (first deploy). Re-run after code changes, after editing ~/stocktruth.env, or to add the Teams webhook.
#
#   bash scripts/deploy_webapp.sh <suffix> [region]
#
# Reads settings from ~/stocktruth.env and pushes them to the web app as app settings
# (the secrets never go into the deployed files). Safe to re-run to redeploy code or refresh settings.

SFX="${1:?Give the same suffix you used in azure_setup.sh}"
LOC="${2:-centralindia}"
RG="rg-stocktruth"
APP="stocktruth-$SFX"
ENVF="${ENV_FILE:-$HOME/stocktruth.env}"
cd "$(dirname "$0")/.." || exit 1
[ -f "$ENVF" ] || { echo "No env file at $ENVF. Run scripts/azure_setup.sh first."; exit 1; }

echo "== Deploying code (first deploy takes 5 to 8 minutes)"
az webapp up --name "$APP" --resource-group "$RG" --location "$LOC" --runtime "PYTHON:3.12" --sku B1 \
  || { echo "Deploy failed. Read the message above; common cause: app name taken (change the suffix)."; exit 1; }

echo "== Startup command and websockets (Streamlit needs both)"
az webapp config set -g "$RG" -n "$APP" --web-sockets-enabled true \
  --startup-file "python -m streamlit run app/streamlit_app.py --server.port 8000 --server.address 0.0.0.0 --server.headless true --server.enableCORS false --server.enableXsrfProtection false" -o none

echo "== App settings from $ENVF"
python3 - "$ENVF" "$APP" "$RG" <<'PY'
import subprocess, sys
sys.path.insert(0, "src")
from stocktruth.config import parse_env_file
envf, app, rg = sys.argv[1:4]
s = {k: v for k, v in parse_env_file(envf).items() if v != ""}
s.update(APP_URL=f"https://{app}.azurewebsites.net", STATE_DIR="/home/stocktruth_state",
         WEBSITES_PORT="8000", SCM_DO_BUILD_DURING_DEPLOYMENT="true")
pairs = [f"{k}={v}" for k, v in s.items()]
r = subprocess.run(["az", "webapp", "config", "appsettings", "set", "-g", rg, "-n", app, "-o", "none",
                    "--settings", *pairs])
print("settings saved" if r.returncode == 0 else "SETTINGS FAILED: re-run this script")
PY

echo
echo "Open: https://$APP.azurewebsites.net   (wait 1 to 2 minutes after the first deploy)"
echo "Logs: az webapp log tail -g $RG -n $APP"
