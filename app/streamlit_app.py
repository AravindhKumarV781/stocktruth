"""StockTruth manager console: approvals, evidence ("why this decision"), kill switch, trust dashboard.
Run:  streamlit run app/streamlit_app.py"""
import json
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from stocktruth.approvals import decide, kill_switch_state, load_cases, set_kill_switch  # noqa: E402
from stocktruth.config import Settings  # noqa: E402
from stocktruth.evaluation import run_eval  # noqa: E402
from stocktruth.orchestrator import run_pipeline  # noqa: E402

st.set_page_config(page_title="StockTruth", layout="wide")
S = Settings()

# simple access gate for the demo (set APP_PASSWORD in the web app settings)
_pw = os.environ.get("APP_PASSWORD", "")
if _pw and not st.session_state.get("auth"):
    st.title("StockTruth")
    entered = st.text_input("Access password", type="password")
    if entered and entered == _pw:
        st.session_state["auth"] = True
        st.rerun()
    elif entered:
        st.error("Wrong password")
    st.stop()

STATUS_ICON = {"AUTO_EXECUTED": "Auto-handled", "AUTO_CLOSED": "Auto-closed", "PENDING_APPROVAL": "Needs approval",
               "ESCALATED": "Escalated", "APPROVED_EXECUTED": "Approved", "REJECTED": "Rejected",
               "ESCALATION_ACKNOWLEDGED": "Escalation acknowledged", "BLOCKED_KILL_SWITCH": "Blocked (kill switch)"}


def load_audit():
    p = S.out_dir / "audit.jsonl"
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


# ---------------- sidebar
ks = kill_switch_state(S)
with st.sidebar:
    st.title("StockTruth")
    st.caption("Governed stock investigation")
    if ks.get("active"):
        st.error("KILL SWITCH ACTIVE: all actions paused")
        if st.button("Resume agents"):
            set_kill_switch(False, "console")
            st.rerun()
    else:
        st.success("Agents running")
        if st.button("Pause all agents (kill switch)"):
            set_kill_switch(True, "console")
            st.rerun()
    st.divider()
    st.write(f"LLM mode: `{S.llm_mode}`  \nData: `{S.data_backend}`")
    if st.button("Run investigation now"):
        with st.spinner("Detecting and investigating..."):
            run_pipeline(S, progress=lambda *_: None)
        st.rerun()
    if st.button("Check accuracy vs answer key"):
        try:
            run_eval(S)
            st.rerun()
        except Exception as e:
            st.error(str(e))
    reviewer = st.text_input("Your name (reviewer)", value="")
    role = st.selectbox("Your role", ["Inventory Manager", "Store Manager", "Loss Prevention Head"])

cases = load_cases(S)
if not cases:
    st.info("No cases yet. Click 'Run investigation now' in the sidebar.")
    st.stop()

focus = st.query_params.get("case")
tab_inbox, tab_all, tab_trust, tab_audit, tab_cctv = st.tabs(
    ["Approval inbox", "All cases", "Trust dashboard", "Audit trail", "CCTV vs billing (Phase 2)"])


def case_card(c, key):
    ev = c.get("evidence") or {}
    cols = st.columns(4)
    cols[0].metric("Variance (units)", c["net_variance"])
    cols[1].metric("Value at risk (INR)", f"{c['value_at_risk_inr']:,.0f}")
    cols[2].metric("Likely cause", c["cause"].replace("_", " ").title())
    cols[3].metric("Confidence", c["confidence"])
    st.write(f"**Route:** {c['route']}  |  **Why:** " + "; ".join(c["route_reasons"]))
    if c.get("security_flags"):
        st.warning("Security: instructions hidden in a source document were detected, redacted and ignored. "
                   + "; ".join(f["where"] for f in c["security_flags"]))
    st.write("**Why this decision**")
    st.write(c["reasoning"])
    if c.get("evidence_refs"):
        st.caption("Evidence used: " + ", ".join(c["evidence_refs"]))
    if c.get("citations"):
        st.caption("Policy cited: " + ", ".join(c["citations"]))
    st.caption(f"Engine: {c['engine']}" + (f" ({c['fallback_reason']})" if c.get("fallback_reason") else ""))
    for a in c["actions"]:
        d = a.get("draft") or {}
        st.write(f"**Proposed action: {a['type']}**" + (f" - {d.get('title', '')}" if d else ""))
        if d.get("body"):
            st.code(d["body"], language=None)
    with st.expander("Raw evidence pack"):
        st.json(ev)
    if c["status"] in ("PENDING_APPROVAL", "ESCALATED"):
        comment = st.text_input("Comment (optional)", key=f"cm-{key}")
        b1, b2, _ = st.columns([1, 1, 4])
        if b1.button("Approve", key=f"ap-{key}", type="primary"):
            try:
                decide(c["case_id"], "approve", reviewer, role, comment, S)
                st.rerun()
            except Exception as e:
                st.error(str(e))
        if b2.button("Reject", key=f"rj-{key}"):
            try:
                decide(c["case_id"], "reject", reviewer, role, comment, S)
                st.rerun()
            except Exception as e:
                st.error(str(e))
    elif c.get("decision"):
        d = c["decision"]
        st.success(f"{d['decision'].title()}d by {d['reviewer']} ({d['role']}). {d.get('comment', '')}")
    if c.get("execution_results"):
        st.caption("Executed: " + "; ".join(c["execution_results"]))


with tab_inbox:
    pending = [c for c in cases if c["status"] in ("PENDING_APPROVAL", "ESCALATED")]
    st.subheader(f"{len(pending)} cases waiting for a person")
    for c in pending:
        with st.expander(f"{c['case_id']}  |  {STATUS_ICON[c['status']]}  |  INR {c['value_at_risk_inr']:,.0f}  |  {c['cause']}",
                         expanded=(focus == c["case_id"])):
            case_card(c, "i-" + c["case_id"])

