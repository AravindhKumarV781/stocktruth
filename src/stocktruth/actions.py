"""Action Agent: maps a cause to concrete actions, then executes them (simulated systems of record)."""
import csv
import uuid
from datetime import datetime, timezone


def plan_actions(case, rc, pack):
    cause, net = rc["cause"], case["net_variance"]
    cost = case["unit_cost"]
    acts = []
    if cause == "SHORT_DELIVERY":
        short = [g for g in pack["grn"] if g["short_qty"] > 0]
        claimable = [g for g in short if not g["within_tolerance"] and g["within_claim_window"]]
        if claimable:
            g = max(claimable, key=lambda x: x["short_qty"])
            sup = pack["supplier_terms"]
            acts.append(dict(type="VENDOR_CLAIM", params=dict(
                supplier_id=g["supplier_id"], po_id=g["po_id"], grn_id=g["grn_id"], short_qty=g["short_qty"],
                short_pct=g["short_pct"], tolerance_pct=g["contract_tolerance_pct"],
                claim_value_inr=round(g["short_qty"] * cost, 2), email=sup["claim_email"])))
            acts.append(dict(type="STOCK_CORRECTION", bundled_with_claim=True, params=dict(
                qty_delta=-net, note="Correct system stock to the received quantity (bundled with the claim).")))
        else:
            why = "shortfall is within the contract tolerance" if short and all(g["within_tolerance"] for g in short) \
                else "claim window has passed"
            acts.append(dict(type="STOCK_CORRECTION", params=dict(
                qty_delta=-net, note=f"No claim allowed: {why}.")))
    elif cause == "SCAN_ERROR":
        other = pack["offsetting"][0]["sku"] if pack["offsetting"] else "a similar item"
        acts.append(dict(type="STOCK_CORRECTION", params=dict(
            qty_delta=-net, note=f"Correct together with {other}; they offset each other.")))
        acts.append(dict(type="PROCESS_TICKET", params=dict(
            note=f"Billing scan substitution pattern between {case['sku']} and {other} at {case['location']}. "
                 "Review manual-key controls and scanner training at shift level. No individual is implicated.")))
    elif cause == "RETURN_NOT_WRITTEN_OFF":
        acts.append(dict(type="STOCK_CORRECTION", params=dict(
            qty_delta=-net, note="Record the missing write-off for discarded defective returns.")))
    elif cause == "MISSLOTTED":
        over = [b["bin"] for b in case["bin_variances"] if b["variance"] > 0]
        under = [b["bin"] for b in case["bin_variances"] if b["variance"] < 0]
        acts.append(dict(type="BIN_SEARCH", params=dict(
            system_bin=over[0] if over else "", bins=under, note="Count shows the stock in the listed bins.")))
    elif cause == "SUSPECTED_LOSS":
        acts.append(dict(type="ESCALATE_LOSS_PREVENTION", params=dict(note="Unexplained loss. Human owner only.")))
    elif cause == "MINOR_COUNT_VARIANCE":
        acts.append(dict(type="NONE", params=dict(note="Within minor variance policy. Closed.")))
    else:
        acts.append(dict(type="RECOUNT", params=dict(note="Evidence insufficient. Recount the location and re-run.")))
    return acts


def _append(path, row):
    new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        if new:
            w.writeheader()
        w.writerow(row)


def execute_action(settings, action, case):
    """Simulated systems of record: CSV files in outputs/ (load them to Fabric for Power BI)."""
    out = settings.out_dir
    now = datetime.now(timezone.utc).isoformat()
    t = action["type"]
    d = action.get("draft", {})
    if t == "NONE":
        return "closed, nothing to do"
    if t == "VENDOR_CLAIM":
        (out / "claims").mkdir(exist_ok=True)
        p = out / "claims" / f"{case['case_id']}.txt"
        p.write_text(f"TO: {action['params']['email']}\nSUBJECT: {d.get('title','')}\n\n{d.get('body','')}\n", encoding="utf-8")
        _append(out / "actions_log.csv", dict(ts=now, case_id=case["case_id"], type=t, ref=p.name,
                                              value_inr=action["params"]["claim_value_inr"]))
        return f"claim drafted: {p.name}"
    if t == "STOCK_CORRECTION":
        _append(out / "stock_adjustments.csv", dict(adj_id="ADJ-" + uuid.uuid4().hex[:8], ts=now,
                                                    location=case["location"], sku=case["sku"],
                                                    qty_delta=action["params"]["qty_delta"],
                                                    reason=case.get("cause", ""), case_id=case["case_id"]))
        return f"stock adjusted by {action['params']['qty_delta']}"
    if t in ("BIN_SEARCH", "RECOUNT", "PROCESS_TICKET", "ESCALATE_LOSS_PREVENTION"):
        _append(out / "tasks.csv", dict(task_id="TASK-" + uuid.uuid4().hex[:8], ts=now, case_id=case["case_id"],
                                        type=t, location=case["location"], sku=case["sku"],
                                        title=d.get("title", t), instruction=(d.get("body", "") or "")[:500],
                                        status="open"))
        return f"task created ({t})"
    return "unknown action type"
