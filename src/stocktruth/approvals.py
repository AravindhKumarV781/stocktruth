"""Human-in-the-loop decisions, case persistence and the kill switch."""
import json
from datetime import datetime, timezone

from .actions import execute_action
from .audit import Audit
from .config import Settings, dumps


def _now():
    return datetime.now(timezone.utc).isoformat()


# ---------- persistence
def load_cases(settings=None):
    s = settings or Settings()
    p = s.out_dir / "cases.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def save_cases(cases, settings=None):
    s = settings or Settings()
    (s.out_dir / "cases.json").write_text(dumps(cases, indent=1), encoding="utf-8")


# ---------- kill switch
def kill_switch_state(settings=None):
    s = settings or Settings()
    p = s.control_dir / "kill_switch.json"
    if not p.exists():
        return dict(active=False)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return dict(active=True, by="system", reason="kill switch file unreadable, failing closed")


def set_kill_switch(active, by="manager", settings=None):
    s = settings or Settings()
    (s.control_dir / "kill_switch.json").write_text(
        json.dumps(dict(active=bool(active), by=by, ts=_now())), encoding="utf-8")
    Audit(s).log("-", "kill_switch", f"human:{by}", dict(active=bool(active)))


# ---------- decisions
def decide(case_id, decision, reviewer, role="Inventory Manager", comment="", settings=None):
    """decision: 'approve' or 'reject'. Agents can never approve (segregation of duties)."""
    s = settings or Settings()
    if str(reviewer).lower().startswith("agent") or not str(reviewer).strip():
        raise PermissionError("Approvals must come from a named human reviewer, never from an agent.")
    if kill_switch_state(s).get("active"):
        raise PermissionError("Kill switch is active. Actions are paused.")
    cases = load_cases(s)
    c = next((x for x in cases if x["case_id"] == case_id), None)
    if c is None:
        raise KeyError(case_id)
    if c["status"] not in ("PENDING_APPROVAL", "ESCALATED"):
        raise ValueError(f"case is {c['status']}, nothing to decide")
    audit = Audit(s)
    c["decision"] = dict(decision=decision, reviewer=reviewer, role=role, comment=comment, ts=_now())
    if decision == "approve":
        results = []
        for a in c["actions"]:
            if a["type"] == "ESCALATE_LOSS_PREVENTION":
                continue
            results.append(execute_action(s, a, c))
        c["status"] = "APPROVED_EXECUTED" if c["status"] == "PENDING_APPROVAL" else "ESCALATION_ACKNOWLEDGED"
        c["execution_results"] = c.get("execution_results", []) + results
    else:
        c["status"] = "REJECTED"
    audit.log(case_id, "human_decision", f"human:{reviewer}", dict(decision=decision, role=role, comment=comment,
                                                                    status=c["status"]))
    save_cases(cases, s)
    return c
