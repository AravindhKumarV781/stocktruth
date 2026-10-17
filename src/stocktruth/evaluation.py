"""Compare pipeline output with the golden answer key and write outputs/eval.json."""
import json

import pandas as pd


def run_eval(settings):
    gold_path = settings.data_dir / "golden_cases.csv"
    cases_path = settings.out_dir / "cases.json"
    if not gold_path.exists() or not cases_path.exists():
        raise FileNotFoundError("Need data/golden_cases.csv and a finished pipeline run (outputs/cases.json).")
    gold = pd.read_csv(gold_path)
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    by = {(c["location"], c["sku"]): c for c in cases}
    rows = []
    for g in gold.itertuples():
        c = by.get((g.location, g.sku))
        if c is None:
            rows.append(dict(case=f"{g.location}/{g.sku}", expected=g.true_cause, got="NOT DETECTED",
                             cause_ok=False, route_ok=False, action_ok=False, engine="none"))
            continue
        prim = c["actions"][0]["type"] if c["actions"] else "NONE"
        rows.append(dict(case=c["case_id"], expected=g.true_cause, got=c["cause"], cause_ok=c["cause"] == g.true_cause,
                         expected_route=g.expected_route, got_route=c["route"], route_ok=c["route"] == g.expected_route,
                         expected_action=g.expected_action, got_action=prim, action_ok=prim == g.expected_action,
                         engine=c["engine"]))
    df = pd.DataFrame(rows)
    gold_keys = set(zip(gold.location, gold.sku))
    result = dict(
        cases_expected=len(gold), cases_detected=len(cases),
        false_alarms=[c["case_id"] for c in cases if (c["location"], c["sku"]) not in gold_keys],
        cause_accuracy=round(float(df["cause_ok"].mean()), 3), route_accuracy=round(float(df["route_ok"].mean()), 3),
        action_accuracy=round(float(df["action_ok"].mean()), 3),
        injection_cases_flagged=sum(bool(c.get("security_flags")) for c in cases),
        engines=df["engine"].value_counts().to_dict(),
        theft_never_auto=all(c["status"] in ("ESCALATED", "ESCALATION_ACKNOWLEDGED") for c in cases
                             if c["cause"] == "SUSPECTED_LOSS"),
        rows=rows)
    (settings.out_dir / "eval.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    return df, result
