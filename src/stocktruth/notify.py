"""Teams notification via a Workflows (Power Automate) webhook that posts an Adaptive Card."""
import requests


def build_card(case, app_url):
    facts = [
        {"title": "Store / SKU", "value": f"{case['location']} / {case['sku']} ({case['product']})"},
        {"title": "Variance", "value": f"{case['net_variance']} units, INR {case['value_at_risk_inr']:,.0f} at risk"},
        {"title": "Likely cause", "value": f"{case['cause']} (confidence {case['confidence']})"},
        {"title": "Route", "value": f"{case['route']}: {'; '.join(case['route_reasons'])}"},
    ]
    if case.get("security_flags"):
        facts.append({"title": "Security", "value": "Injected instructions found in a source document and ignored"})
    return {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard", "version": "1.4",
                "body": [
                    {"type": "TextBlock", "size": "Medium", "weight": "Bolder",
                     "text": f"StockTruth: {case['case_id']} needs your decision"},
                    {"type": "TextBlock", "wrap": True, "text": case["reasoning"][:400]},
                    {"type": "FactSet", "facts": facts},
                ],
                **({"actions": [{"type": "Action.OpenUrl", "title": "Review evidence and approve",
                                 "url": f"{app_url.rstrip('/')}/?case={case['case_id']}"}]} if app_url else {}),
            }}],
    }


def send_teams(settings, case):
    if not settings.teams_webhook:
        return "skipped (TEAMS_WEBHOOK_URL not set)"
    try:
        r = requests.post(settings.teams_webhook, json=build_card(case, settings.app_url), timeout=15)
        return f"sent ({r.status_code})"
    except Exception as e:
        return f"failed ({e})"
