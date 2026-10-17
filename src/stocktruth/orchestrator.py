"""Orchestrator: detect -> investigate -> reason -> route by policy -> act or ask a human."""
import time
from datetime import datetime, timezone

import pandas as pd

from .actions import execute_action, plan_actions
from .agents import draft_text, root_cause_agent
from .approvals import kill_switch_state, save_cases
from .audit import Audit
from .config import Settings, dumps, load_policy
from .data_access import DataStore
from .detector import detect
from .evidence import Evidence
from .guardrails import Guard, validate_root_cause
from .kb import KB
from .llm import LLM
from .notify import send_teams


def route_case(case, rc, actions, pack, policy, auto_used):
    """Business guardrails. Returns (route, reasons). Every rule that fires adds a reason."""
    cause, conf, value = rc["cause"], rc["confidence"], case["value_at_risk_inr"]
    primary = actions[0]["type"] if actions else "NONE"
    lim = policy["limits_inr"]
    if cause in policy["never_auto_causes"]:
        return "ESCALATE", [f"{cause} is on the never-auto list: a human owner decides; no individual is named"]
    if cause == "MINOR_COUNT_VARIANCE":
        return "AUTO_CLOSE", ["within minor variance policy"]
    reasons = []
    if policy.get("require_human_if_injection") and pack["security_flags"]:
        reasons.append("injected instructions were found in a source document and ignored; human check required")
    if policy.get("require_grounded_evidence") and cause != "UNKNOWN" and not rc["evidence_refs"]:
        reasons.append("cause is not backed by any verifiable evidence reference")
    if cause == "UNKNOWN":
        reasons.append("evidence is insufficient")
    if conf < policy["confidence"]["auto_min"]:
        reasons.append(f"confidence {conf} is below the auto threshold {policy['confidence']['auto_min']}")
    if primary == "VENDOR_CLAIM" and value > lim["vendor_claim_auto"]:
        reasons.append(f"claim value INR {value:,.0f} is above the auto limit INR {lim['vendor_claim_auto']:,}")
    if primary == "STOCK_CORRECTION" and value > lim["stock_correction_auto"]:
        reasons.append(f"stock correction value INR {value:,.0f} is above the auto limit INR {lim['stock_correction_auto']:,}")
    if primary not in ("VENDOR_CLAIM", "STOCK_CORRECTION") and primary not in policy["auto_action_types"]:
        reasons.append(f"action {primary} always needs a person")
    if auto_used >= policy["max_auto_actions_per_run"]:
        reasons.append("auto-action rate limit reached for this run")
    if reasons:
        return "HUMAN_REVIEW", reasons
    return "AUTO", ["confidence and value are within policy limits"]


def process_case(case, ctx, auto_used):
    s, policy, llm, ev, audit = ctx["s"], ctx["policy"], ctx["llm"], ctx["ev"], ctx["audit"]
    t0 = time.perf_counter()
    snap = llm.snapshot()
    cid = case["case_id"]
    audit.log(cid, "case_opened", "agent:detector", dict(net=case["net_variance"], value=case["value_at_risk_inr"],
                                                         bins=case["bin_variances"]))
    rec = dict(case, created_ts=datetime.now(timezone.utc).isoformat(), decision=None, execution_results=[])

    if case["is_minor"]:
        rc = dict(cause="MINOR_COUNT_VARIANCE", confidence=0.95, evidence_refs=[], alternatives=[], citations=[],
                  reasoning="Variance is within the minor variance policy (small units and low value).")
        rec.update(rc, engine="rules", fallback_reason="minor variance rule, no model call needed",
                   evidence=None, security_flags=[], actions=[dict(type="NONE", params={}, draft={})],
                   route="AUTO_CLOSE", route_reasons=["within minor variance policy"], status="AUTO_CLOSED")
        audit.log(cid, "auto_closed", "agent:orchestrator", dict(reason="minor variance"))
    else:
        pack = ev.collect(case)
        audit.log(cid, "evidence_collected", "agent:evidence",
                  dict(sources=pack["sources_checked"], findings=pack["findings"],
                       security_flags=pack["security_flags"]))
        if pack["security_flags"]:
            audit.log(cid, "guardrail_blocked_injection", "guard:prompt_shields", dict(flags=pack["security_flags"]))
        raw, engine, why = root_cause_agent(llm, ev, pack)
        rc, problems = validate_root_cause(raw, set(pack["valid_refs"]))
        audit.log(cid, "root_cause", f"agent:root_cause[{engine}]",
                  dict(cause=rc["cause"], confidence=rc["confidence"], refs=rc["evidence_refs"],
                       problems=problems, fallback_reason=why))
        actions = plan_actions(case, rc, pack)
        rec.update(rc, engine=engine, fallback_reason=why, validation_problems=problems,
                   security_flags=pack["security_flags"], actions=actions)
        route, reasons = route_case(case, rc, actions, pack, policy, auto_used)
        rec["route"], rec["route_reasons"] = route, reasons
        rec["cause_for_log"] = rc["cause"]
        for a in actions:
            a["draft"] = draft_text(llm, a, case, rc)
        rec["evidence"] = {k: v for k, v in pack.items() if k != "valid_refs"}
        audit.log(cid, "routed", "agent:orchestrator", dict(route=route, reasons=reasons))
        if route == "AUTO":
            results = [execute_action(s, a, rec) for a in actions]
            rec.update(status="AUTO_EXECUTED", execution_results=results)
            audit.log(cid, "auto_executed", "agent:action", dict(results=results))
        elif route == "HUMAN_REVIEW":
            rec["status"] = "PENDING_APPROVAL"
            rec["teams"] = send_teams(s, rec)
            audit.log(cid, "approval_requested", "agent:action", dict(teams=rec["teams"]))
        else:
            rec["status"] = "ESCALATED"
            rec["teams"] = send_teams(s, rec)
            audit.log(cid, "escalated", "agent:action", dict(teams=rec["teams"]))
            for a in actions:        # create the escalation task only; no stock, claim or accusation
                if a["type"] == "ESCALATE_LOSS_PREVENTION":
                    rec["execution_results"].append(execute_action(s, a, rec))
    rec["elapsed_s"] = round(time.perf_counter() - t0, 2)
    rec.update(llm.cost_since(snap))
    return rec


