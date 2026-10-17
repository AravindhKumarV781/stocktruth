"""Platform + business guardrails.

Platform: Azure AI Content Safety Prompt Shields (document attack detection) when configured,
          always combined with a local pattern check so the demo never depends on one service.
Business: policy-driven routing lives in orchestrator.route_case(); output grounding checks live here.
"""
import json
import re

import requests

INJECTION_RE = re.compile(
    r"(ignore\s+(all\s+)?(the\s+)?(previous|prior|above)\s+instructions"
    r"|disregard\s+.{0,40}(rules|instructions|policy)"
    r"|you\s+are\s+now\s+(in\s+)?(admin|developer|root)"
    r"|admin\s+mode|system\s+prompt"
    r"|approve\s+(every|all|any)\s+.{0,25}(claim|case|request)"
    r"|skip\s+(the\s+)?(manager\s+|human\s+)?review)", re.I)

REDACTED = "[REDACTED: possible prompt injection detected in source document]"
CAUSES = ["SHORT_DELIVERY", "SCAN_ERROR", "RETURN_NOT_WRITTEN_OFF", "MISSLOTTED",
          "SUSPECTED_LOSS", "MINOR_COUNT_VARIANCE", "UNKNOWN"]


class Guard:
    def __init__(self, settings):
        self.s = settings
        self.shield_errors = 0

    def scan_document(self, text):
        """Return dict(attack, engine). Never raises."""
        if not text or not str(text).strip():
            return dict(attack=False, engine="none")
        text = str(text)
        local = bool(INJECTION_RE.search(text))
        shield = None
        if self.s.cs_endpoint and self.s.cs_key:
            try:
                url = self.s.cs_endpoint.rstrip("/") + "/contentsafety/text:shieldPrompt?api-version=2024-09-01"
                r = requests.post(url, headers={"Ocp-Apim-Subscription-Key": self.s.cs_key,
                                                "Content-Type": "application/json"},
                                  json={"userPrompt": "Review this stock case.", "documents": [text[:9000]]},
                                  timeout=15)
                r.raise_for_status()
                shield = bool(r.json()["documentsAnalysis"][0]["attackDetected"])
            except Exception:
                self.shield_errors += 1
        engine = "prompt_shields+local" if shield is not None else "local_patterns"
        return dict(attack=bool(local or shield), engine=engine, shield=shield, local=local)

    def sanitize(self, text, where, flags):
        """Scan third-party free text. If it holds an attack, redact it and record a flag."""
        res = self.scan_document(text)
        if res["attack"]:
            flags.append(dict(where=where, engine=res["engine"], excerpt=str(text)[:80] + "..."))
            return REDACTED
        return text


def extract_json(text):
    if text is None:
        raise ValueError("empty model output")
    t = text.strip()
    t = re.sub(r"^```(?:json)?|```$", "", t, flags=re.M).strip()
    a, b = t.find("{"), t.rfind("}")
    if a < 0 or b < 0:
        raise ValueError("no JSON object in model output")
    return json.loads(t[a:b + 1])


def validate_root_cause(rc, valid_refs):
    """Schema + grounding checks. Returns (clean_rc, problems)."""
    problems = []
    cause = str(rc.get("cause", "")).upper().strip()
    if cause not in CAUSES:
        problems.append(f"invalid cause '{cause}'")
        cause = "UNKNOWN"
    try:
        conf = float(rc.get("confidence", 0))
    except Exception:
        conf = 0.0
        problems.append("confidence not numeric")
    conf = max(0.0, min(1.0, conf))
    refs = [r for r in (rc.get("evidence_refs") or []) if r in valid_refs]
    dropped = [r for r in (rc.get("evidence_refs") or []) if r not in valid_refs]
    if dropped:
        problems.append(f"dropped {len(dropped)} evidence refs that do not exist")
    clean = dict(cause=cause, confidence=round(conf, 2), reasoning=str(rc.get("reasoning", ""))[:600],
                 evidence_refs=refs, alternatives=rc.get("alternatives") or [],
                 citations=[c for c in (rc.get("citations") or []) if isinstance(c, str)][:6])
    return clean, problems
