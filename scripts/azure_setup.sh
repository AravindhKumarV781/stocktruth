#!/usr/bin/env bash
# Create the Azure resources and write all keys into ~/stocktruth.env. Run in Azure Cloud Shell (bash).
# WHEN : RUNBOOK Step 4 (first run), and Step 5 again with the Foundry resource name to add the model key.
#
#   bash scripts/azure_setup.sh <suffix> [region] [foundry-resource-name] [foundry-resource-group]
#
#   <suffix>  3-8 lowercase letters/digits, makes your resource names globally unique (example: abc12)
#   region    default centralindia
#   The 3rd and 4th arguments are optional. Run once without them, create the model in the Foundry
#   portal, then run again WITH the Foundry resource name so its key and endpoint are added.
# Safe to re-run: existing resources are kept and keys are re-read.

SFX="${1:?Give a short unique suffix, e.g. abc12}"
LOC="${2:-centralindia}"
AOAI="${3:-}"
AOAI_RG="${4:-rg-stocktruth}"
RG="rg-stocktruth"
ENVF="${ENV_FILE:-$HOME/stocktruth.env}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"

[ -f "$ENVF" ] || cp "$HERE/.env.example" "$ENVF"
echo "Using env file: $ENVF"

setenv() {   # setenv KEY VALUE  (replaces the line if present, else appends)
  local k="$1" v="$2"
  grep -v "^${k}=" "$ENVF" > "$ENVF.tmp" 2>/dev/null; mv "$ENVF.tmp" "$ENVF"
  printf '%s=%s\n' "$k" "$v" >> "$ENVF"
}

echo "== Resource group"
az group create -n "$RG" -l "$LOC" -o none && echo "ok: $RG"

echo "== Azure AI Search (free tier)"
az search service create -n "srch-st-$SFX" -g "$RG" --sku free -l "$LOC" -o none \
  || echo "WARN: search create failed (maybe a free one already exists or the region has none). Create it in the portal."
SKEY=$(az search admin-key show --service-name "srch-st-$SFX" -g "$RG" --query primaryKey -o tsv 2>/dev/null)
if [ -n "$SKEY" ]; then
  setenv SEARCH_ENDPOINT "https://srch-st-$SFX.search.windows.net"; setenv SEARCH_KEY "$SKEY"; echo "ok: search keys saved"
fi

echo "== Cosmos DB (free tier, takes a few minutes)"
az cosmosdb create -n "cosmos-st-$SFX" -g "$RG" --enable-free-tier true \
  --locations regionName="$LOC" failoverPriority=0 isZoneRedundant=False -o none \
  || echo "WARN: cosmos create failed (only one free-tier account per subscription). Create it in the portal."
CEP=$(az cosmosdb show -n "cosmos-st-$SFX" -g "$RG" --query documentEndpoint -o tsv 2>/dev/null)
CKEY=$(az cosmosdb keys list -n "cosmos-st-$SFX" -g "$RG" --query primaryMasterKey -o tsv 2>/dev/null)
if [ -n "$CEP" ] && [ -n "$CKEY" ]; then
  setenv COSMOS_ENDPOINT "$CEP"; setenv COSMOS_KEY "$CKEY"; echo "ok: cosmos keys saved"
fi

echo "== Content Safety (Prompt Shields)"
az cognitiveservices account create -n "cs-st-$SFX" -g "$RG" -l "$LOC" --kind ContentSafety --sku F0 \
  --custom-domain "cs-st-$SFX" --yes -o none \
  || echo "WARN: content safety create failed (F0 may be used up). Create it in the portal with S0."
CSEP=$(az cognitiveservices account show -n "cs-st-$SFX" -g "$RG" --query properties.endpoint -o tsv 2>/dev/null)
CSKEY=$(az cognitiveservices account keys list -n "cs-st-$SFX" -g "$RG" --query key1 -o tsv 2>/dev/null)
if [ -n "$CSEP" ] && [ -n "$CSKEY" ]; then
  setenv CONTENT_SAFETY_ENDPOINT "$CSEP"; setenv CONTENT_SAFETY_KEY "$CSKEY"; echo "ok: content safety keys saved"
fi

if [ -n "$AOAI" ]; then
  echo "== Foundry / Azure OpenAI resource: $AOAI"
  AKEY=$(az cognitiveservices account keys list -n "$AOAI" -g "$AOAI_RG" --query key1 -o tsv 2>/dev/null)
  if [ -n "$AKEY" ]; then
    setenv AZURE_OPENAI_ENDPOINT "https://$AOAI.openai.azure.com/"; setenv AZURE_OPENAI_API_KEY "$AKEY"
    setenv LLM_MODE azure; echo "ok: model key saved, LLM_MODE=azure"
  else
    echo "WARN: could not read keys for '$AOAI' in group '$AOAI_RG'. Check the name and resource group."
  fi
fi

echo
echo "Done. Saved to $ENVF (keys are NOT shown here). Names used:"
echo "  search=srch-st-$SFX  cosmos=cosmos-st-$SFX  content-safety=cs-st-$SFX"
echo "Next: python3 scripts/00_check_env.py --create-cosmos"
