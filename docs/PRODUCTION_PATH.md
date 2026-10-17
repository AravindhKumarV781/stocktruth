# Pitch material: judging criteria map, production path, repeatability

## 1. Business impact (30%): problem to outcome
- Problem: when system stock and physical stock disagree, people spend hours across POS, warehouse, receiving and returns records to find out why. Meanwhile planning and replenishment run on wrong numbers.
- Solution: StockTruth investigates each mismatch, names the cause with evidence, drafts the fix, and a manager approves.
- Outcomes to show (all measurable in the console): share of mismatches resolved without a person (autonomy rate), manager override rate, cause accuracy vs answer key, cost per case, value at risk surfaced, and the stock-number error that planning would otherwise have used (planning-impact table).
- Time saved is an ASSUMPTION on synthetic data (state your baseline, for example "about 45 minutes per manual investigation"); validate it in a pilot with one retailer's real exceptions.

## 2. AI innovation and agentic design (30%)
- Reinvents the process: from "report a variance" to "explain it, evidence it, fix it, learn from overrides".
- Patterns used: multi-agent roles, tool calling over read-only evidence tools, RAG over SOPs and supplier contracts, policy-based routing, human-in-the-loop approval, rules fallback if the model fails.
- Prototype to production: see section 4.

## 3. Enterprise readiness (30%): controls in the prototype
| Control | In the prototype | Production step |
|---|---|---|
| Responsible AI | Prompt Shields plus pattern scan on third-party text, model content filter, evidence-grounding check, neutral wording, no individuals named | Red-team test set, periodic review |
| Governance | policy.yaml limits, never-auto causes, rate limit, kill switch, segregation of duties (agents cannot approve) | Policy owned by risk team, change-controlled in GitHub |
| Audit | Every step to Cosmos DB and file | Immutable storage, retention policy |
| Identity | Entra sign-in on the web app, role names recorded on each decision | Entra groups for reviewer/approver roles, agent identities via managed identity |
| Secrets | App settings | Key Vault references, managed identity for Cosmos and Search |
| Observability | Application Insights, cost per case, engine and fallback reason per case | Alerts on fallback rate, override rate, cost |
| Reliability | Rules fallback when the model is unavailable; kill switch | Retries and queue, multi-instance, slots |
| Data | Fabric Lakehouse via OneLake | Live POS/WMS ingestion with Fabric pipelines or Eventstream |

## 4. Path from prototype to production
1. Pilot: one retailer, one category, read-only, human approves every action.
2. Connect real feeds (POS, WMS, receiving, returns) into Fabric; map to the same table shapes.
3. Move the agent loop to Foundry Agent Service; keep policy.yaml as the governance layer.
4. Write-back through Logic Apps or APIs after approval, with Entra-scoped identities.
5. Raise autonomy only where override rate stays low.

## 5. Platform alignment (5%)
Azure App Service, Foundry (model deployments), Fabric (Lakehouse, Power BI), AI Search, Cosmos DB, Content Safety, Entra ID, Application Insights, Teams, GitHub (source and change control).

## 6. Repeatability (5%)
- Reusable engine: detect, investigate, route, approve. Customer-specific parts are configuration: data adapters, SOP and contract documents, policy.yaml.
- Same pattern in Manufacturing (scrap and yield variance, WIP vs ERP) and Financial Services (reconciliation breaks).
- Offer: fixed-scope pilot, then a managed accelerator (data onboarding checklist, policy workshop, evaluation set) that drives Azure and Fabric consumption.
