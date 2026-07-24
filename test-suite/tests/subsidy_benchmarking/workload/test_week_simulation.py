import pytest
import json, time
from ... import helper
from ..shared.instrumentation import RunCounters
from .data import WEEK_CUSTOMERS, WEEK_SUBSIDIES  

@pytest.mark.workload
def test_week_of_usage(topic_factory, purpose_factory, run_config):
    interval = run_config.get("event_interval_seconds", 2)
    n_events = run_config.get("n_events", len(WEEK_SUBSIDIES))
    counters = RunCounters()

    input_topic = topic_factory("input")
    purpose = purpose_factory("workload")
    helper.reserve_topic(input_topic, aip=[purpose])

    # fixed subagent count — NOT discovered dynamically from RAG
    for customer in WEEK_CUSTOMERS:
        helper.create_agent(
            runOnce=False,
            text=f"... vergleiche eingehende Subsidies mit: {customer['text']}",
            purpose=purpose, memoryWindow=5, listenTopic=input_topic,
        )

    for subsidy in WEEK_SUBSIDIES[:n_events]:
        helper.send_and_expect(input_topic, json.dumps(subsidy), purposes=[purpose])
        counters.record_sent()
        time.sleep(interval)

    print(f"WORKLOAD_COUNTERS::{json.dumps(counters.as_dict())}")  # sma can grep this from captured output
    assert counters.messages_sent == n_events, "Nicht alle geplanten Events wurden gesendet"