"""Evidence Agent: read-only tools that pull records for one case. Also exposed as LLM tools."""
import pandas as pd

from .detector import all_variances

TOOL_SPECS = [
    {"name": "get_pos_sales", "description": "Billing summary for a SKU at a location, including manual-key sales.",
     "params": ["location", "sku"]},
    {"name": "get_grn", "description": "Supplier deliveries (GRN) with shortfall vs invoice and contract tolerance.",
     "params": ["location", "sku"]},
    {"name": "get_returns", "description": "Customer returns and their disposition for a SKU at a location.",
     "params": ["location", "sku"]},
    {"name": "get_wms_moves", "description": "Warehouse bin movements (putaway, transfers) for a SKU.",
     "params": ["location", "sku"]},
    {"name": "get_pick_exceptions", "description": "Short picks logged for a SKU at a location.",
     "params": ["location", "sku"]},
    {"name": "get_adjustments", "description": "Recorded stock adjustments (damage write-offs) for a SKU.",
     "params": ["location", "sku"]},
    {"name": "get_count_history", "description": "System vs counted quantity at each count date.",
     "params": ["location", "sku"]},
    {"name": "find_offsetting_variances", "description": "Other SKUs in same store and category with the opposite variance.",
     "params": ["location", "sku"]},
    {"name": "get_cctv_findings", "description": "CCTV-vs-billing leads for a SKU at a store (items taken with no sale, items left on the wrong shelf). Leads only, not proof.",
     "params": ["location", "sku"]},
    {"name": "search_policy", "description": "Search SOPs, supplier contracts and loss policy. Use for citations.",
     "params": ["query"]},
]


def openai_tools():
    out = []
    for t in TOOL_SPECS:
        props = {p: {"type": "string"} for p in t["params"]}
        out.append({"type": "function", "function": {
            "name": t["name"], "description": t["description"],
            "parameters": {"type": "object", "properties": props, "required": t["params"]}}})
    return out