def run_pipeline(settings=None, policy=None, progress=print):
    s = settings or Settings()
    policy = policy or load_policy()
    store = DataStore.load(s)
    guard, kb, audit, llm = Guard(s), KB(s), Audit(s), LLM(s)
    ev = Evidence(store, guard, kb, s)
    ctx = dict(s=s, policy=policy, llm=llm, ev=ev, audit=audit)
    cases = detect(store, policy)
    try:    # Phase 2: refresh CCTV-vs-billing findings so agents see them (skipped if no CCTV events exist)
        from .cctv import reconcile_to_file
        cv, cv_src = reconcile_to_file(s, store)
        if cv is not None:
            progress(f"CCTV: {len(cv)} findings from {cv_src}")
    except Exception as e:
        progress(f"CCTV skipped: {e}")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    audit.log("-", "run_started", "agent:orchestrator",
              dict(run_id=run_id, cases=len(cases), llm_mode=s.llm_mode, kb=kb.engine, data=s.data_backend,
                   cosmos=bool(audit.container)))
    progress(f"Detector opened {len(cases)} cases | llm_mode={s.llm_mode} | kb={kb.engine} | data={s.data_backend}")
    results, auto_used = [], 0
    for c in cases:
        ks = kill_switch_state(s)
        if ks.get("active"):
            rec = dict(c, status="BLOCKED_KILL_SWITCH", route="BLOCKED", route_reasons=["kill switch active"],
                       cause="NOT_ASSESSED", confidence=0, reasoning="", actions=[], evidence=None,
                       security_flags=[], decision=None, execution_results=[], elapsed_s=0, cost_usd=0,
                       tokens_in=0, tokens_out=0, llm_calls=0, engine="none", fallback_reason="kill switch")
            audit.log(c["case_id"], "blocked_by_kill_switch", "guard:kill_switch", ks)
            results.append(rec)
            progress(f"  {c['case_id']}: BLOCKED (kill switch)")
            continue
        rec = process_case(c, ctx, auto_used)
        if rec["status"] == "AUTO_EXECUTED":
            auto_used += 1
        results.append(rec)
        progress(f"  {rec['case_id']:24s} {rec['cause']:24s} conf={rec['confidence']:<4} -> {rec['route']:12s} "
                 f"[{rec['engine']}] {rec['status']}")
    for r in results:
        r["run_id"] = run_id
    save_cases(results, s)
    flat = pd.DataFrame([{k: v for k, v in r.items() if k in (
        "run_id", "case_id", "location", "sku", "product", "category", "net_variance", "value_at_risk_inr", "cause",
        "confidence", "route", "status", "engine", "elapsed_s", "cost_usd", "tokens_in", "tokens_out")}
        for r in results])
    flat.to_csv(s.out_dir / "case_results.csv", index=False)
    return results
