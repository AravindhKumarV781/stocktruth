# StockTruth Phase-1 runbook (everything in the Azure portal, nothing on your laptop)

**How it works:** Azure Cloud Shell (a terminal inside the portal) is your workstation. The approval console runs as an Azure web app. Fabric, Foundry and the other services are set up in the portal.

Every step has the same shape: **Goal** (one line), **Do**, **Check**. Do not move on until the Check passes.

Total time: about 4 to 5 hours for Phase 1, plus 1.5 to 2 hours for Phase 2 (CCTV). **The one-table run order for every script is in `RUN_ORDER.md`.** Minimum demo path: Steps 1, 3, 4, 5, 6, 7, 9, 12. Then Step 9b for the enterprise-readiness score. Steps 8, 10 and 11 (Fabric, Teams, Power BI) can be done after, in that order of priority.

---

## What you are building, and what you may claim

| Pitch statement | Reality | Say it like this |
|---|---|---|
| Built on Fabric | Data and results live in a Fabric Lakehouse, Power BI reads them. A Cloud Shell run reads the Lakehouse directly (`DATA_BACKEND=onelake`). The web app uses the same CSV files shipped with it | "Data and dashboards on Microsoft Fabric" |
| Built on Azure AI Foundry | Models deployed in Foundry, called through the Azure OpenAI API with function calling. The agent loop is our own Python, not Foundry Agent Service | "Agents powered by models deployed in Azure AI Foundry" |
| Multi-agent | Detector, Evidence agent (read-only tools), Root-Cause agent (model + tools), Action agent, Orchestrator (policy routing) | Accurate |
| Guardrails | Prompt Shields on third-party text (plus local patterns), evidence-grounding check, policy file with value limits, never-auto list, rate limit, kill switch, foundry default content filter | Accurate |
| Managers approve in Teams | Teams card notifies and links to the web console. The Approve button is in the web console | "Approval requests reach managers in Teams; decisions are recorded in the console" |
| Audit trail | Every step goes to Cosmos DB and to a file | Accurate |
| Entra agent identities | Not built. Each agent has a read-only tool allowlist in code | Say "least-privilege tool allowlists" |
| Logic Apps | Not used. Actions write to sample systems of record | "Actions simulated against sample systems of record" |

## Cost (estimates, confirm in the portal)

| Item | Plan | Expected cost |
|---|---|---|
| Foundry model (mini, non-reasoning) | Pay as you go | well under 1 USD for the whole project |
| App Service (Linux B1) | 1 small instance | about 1 USD for 2 days if deleted after |
| Cloud Shell storage | Created on first use | a few cents |
| Cosmos DB, AI Search, Content Safety | Free tiers | 0 |
| Fabric | Trial capacity | 0 |

Delete everything at the end (Step 13).

---

### Step 1: Open Cloud Shell
**Goal:** get a terminal inside the portal that is already signed in.

**Do:**
1. Go to https://portal.azure.com and sign in with the hackathon account.
2. Click the `>_` icon in the top bar. Choose **Bash**. If it asks to create storage, accept (a few cents).
3. Check the subscription and pick the one with your credits:
```bash
az account show --query "{name:name, id:id}" -o table
az account list -o table
az account set --subscription "<name or id of the hackathon subscription>"
python3 --version
```
**Check:** `az account show` prints the hackathon subscription. Python is 3.9 or newer.

---

### Step 2: Budget alert
**Goal:** get emailed before spending runs away.

**Do:** Portal search bar > **Cost Management** > **Budgets** > **Add**. Scope: your subscription. Amount: 200. Add alerts at 50% and 75% to your email.

**Check:** the budget appears in the list.

---

### Step 3: Upload the project and install packages
**Goal:** put the code in Cloud Shell and install what it needs.