class Evidence:
    """All methods are read-only. Third-party free text is scanned and redacted if it holds an attack."""

    def __init__(self, store, guard, kb, settings=None):
        self.store, self.guard, self.kb, self.settings = store, guard, kb, settings
        self.variances = all_variances(store)
        self.flags = []

    # ---------- individual tools
    def get_pos_sales(self, location, sku):
        df = self.store.rows("pos_sales", location, sku)
        by = df.groupby("scan_method")["qty"].sum().to_dict()
        mk = df[df["scan_method"] == "manual_key"]
        return dict(ref=f"pos:{location}:{sku}", total_qty=int(df["qty"].sum()),
                    by_scan_method={k: int(v) for k, v in by.items()},
                    manual_key_qty=int(mk["qty"].sum()),
                    manual_key_shifts=mk["shift"].value_counts().to_dict(),
                    manual_key_rows=mk[["txn_id", "ts", "qty", "shift"]].head(15).to_dict("records"))

    def get_grn(self, location, sku, as_of=None):
        df = self.store.rows("grn", location, sku).sort_values("ts")
        out = []
        for r in df.itertuples():
            sup = self.store.supplier(r.supplier_id)
            short = int(r.invoiced_qty - r.received_qty)
            pct = round(100.0 * short / r.invoiced_qty, 2) if r.invoiced_qty else 0.0
            days = None
            if as_of is not None:
                days = (pd.Timestamp(as_of) - pd.Timestamp(r.ts).normalize()).days
            note = self.guard.sanitize(r.notes if isinstance(r.notes, str) else "", f"grn:{r.grn_id}.notes", self.flags)
            out.append(dict(ref=f"grn:{r.grn_id}", grn_id=r.grn_id, po_id=r.po_id, ts=str(r.ts),
                            supplier_id=r.supplier_id, invoiced_qty=int(r.invoiced_qty),
                            received_qty=int(r.received_qty), short_qty=short, short_pct=pct,
                            contract_tolerance_pct=sup["short_tolerance_pct"],
                            within_tolerance=pct <= sup["short_tolerance_pct"],
                            claim_window_days=sup["claim_window_days"], days_since_delivery=days,
                            within_claim_window=(days is None) or days <= sup["claim_window_days"],
                            discrepancy_flagged=r.discrepancy_flagged, notes=note))
        return out

    def get_returns(self, location, sku):
        df = self.store.rows("returns", location, sku).sort_values("ts")
        return [dict(ref=f"ret:{r.return_id}", return_id=r.return_id, ts=str(r.ts), qty=int(r.qty),
                     reason=r.reason, disposition=r.disposition, inventory_adjusted=r.inventory_adjusted,
                     writeoff_recorded=r.writeoff_recorded) for r in df.itertuples()][-12:]

    def get_wms_moves(self, location, sku):
        df = self.store.rows("wms_moves", location, sku).sort_values("ts")
        return [dict(ref=f"move:{r.move_id}", move_id=r.move_id, ts=str(r.ts), qty=int(r.qty),
                     from_bin=r.from_bin, to_bin=r.to_bin, move_type=r.move_type,
                     bin_confirmed=r.bin_confirmed,
                     notes=self.guard.sanitize(r.notes if isinstance(r.notes, str) else "", f"move:{r.move_id}.notes", self.flags))
                for r in df.itertuples()][-12:]

    def get_pick_exceptions(self, location, sku):
        df = self.store.rows("pick_exceptions", location, sku)
        return [dict(ref=f"pick:{r.pick_id}", pick_id=r.pick_id, ts=str(r.ts), bin=r.bin,
                     qty_requested=int(r.qty_requested), qty_found=int(r.qty_found), status=r.status)
                for r in df.itertuples()]

    def get_adjustments(self, location, sku):
        df = self.store.rows("adjustments", location, sku)
        return [dict(ref=f"adj:{r.adj_id}", adj_id=r.adj_id, ts=str(r.ts), qty_delta=int(r.qty_delta),
                     reason=r.reason) for r in df.itertuples()]

    def get_count_history(self, location, sku):
        df = self.store.rows("stock_counts", location, sku)
        out = []
        for d, g in df.groupby("count_date"):
            out.append(dict(ref=f"count:{d}:{location}:{sku}", count_date=d,
                            system_qty=int(g["system_qty"].sum()), counted_qty=int(g["counted_qty"].sum()),
                            variance=int((g["system_qty"] - g["counted_qty"]).sum()),
                            bins=[dict(bin=r.bin, system_qty=int(r.system_qty), counted_qty=int(r.counted_qty))
                                  for r in g.itertuples() if r.system_qty != r.counted_qty]))
        return out

    def find_offsetting_variances(self, location, sku):
        me = self.store.product(sku)
        v = self.variances.get((location, sku), 0)
        out = []
        for (loc, s), v2 in self.variances.items():
            if loc != location or s == sku or v == 0 or (v > 0) == (v2 > 0):
                continue
            p2 = self.store.product(s)
            if p2["category"] != me["category"]:
                continue
            if 0.75 * abs(v) <= abs(v2) <= 1.25 * abs(v):
                out.append(dict(ref=f"offset:{location}:{s}", sku=s, product=p2["name"], variance=v2,
                                price_ratio=round(p2["unit_price"] / me["unit_price"], 2),
                                manual_key_qty=self.get_pos_sales(location, s)["manual_key_qty"]))
        return out

    def get_cctv_findings(self, location, sku):
        """Phase 2. Empty (available=False) until CCTV events exist. Never contains people, only product events."""
        if self.settings is None:
            return dict(ref=f"cctv:{location}:{sku}", available=False, findings=[])
        from .cctv import load_findings
        df = load_findings(self.settings)
        df = df[(df["location"] == location) & (df["sku"] == sku)]
        return dict(ref=f"cctv:{location}:{sku}", available=not df.empty,
                    unbilled_pick_units=int(df.loc[df["type"] == "UNBILLED_PICK", "qty"].sum()),
                    misplaced_units=int(df.loc[df["type"] == "MISPLACED_ITEM", "qty"].sum()),
                    findings=df[["finding_id", "type", "qty", "event_ts", "confidence", "message"]].head(10)
                    .to_dict("records"))

    def search_policy(self, query):
        return [dict(ref=f"kb:{h['doc_id']}", title=h["title"], snippet=h["snippet"])
                for h in self.kb.search(query, 3)]

    def get_supplier_terms(self, supplier_id):
        s = self.store.supplier(supplier_id)
        s["ref"] = f"contract:{supplier_id}"
        return s

    # ---------- LLM tool dispatch (read-only allowlist)
    def call(self, name, args):
        allowed = {t["name"] for t in TOOL_SPECS}
        if name not in allowed:
            return {"error": f"tool '{name}' is not allowed for this agent"}
        try:
            return getattr(self, name)(**args)
        except TypeError as e:
            return {"error": f"bad arguments: {e}"}
        except Exception as e:
            return {"error": str(e)}

    # ---------- full pack for one case
    def collect(self, case):
        self.flags = []
        loc, sku, as_of = case["location"], case["sku"], case["count_date"]
        pack = dict(
            case={k: case[k] for k in ("case_id", "location", "sku", "product", "category", "net_variance",
                                       "direction", "bin_variances", "value_at_risk_inr", "count_date")},
            grn=self.get_grn(loc, sku, as_of), pos=self.get_pos_sales(loc, sku),
            returns=self.get_returns(loc, sku), wms_moves=self.get_wms_moves(loc, sku),
            pick_exceptions=self.get_pick_exceptions(loc, sku), adjustments=self.get_adjustments(loc, sku),
            count_history=self.get_count_history(loc, sku),
            offsetting=self.find_offsetting_variances(loc, sku), cctv=self.get_cctv_findings(loc, sku),
            supplier_terms=self.get_supplier_terms(case["supplier_id"]))
        short_rows = [g for g in pack["grn"] if g["short_qty"] > 0]
        findings = {
            "grn_shortfall": bool(short_rows), "manual_key_sales": pack["pos"]["manual_key_qty"] > 0,
            "returns_not_written_off": any(r["disposition"] == "discarded" and r["writeoff_recorded"] == "N"
                                           for r in pack["returns"]),
            "bin_issue": any(m["bin_confirmed"] == "N" for m in pack["wms_moves"]) or bool(pack["pick_exceptions"]),
            "cctv_unbilled_picks": pack["cctv"].get("unbilled_pick_units", 0) > 0,
            "offsetting_variance": bool(pack["offsetting"]), "recorded_adjustments": bool(pack["adjustments"]),
        }
        pack["sources_checked"] = ["grn", "pos", "returns", "wms_moves", "pick_exceptions", "adjustments",
                                   "count_history", "offsetting", "supplier_terms", "cctv"]
        pack["findings"] = findings
        pack["security_flags"] = list(self.flags)
        refs = set()

        def walk(o):
            if isinstance(o, dict):
                if "ref" in o:
                    refs.add(o["ref"])
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        walk(pack)
        pack["valid_refs"] = sorted(refs)
        return pack