with tab_all:
    df = pd.DataFrame([dict(case=c["case_id"], product=c["product"], variance=c["net_variance"],
                            value_inr=c["value_at_risk_inr"], cause=c["cause"], confidence=c["confidence"],
                            route=c["route"], status=STATUS_ICON.get(c["status"], c["status"]),
                            engine=c["engine"]) for c in cases])
    st.dataframe(df, hide_index=True)
    pick = st.selectbox("Open a case", [c["case_id"] for c in cases])
    case_card(next(c for c in cases if c["case_id"] == pick), "a-" + pick)

with tab_trust:
    n = len(cases)
    auto = sum(c["status"] in ("AUTO_EXECUTED", "AUTO_CLOSED") for c in cases)
    decided = [c for c in cases if c.get("decision")]
    rejected = sum(c["decision"]["decision"] == "reject" for c in decided)
    escal = sum(c["route"] == "ESCALATE" for c in cases)
    inj = sum(bool(c.get("security_flags")) for c in cases)
    cost = sum(c.get("cost_usd", 0) for c in cases)
    secs = sum(c.get("elapsed_s", 0) for c in cases)
    r1 = st.columns(4)
    r1[0].metric("Cases investigated", n)
    r1[1].metric("Autonomy rate", f"{100 * auto / n:.0f}%")
    r1[2].metric("Human override rate", f"{100 * rejected / len(decided):.0f}%" if decided else "n/a (no decisions yet)")
    r1[3].metric("Never-auto escalations", escal)
    r2 = st.columns(4)
    ev_p = S.out_dir / "eval.json"
    if ev_p.exists():
        e = json.loads(ev_p.read_text(encoding="utf-8"))
        r2[0].metric("Cause accuracy vs golden set", f"{100 * e['cause_accuracy']:.0f}%")
    else:
        r2[0].metric("Cause accuracy vs golden set", "click Check accuracy")
    r2[1].metric("Injection attempts blocked", inj)
    r2[2].metric("Model cost per case (USD)", f"{cost / n:.4f}")
    r2[3].metric("Machine time per case (s)", f"{secs / n:.1f}")
    manual = st.number_input("Assumed manual investigation time per case (minutes) - ASSUMPTION", 10, 600, 120)
    st.caption(f"Assumption-based estimate: {n} cases x {manual} min manual = {n * manual / 60:.0f} analyst hours, "
               f"versus about {secs / 60:.1f} min of machine time plus manager review. Replace with real figures when available.")
    st.caption("Engine mix: " + str(pd.Series([c["engine"] for c in cases]).value_counts().to_dict())
               + "  ('rules' means the model was not used for that case.)")
    chart = pd.Series([STATUS_ICON.get(c["status"], c["status"]) for c in cases]).value_counts()
    st.bar_chart(chart)

    st.subheader("Why this matters for inventory planning")
    st.caption("Forecasts and replenishment read system stock. These are the numbers planning would have used "
               "versus the counted reality (14-day average sales).")
    plan = []
    for c in cases:
        ev = c.get("evidence")
        if not ev or not ev.get("count_history"):
            continue
        last = ev["count_history"][-1]
        daily = max(ev["pos"]["total_qty"] / 14.0, 0.1)
        plan.append(dict(case=c["case_id"], system_stock=last["system_qty"], real_stock=last["counted_qty"],
                         system_days_of_cover=round(last["system_qty"] / daily, 1),
                         real_days_of_cover=round(last["counted_qty"] / daily, 1),
                         stock_value_overstated_inr=round(c["net_variance"] * c["unit_cost"], 0)))
    if plan:
        st.dataframe(pd.DataFrame(plan), hide_index=True)

with tab_audit:
    audit = load_audit()
    cid = st.selectbox("Case", ["(all)"] + sorted({a["case_id"] for a in audit}))
    rows = [a for a in audit if cid in ("(all)", a["case_id"])]
    st.dataframe(pd.DataFrame([dict(ts=a["ts"], case=a["case_id"], step=a["step"], actor=a["agent"],
                                    detail=json.dumps(a["payload"])[:300]) for a in rows]),
                 hide_index=True)

with tab_cctv:
    st.markdown("**Phase 2.** Camera events (what left the shelf) compared with billing (what was sold). "
                "Findings are leads for a person to check, never proof. Only product events are used: no faces, no identities.")
    from stocktruth.cctv import load_findings, reconcile_to_file
    from stocktruth.config import Settings as _S
    from stocktruth.data_access import DataStore as _DS
    if st.button("Compare CCTV events with billing now"):
        _s = _S()
        _df, _src = reconcile_to_file(_s, _DS.load(_s))
        st.success(f"Done using {_src}" if _df is not None else "No CCTV events file found.")
    fnd = load_findings(_S())
    if fnd.empty:
        st.info("No findings yet. Click the button above.")
    else:
        c1, c2, c3 = st.columns(3)
        ub = fnd[fnd["type"] == "UNBILLED_PICK"]
        c1.metric("Units taken with no matching sale", int(ub["qty"].sum()))
        c2.metric("Value at shelf price (INR)", int(ub["value_inr"].sum()))
        c3.metric("Items on the wrong shelf", int(fnd.loc[fnd["type"] == "MISPLACED_ITEM", "qty"].sum()))
        st.dataframe(fnd.drop(columns=["ref"]), hide_index=True)
        st.caption("Click 'Run investigation now' again: the agents then use these findings as extra evidence "
                   "(for example repeated unbilled picks next to an unexplained stock surplus).")