**Do:**
1. In Cloud Shell click **Manage files** > **Upload** > choose `stocktruth.zip`.
2. Run:
```bash
cd ~
unzip -o stocktruth.zip
cd stocktruth
grep -v streamlit requirements.txt > ~/req-cli.txt
pip install --user -r ~/req-cli.txt
```
3. Prove the code works before touching Azure services (uses built-in sample data, no keys needed):
```bash
python3 scripts/run_pipeline.py --reset
python3 scripts/evaluate.py | tail -1
```
**Check:** the run prints `Detector opened 11 cases` and the summary `{'PENDING_APPROVAL': 3, 'ESCALATED': 2, 'AUTO_EXECUTED': 4, 'AUTO_CLOSED': 2}`. The evaluation prints accuracy 1.0. That 100% comes from the built-in rule engine written against the sample data; it proves the plumbing, not the model. Step 7 measures the model.

If Cloud Shell disconnects later, files stay. Reopen it and run `cd ~/stocktruth`.

---

### Step 4: Create the Azure resources with one script
**Goal:** create AI Search, Cosmos DB and Content Safety, and save every key into `~/stocktruth.env` automatically.

**Do:** pick a short unique suffix (3 to 8 lowercase letters or digits, for example `sk4821`). Use the same suffix everywhere.
```bash
cd ~/stocktruth
bash scripts/azure_setup.sh sk4821 centralindia
```
Cosmos DB takes 3 to 6 minutes. The script prints `ok:` lines and never prints keys.

**Check:** you see `ok: search keys saved`, `ok: cosmos keys saved`, `ok: content safety keys saved`.
If one prints `WARN`, create that service in the portal instead (Create a resource > search the name > pick the free tier), then copy its endpoint and key into the file with:
```bash
echo "SEARCH_ENDPOINT=https://...search.windows.net" >> ~/stocktruth.env
echo "SEARCH_KEY=..." >> ~/stocktruth.env
```
(If a key appears twice in the file, the last one wins.)

Limits to know: only one free Cosmos DB account and one free Search service per subscription. If the region has no free Search, try `eastus` or `southeastasia` as the second argument.

---

### Step 5: Create the model in Foundry
**Goal:** get one small chat model with a key you can call.

