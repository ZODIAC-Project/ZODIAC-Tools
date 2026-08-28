import json
from logging import exception
import pytest
from ... import helper
from ..shared.prompts import build_matching_task
from ..shared.parsing import parse_match_response, matches_to_dict
from .data import build_scale_dataset

@pytest.mark.model_quality
def test_agent_matches_at_scale(topic_factory, purpose_factory, run_config):
    
    #TODO: REMOVE this 
    try:
        n_pairs = run_config.get("scale_pairs", 15)
    except Exception as e:
        print(f"Error reading run_config: {e}. Defaulting to 10 pairs.")
        n_pairs = 10
        
    customers, subsidies, expected = build_scale_dataset(n_pairs)
    input_topic = topic_factory("input")
    result_topic = topic_factory("matches")
    purpose = purpose_factory("logic")

    helper.reserve_topic(input_topic, aip=[purpose])
    helper.create_agent(
        runOnce=True,
        text=build_matching_task(result_topic),
        purpose=purpose, memoryWindow=5, listenTopic=input_topic,
    )

    payload = json.dumps({"customers": customers, "subsidies": subsidies})
    helper.publish_message(input_topic, payload)

    raw = helper.listen_to_a_mqtt_topic(result_topic, timeout=120)  # longer: more tokens to generate
    actual = matches_to_dict(parse_match_response(raw))

    missing = set(expected) - set(actual)
    extra = set(actual) - set(expected)
    assert not missing, f"Fehlende Customer im Ergebnis: {missing}"
    assert not extra, f"Unerwartete Customer im Ergebnis: {extra}"

    mismatches = {c: (actual[c], expected[c]) for c in expected if actual[c] != expected[c]}
    assert not mismatches, f"Falsche Zuordnungen: {mismatches}"