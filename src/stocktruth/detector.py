"""Variance Detector: compares system quantity with counted quantity and opens cases."""
import pandas as pd


def detect(store, policy):
    counts = store.t["stock_counts"].copy()
    latest = counts["count_date"].max()
    cur = counts[counts["count_date"] == latest].copy()
    cur["variance"] = cur["system_qty"] - cur["counted_qty"]
    mv = policy["minor_variance"]
    cases = []
    for (loc, sku), g in cur.groupby(["location", "sku"]):
        net = int(g["variance"].sum())
        bins = [dict(bin=r.bin, system_qty=int(r.system_qty), counted_qty=int(r.counted_qty),
                     variance=int(r.variance)) for r in g.itertuples() if r.variance != 0]
        if net == 0 and not bins:
            continue
        p = store.product(sku)
        sum_abs = int(g["variance"].abs().sum())
        units_at_risk = max(abs(net), sum_abs // 2)
        value = round(units_at_risk * p["unit_cost"], 2)
        has_bin_split = len(bins) >= 2 and any(b["variance"] > 0 for b in bins) and any(b["variance"] < 0 for b in bins)
        is_minor = (abs(net) <= mv["max_units"] and not has_bin_split and value < mv["max_value_inr"])
        cases.append(dict(
            case_id=f"CASE-{loc}-{sku}", location=loc, sku=sku, product=p["name"], category=p["category"],
            supplier_id=p["supplier_id"], unit_cost=p["unit_cost"], count_date=latest,
            net_variance=net, direction="system_higher" if net > 0 else ("system_lower" if net < 0 else "net_zero"),
            bin_variances=bins, value_at_risk_inr=value, is_minor=bool(is_minor)))
    cases.sort(key=lambda c: -c["value_at_risk_inr"])
    return cases


def all_variances(store):
    """(location, sku) -> net variance at the latest count. Used to find offsetting swaps."""
    counts = store.t["stock_counts"]
    cur = counts[counts["count_date"] == counts["count_date"].max()].copy()
    cur["variance"] = cur["system_qty"] - cur["counted_qty"]
    s = cur.groupby(["location", "sku"])["variance"].sum()
    return {k: int(v) for k, v in s.items() if v != 0}
