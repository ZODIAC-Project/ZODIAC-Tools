import json

def parse_match_response(raw: str | None) -> list[dict]:
    assert raw is not None, "Agent hat kein Ergebnis veröffentlicht"
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        assert False, f"Agent-Antwort war kein valides JSON: {raw!r}"
    assert isinstance(data, list), f"Erwartete JSON-Liste, bekam: {data!r}"
    return data

def matches_to_dict(matches: list[dict]) -> dict[str, str]:
    return {m["customer_id"]: m["subsidy_id"] for m in matches}