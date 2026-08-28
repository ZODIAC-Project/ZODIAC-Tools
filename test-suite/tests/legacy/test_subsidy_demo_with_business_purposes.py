import time
from .helper import STREAM_MANAGER_URL, AGENT_URL, create_agent, reserve_topic, client
import httpx
import pytest

pytestmark = pytest.mark.retain_agents

new_subsidy_topic = "zodiac/subsidy/new"
customer_proposal_topic = "zodiac/subsidy/customer/+/proposal"

DISCOVERY_AGENT_PURPOSE = "query"
DISCOVERY_RAG_PURPOSE = "Bayern"
ELIGIBILITY_PURPOSE = "subsidy/eligibility"
APPLICATION_PURPOSE = "subsidy/application"


def create_agent1():
    task_agent1 = f"""Use the tool search_knowledge_base with collection="subsidies" and purpose="{DISCOVERY_RAG_PURPOSE}".
                    Retrieve subsidy entries only from the "subsidies" collection.
                    Generate subsidy descriptions from those entries and use the publish tool to post each
                    description to the topic zodiac/subsidy/new.
                    Each description should contain:
                    - Criteria to get the subsidy
                    - Form and extent of the subsidy
                    - Purpose of the subsidy
                    - Any other relevant information useful for customers to evaluate whether the subsidy is interesting
                    Do not use the default collection and do not query foerderprogramme_export.
                    """
    agent1_id = create_agent(
        runOnce=False,
        text=task_agent1,
        purpose=DISCOVERY_AGENT_PURPOSE,
        memoryWindow=5,
        intervalMs=60000,
    )
    assert agent1_id is not None, "Failed to create Agent 1 for subsidy discovery."

    agents = httpx.get(f"{AGENT_URL}/agents", timeout=5.0).json()
    agent1_info = next((a for a in agents if a.get("id") == agent1_id), None)
    assert agent1_info is not None, f"Failed to retrieve info for Agent 1: {agent1_info}"
    assert agent1_info.get("intervalMs") == 60000, (
        f"Expected Agent 1 intervalMs to be 60000 but got {agent1_info.get('intervalMs')}"
    )
    assert agent1_info.get("purposes", []) == [DISCOVERY_AGENT_PURPOSE], (
        f"Expected Agent 1 to have only purpose '{DISCOVERY_AGENT_PURPOSE}' "
        f"but got {agent1_info.get('purposes')}"
    )
    return agent1_id


def create_agent2():
    task_agent2 = """Use the tool search_knowledge_base with collection="customers" and purpose="subsidy/eligibility".
    Retrieve the customer list only from the "customers" collection and create one sub-agent for each customer.
    Do not use the default collection and do not query foerderprogramme_export.
    Use the tool create_agent_and_subscribe to create sub-agents with the following properties:

    How to create a sub-agent ALL OF THE FOLLOWING POINTS MUST BE FULFILLED:
    1. Give each sub-agent its customer description as context.
    2. Each sub-agent must listen to the topic zodiac/subsidy/new.
    3. Give the Agents the following task as a quote: "You are {ALL AVAILABLE INFOS HERE}. Evaluate each incoming subsidy description
    against your customer description. If a subsidy fits and seems appropriate, publish a subsidy proposal to
    zodiac/subsidy/customer/<your-customer-id>/proposal. Dont spawn a sub-agent."
    4. The Purpose has to be "subsidy/eligibility" for creating all sub-agents.

    Give the sub-agent the 3 points as a quote and dont change anything to it
    """

    agent2_id = create_agent(
        runOnce=True,
        text=task_agent2,
        purpose=ELIGIBILITY_PURPOSE,
        memoryWindow=5,
        intervalMs=400,
    )
    assert agent2_id is not None, "Failed to create Agent 2 for subsidy eligibility."

    agents = httpx.get(f"{AGENT_URL}/agents", timeout=5.0).json()
    agent2_info = next((a for a in agents if a.get("id") == agent2_id), None)
    assert agent2_info is not None, f"Failed to retrieve info for Agent 2: {agent2_info}"
    assert ELIGIBILITY_PURPOSE in agent2_info.get("purposes", []), (
        f"Expected Agent 2 to have purpose '{ELIGIBILITY_PURPOSE}' but got {agent2_info.get('purposes')}"
    )
    return agent2_id


def create_agent3():
    task_agent3 = """Use the tool search_knowledge_base with collection="fundingPlan" and purpose="subsidy/application".
    For each incoming subsidy proposal, retrieve matching application guidance only from the "fundingPlan" collection.
    Use that information to evaluate if the proposal is actionable and, if so, send an email to the customer using the tool_send_email.
    Do not use the default collection and do not query foerderprogramme_export.
    """

    agent3_id = create_agent(
        runOnce=False,
        text=task_agent3,
        purpose=APPLICATION_PURPOSE,
        memoryWindow=5,
        listenTopic=customer_proposal_topic,
    )
    assert agent3_id is not None, "Failed to create Agent 3 for subsidy application."

    agents = httpx.get(f"{AGENT_URL}/agents", timeout=5.0).json()
    agent3_info = next((a for a in agents if a.get("id") == agent3_id), None)
    assert agent3_info is not None, f"Failed to find Agent 3 with id {agent3_id}"
    assert agent3_info.get("listenTopic") == customer_proposal_topic, (
        f"Expected Agent 3 to listen to {customer_proposal_topic} but got {agent3_info.get('listenTopic')}"
    )
    assert APPLICATION_PURPOSE in agent3_info.get("purposes", []), (
        f"Expected Agent 3 to have purpose '{APPLICATION_PURPOSE}' but got {agent3_info.get('purposes')}"
    )
    return agent3_id


def test_subsidy_demo_with_business_purposes():
    client.set_purpose_setting("filter_on_subscribe", False)
    client.set_purpose_setting("filter_on_publish", True)
    client.set_purpose_setting("filter_hybrid", False)

    reserve_topic(new_subsidy_topic, aip=[DISCOVERY_AGENT_PURPOSE, ELIGIBILITY_PURPOSE])
    reserve_topic(customer_proposal_topic, aip=[ELIGIBILITY_PURPOSE, APPLICATION_PURPOSE])

    agent3_id = create_agent3()
    agent2_id = create_agent2()
    time.sleep(10)
    agent1_id = create_agent1()

@pytest.fixture(autouse=True)
def cleanup_agents():
    yield