**Do:**
1. Go to https://ai.azure.com > **Create project**. Resource group: `rg-stocktruth`. Region: one that has the model. Note the Foundry resource name it creates.
2. **Models + endpoints** > **Deploy model** > pick a small, cheap chat model (for example `gpt-4.1-mini`, or `gpt-4o-mini` if that is what you can deploy). **Do not use a reasoning model.** Deployment name: type exactly `gpt-4.1-mini`. Keep the default content filter on.
3. Back in Cloud Shell, re-run the script with the Foundry resource name so its key is added (it is safe to re-run):
```bash
cd ~/stocktruth
bash scripts/azure_setup.sh sk4821 centralindia <your-foundry-resource-name> rg-stocktruth
```
4. If you used a different deployment name or model, set it:
```bash
echo "MODEL_DEPLOYMENT=<exact deployment name>" >> ~/stocktruth.env
```
**Check:** the script prints `ok: model key saved, LLM_MODE=azure`.
If it says it could not read keys: the resource name or its resource group is wrong (find it in the portal under the resource's Overview).

---

### Step 6: Test every connection
**Goal:** find any 401 or typo now, one service at a time.

**Do:**
```bash
cd ~/stocktruth
python3 scripts/00_check_env.py --create-cosmos
python3 scripts/02_index_knowledge.py
```
**Check:** Azure OpenAI, AI Search and Cosmos DB show `[PASS]`. Content Safety shows `[PASS]` with `attack detected=True`. Fabric and Teams show `[FAIL] ... not set`: that is expected until Steps 8 and 10. Indexing prints `Indexed 14/14 documents`.
Every `[FAIL]` prints a hint for the cause. Fix it before continuing (see Troubleshooting).

---

### Step 7: Run the real investigation and measure the model
**Goal:** run all 11 sample mismatches through the Foundry model and record true accuracy and cost.

**Do:**
```bash
cd ~/stocktruth
python3 scripts/run_pipeline.py --reset
python3 scripts/evaluate.py
```
**Check:**
- The `[engine]` column shows `llm` for most cases. If everything shows `rules`, the model call is failing; read the reason:
```bash
python3 -c "import json;c=json.load(open('outputs/cases.json'));print(set(x['fallback_reason'] for x in c))"
```
- `Total LLM cost (USD)` is a small number.
- Note the accuracy figures. Report the real numbers in your pitch, including misses.

If the model gets a case wrong, open it later in the web app and read its reasoning. Two rounds of tuning are enough: add a clearer line to the matching `knowledge/SOP-*.md` (then re-run `02_index_knowledge.py`) or tighten the signature line in `ROOT_CAUSE_SYSTEM` in `src/stocktruth/agents.py` (edit with `nano`).

---

### Step 8: Fabric workspace, data and tables
**Goal:** put the data in a Fabric Lakehouse, run the investigation against it, and publish results for Power BI.

**Do:**
1. https://app.fabric.microsoft.com > profile icon > **Start trial** (a trial capacity; read the screen for current terms).
2. **Workspaces** > **New workspace** `stocktruth` > Advanced > License mode: **Trial** > Apply.
3. In the workspace: **New item** > **Lakehouse** > name `stocktruth_lh`.
4. Copy the two IDs from the browser address bar: `.../groups/<WORKSPACE_ID>/lakehouses/<LAKEHOUSE_ID>`. In Cloud Shell:
```bash
echo "FABRIC_WORKSPACE_ID=<workspace guid>" >> ~/stocktruth.env
echo "FABRIC_LAKEHOUSE_ID=<lakehouse guid>" >> ~/stocktruth.env
cd ~/stocktruth
python3 scripts/01_upload_to_onelake.py
```
5. Create tables. In Fabric: workspace > **New item** > **Notebook** > attach `stocktruth_lh` (left panel, Add > existing lakehouse). Paste each block below into its own cell and run top to bottom.

Cell 1 (load the CSVs as tables):
```python
tables = ["products", "suppliers", "locations", "pos_sales", "grn", "returns",
          "wms_moves", "adjustments", "pick_exceptions", "stock_counts", "golden_cases"]
for t in tables:
    df = (spark.read.option("header", True).option("inferSchema", True)
          .csv(f"Files/stocktruth/data/{t}.csv"))
    df.write.mode("overwrite").format("delta").saveAsTable(t)
    print(t, df.count())
```
Cell 2 (the detector as SQL; optional, skip if it errors):
```python
spark.sql("""
CREATE OR REPLACE TABLE variance_cases AS
SELECT c.location, c.sku, p.name AS product, p.category, p.supplier_id,
       SUM(c.system_qty - c.counted_qty) AS net_variance,
       MAX(ABS(c.system_qty - c.counted_qty)) AS max_bin_variance,
       GREATEST(ABS(SUM(c.system_qty - c.counted_qty)),
                SUM(ABS(c.system_qty - c.counted_qty)) DIV 2) * p.unit_cost AS value_at_risk_inr
FROM stock_counts c JOIN products p ON p.sku = c.sku
WHERE c.count_date = (SELECT MAX(count_date) FROM stock_counts)
GROUP BY c.location, c.sku, p.name, p.category, p.supplier_id, p.unit_cost
HAVING SUM(c.system_qty - c.counted_qty) <> 0 OR MAX(ABS(c.system_qty - c.counted_qty)) <> 0
""")
display(spark.sql("SELECT * FROM variance_cases ORDER BY value_at_risk_inr DESC"))
```
6. Run the investigation reading straight from Fabric, then publish the results:
```bash
cd ~/stocktruth
DATA_BACKEND=onelake python3 scripts/run_pipeline.py --reset
python3 scripts/01_upload_to_onelake.py --results
```
Back in the Fabric notebook, add Cell 3 and run it:
```python
res = (spark.read.option("header", True).option("inferSchema", True)
       .csv("Files/stocktruth/results/case_results.csv"))
res.write.mode("overwrite").format("delta").saveAsTable("case_results")
display(res)
```
**Check:** Cell 1 prints a row count for every table; the Cloud Shell run says `data=onelake` and finds the same 11 cases; `case_results` shows 11 rows.

**If the upload fails with 401 or 403:** the signed-in account is not a member of the workspace. Workspace > Manage access > add your account as Member. **Manual fallback:** in Cloud Shell run `cd ~/stocktruth && zip -r data.zip data`, use Manage files > Download, then in the Lakehouse create Files > `stocktruth` > `data` and upload the CSVs (this one step needs the downloaded files on a computer).

---

### Step 9: Deploy the approval console as a web app
**Goal:** get a public, password-protected URL for the console (cases, evidence, approve/reject, kill switch, trust dashboard).

**Do:**
```bash
cd ~/stocktruth
echo "APP_PASSWORD=<choose a password>" >> ~/stocktruth.env
bash scripts/deploy_webapp.sh sk4821 centralindia
```
The first deploy takes 5 to 8 minutes (it installs the packages). The script prints the URL: `https://stocktruth-sk4821.azurewebsites.net`.

Then open the URL, enter the password, type your name in the sidebar (reviewer), and click **Run investigation now**.

**Check:** the **Approval inbox** shows 5 cases waiting (3 for approval, 2 escalated). The **Trust dashboard** tab shows metrics. Click **Check accuracy vs answer key** to fill the accuracy tile.

If the site shows an error or a blank page after 3 minutes, see Troubleshooting. Look at live logs with:
```bash
az webapp log tail -g rg-stocktruth -n stocktruth-sk4821
```
Emergency switch to the offline engine (no model calls) if the model misbehaves during the demo:
```bash
az webapp config appsettings set -g rg-stocktruth -n stocktruth-sk4821 --settings LLM_MODE=mock -o none
```
(Set it back to `azure` the same way. Say so in the demo if you use it: cases then show engine `rules`.)

---

### Step 9b: Enterprise hardening (30 minutes, do after Step 9)
**Goal:** add sign-in with Entra ID, monitoring and source control, so the "enterprise ready" claims are true.

**Do:**
1. **Entra sign-in.** Portal > your web app `stocktruth-<sfx>` > **Authentication** > **Add identity provider** > **Microsoft** > keep the defaults > **Require authentication** > Add. Open the URL in a private window and confirm it asks for a Microsoft sign-in. The app password stays as a second gate.
2. **Monitoring.** Same web app > **Application Insights** > **Turn on** > Apply. After a few minutes, **Application Insights > Logs/Failures** show requests and errors.
3. **Source control.** Create a private GitHub repository, then in Cloud Shell:
```bash
cd ~/stocktruth
git init -q && git add -A && git commit -qm "StockTruth Phase-1"
git remote add origin https://github.com/<your-user>/stocktruth.git
git branch -M main && git push -u origin main
```
Check `git status` first: `.env` and `outputs/` are excluded by `.gitignore`, and `~/stocktruth.env` lives outside the project, so no secrets are pushed.
4. **Production steps to state, not build** (see `docs/PRODUCTION_PATH.md`): Key Vault references, managed identity, multi-instance, Foundry Agent Service, write-back through Logic Apps.

**Check:** a private browser window shows a Microsoft sign-in before the console; Application Insights shows traffic; the repo has the code and no keys.

If Entra sign-in blocks you from the console (tenant policy), disable it and rely on the app password; say "Entra sign-in is the production setting".

---

### Step 10: Teams notification (optional)
**Goal:** managers get a card in Teams with a link to the case.

**Do:**
1. Teams > open a channel > `...` > **Workflows** > **Post to a channel when a webhook request is received** > create > copy the URL.
2. In Cloud Shell:
```bash
echo "TEAMS_WEBHOOK_URL=<the url>" >> ~/stocktruth.env
cd ~/stocktruth
python3 scripts/00_check_env.py | grep Teams
bash scripts/deploy_webapp.sh sk4821 centralindia
```
**Check:** the test card appears in the channel. In the web app, click **Run investigation now**: a card arrives for each case that needs a person, and its button opens the web console at that case.

---

### Step 11: Power BI page in Fabric (optional)
**Goal:** a Fabric-native view of the results.

**Do:** Lakehouse > **New semantic model** > select `case_results`, `variance_cases`, `stock_counts`, `products` > **Create new report**. Add four visuals: card (count of `case_id`), donut (`status`), bar (`value_at_risk_inr` by `cause`), table (`case_id`, `cause`, `confidence`, `route`). Save as "StockTruth trust dashboard".

**Check:** the report shows 11 cases.

---

### Step 12: Demo (3 minutes) and backups
**Goal:** rehearse the exact story once, and have fallbacks ready.

**Before you present:** open the web app, click **Run investigation now**, and keep the browser tab open.

| Step | Show | Say |
|---|---|---|
| 1 | Run summary / Trust dashboard | "11 mismatches found. 6 handled without a person, 3 waiting for approval, 2 escalated." |
| 2 | All cases > CASE-STORE_A-SKU003 | "Short delivery above the contract tolerance. The claim is drafted and was under the INR 5,000 auto limit." |
| 3 | Approval inbox > CASE-STORE_B-SKU001 | "Two rice products are off by +12 and -12. The agent saw the swap and the manually keyed sales. Over the limit, so a person decides." Enter your name, click **Approve**. |
| 4 | CASE-STORE_C-SKU014 | "The delivery note carried a hidden instruction to approve everything. It was detected, redacted and ignored, and the case was forced to human review." |
| 5 | CASE-STORE_C-SKU011 | "Repeated unexplained loss. Never auto-actioned, no person named, neutral wording." |
| 6 | Sidebar > Pause all agents | "Kill switch." Try Approve on another case: it is blocked. Resume. |
| 7 | Trust dashboard | Autonomy rate, override rate, accuracy, cost per case, and the planning-impact table: "Planning would have used these stock numbers." |
| 8 | Power BI report (if built) | "Same results in Fabric." |

Backups: record a screen capture of a clean run today. Keep the audit trail tab open for one case. Have the mock-engine switch command (Step 9) ready.

Honest answers for Q&A:
- Data is synthetic, so the saving is an assumption (the console labels it as one).
- Accuracy comes from a small planted set; it shows the approach works, not production accuracy.
- The web app and the Cloud Shell run each keep their own approval state; Fabric shows the Cloud Shell run's results.
- Phase 2 (CCTV to billing) adds one more evidence source; the rest of the flow stays.

---

### Step 13: Clean up after the hackathon
**Goal:** stop all charges.
```bash
az group delete -n rg-stocktruth --yes --no-wait
```
Delete the Foundry project in https://ai.azure.com if it is in another resource group. Fabric trial resources expire on their own.

---

## Phase 2: CCTV-to-billing (wow factor, 1.5 to 2 hours)

Do this only after the demo path (Steps 1 to 9) works. Background: `docs/PHASE2_CCTV.md`. The order of all scripts is in `RUN_ORDER.md`.

### Step P2-1: See it work with sample CCTV events
**Goal:** prove the CCTV-vs-billing logic end to end before spending time on video.

**Do:**
```bash
cd ~/stocktruth
python3 scripts/12_cctv_reconcile.py
python3 scripts/run_pipeline.py --reset | grep -E "CCTV|Summary"
```
**Check:** the reconcile prints 6 findings (5 unbilled units worth INR 5,040, and 2 units on the wrong shelf) and the pipeline prints `CCTV: 6 findings from sample_events.csv`. The Phase-1 accuracy is unchanged.

### Step P2-2: Get the CCTV clips
**Goal:** have 3 to 4 short clips that show a shelf pick, a put-back and a wrong-shelf placement.

**Option A (fastest, already in the zip):** four ready-made sample clips and their `cctv/manifest.csv` are in `cctv/videos/`. They are drawn animations, not real footage (shelf units with large product labels and a faceless silhouette shopper):
| Clip | Store | What happens | Expected result |
|---|---|---|---|
| clip01 | STORE_C | shopper takes 1 razor-cartridge pack and leaves, no sale follows | UNBILLED_PICK |
| clip02 | STORE_B | shopper takes units and puts them back | nothing to report |
| clip03 | STORE_A | shopper places a wheat-atta pack on the wrong shelf (A5-S1, belongs on A3-S2) | MISPLACED_ITEM |
| clip04 | STORE_C | shopper takes razor cartridges and a sale follows | matched, nothing to report |

```bash
cd ~/stocktruth
ls cctv/videos
cat cctv/manifest.csv
```
To re-create them: `pip install --user -r requirements-cctv.txt && python3 scripts/13_cctv_render_samples.py`.

**Option B (more impressive):** make your own with an AI video tool (guidance in `docs/PHASE2_CCTV.md`), upload with Cloud Shell **Manage files > Upload**, then:
```bash
mv ~/clip*.mp4 cctv/videos/
nano cctv/manifest.csv      # one row per clip: clip_id,location,camera,start_ts,file
```
Find real sale times to line up with: `grep ",STORE_C,SKU011," data/pos_sales.csv | head`.

**Check:** `ls cctv/videos` shows the clips and every `file` in the manifest exists.

### Step P2-3: Turn the clips into product events
**Goal:** the vision model in Foundry reads the frames and lists what was picked, returned or misplaced.

**Do:**
```bash
pip install --user -r requirements-cctv.txt
python3 scripts/11_cctv_analyze.py
```
**Check:** each clip prints `[OK] ... frames -> N events` (expect about 1 event for clips 01, 03 and 04, and 2 for clip 02 with the sample clips; model output varies, so judge by the findings in P2-4) and `cctv/cctv_events.csv` is written. Open it with `cat cctv/cctv_events.csv`. If a clip gives 0 events, the products were not readable: regenerate that clip with larger labels. If the model call fails with an image or 400 error, confirm the deployed model supports images (gpt-4.1-mini and gpt-4o-mini do).

### Step P2-4: Compare with billing and re-investigate
**Goal:** the agents see CCTV findings next to the other evidence.

**Do:**
```bash
python3 scripts/12_cctv_reconcile.py
python3 scripts/run_pipeline.py --reset
python3 scripts/evaluate.py | tail -1
```
**Check:** the findings match your story (a missing sale shows as `UNBILLED_PICK`, a put-back shows nothing, a wrong shelf shows `MISPLACED_ITEM`). The evaluation still reports the Phase-1 accuracy.

### Step P2-5: Ship it to the web app and rehearse
**Goal:** the demo console shows the CCTV tab with your clips' results.

**Do:**
```bash
bash scripts/deploy_webapp.sh sk4821 centralindia
```
Open the web app > **CCTV vs billing (Phase 2)** tab > **Compare CCTV events with billing now**, then **Run investigation now** in the sidebar.

**Check:** the tab shows metrics and a findings table; open the STORE_C razor-cartridge case and the evidence now includes the CCTV lead.

**Demo add-on (60 seconds):** "Billing says what was sold. The camera says what left the shelf. Here the camera saw units leave the razor shelf with no sale. StockTruth adds that to the investigation as a lead, not an accusation, and a manager decides. It also found two units on the wrong shelf, which is why the shelf looked empty." If you used the sample events instead of your own clips, say they are synthetic.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| 401 from Azure OpenAI | Key from a different resource, endpoint and key mismatch, or an old line in the env file | Re-run `azure_setup.sh` with the Foundry resource name (it rewrites the key). Open `nano ~/stocktruth.env` and check there are no stray spaces |
| 404 or `DeploymentNotFound` | `MODEL_DEPLOYMENT` is the model name, not the deployment name | Use the deployment name from Foundry > Models + endpoints |
| `api-version` error | Version not accepted | Set `AZURE_OPENAI_API_VERSION` to the version in Foundry's "Get code" sample |
| 429 | Token quota or rate limit | Wait a minute; lower capacity use; deploy in a region with quota |
| 400 about `temperature` or `max_tokens` | You deployed a reasoning model | Deploy a non-reasoning mini model; the code sends neither parameter |
| Every case says engine `rules` | Model call failing | Print the reason (Step 7 command) and run `00_check_env.py` |
| `azure_setup.sh` WARN for Cosmos | One free account per subscription already exists | Use the existing account or create a paid-tier one in the portal |
| Search 403 | Wrong key type | Use the admin key (the script saves the admin key) |
| OneLake 401 or 403 | Account not in the Fabric workspace | Workspace > Manage access > add as Member |
| `az webapp up` quota error for B1 | No quota in region | Run again with another region, e.g. `bash scripts/deploy_webapp.sh sk4821 southeastasia` |
| Web app name taken | Suffix not unique | Use a different suffix everywhere |
| Web app shows "Application Error" or stays blank | Build still running, or startup failed | Wait 3 minutes; `az webapp log tail ...`; re-run `deploy_webapp.sh` |
| Streamlit page loads then says "connecting" forever | Web sockets off | Re-run `deploy_webapp.sh` (it turns them on) |
| Web app shows no cases | Pipeline not run in the app | Click **Run investigation now** in the sidebar |
| Teams card does not arrive | Workflow not published or wrong URL | Re-copy the URL; check the workflow run history |
| CCTV step: 0 events from a clip | Products not readable | Regenerate the clip with large, clear labels using catalogue names |
| Cloud Shell timed out | Idle 20 minutes | Reopen; files persist; `cd ~/stocktruth` |

## File map
```
config/policy.yaml                business guardrails (limits, thresholds, never-auto list)
data/ knowledge/                  synthetic data, answer key, SOPs and contracts
src/stocktruth/                   detector, evidence tools, agents, orchestrator, guardrails, audit, actions
docs/PRODUCTION_PATH.md          judging-criteria map, production path, repeatability (slide text)
scripts/azure_setup.sh            create Search, Cosmos, Content Safety; write keys to ~/stocktruth.env
scripts/deploy_webapp.sh          deploy the console and push settings
scripts/00_check_env.py           test every connection
scripts/01_upload_to_onelake.py   push data or results to Fabric
scripts/02_index_knowledge.py     build the Search index
scripts/run_pipeline.py           run the full flow in Cloud Shell
scripts/10_cctv_make_sample.py    (Phase 2, optional) rebuild synthetic CCTV events
scripts/11_cctv_analyze.py        (Phase 2) video clips to product events
scripts/12_cctv_reconcile.py      (Phase 2) CCTV events vs billing
src/stocktruth/cctv.py            (Phase 2) CCTV logic
cctv/                             (Phase 2) sample events, manifest template, videos folder
RUN_ORDER.md                      what to run, when, where (one table)
scripts/evaluate.py               accuracy against the answer key
app/streamlit_app.py              the console
```

## Change the sample data (optional)
`python3 data_gen/generate_data.py --seed 7` rewrites `data/` and `knowledge/`. The 11 planted cases stay; only the baseline noise changes. Re-upload to Fabric and redeploy the web app after.
