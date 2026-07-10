import time

import httpx
import pytest

from .helper import AGENT_URL, create_agent, reserve_topic, client

new_subsidy_topic = "zodiac/subsidy/new"
customer_proposal_topic = "zodiac/subsidy/customer/+/proposal"

DISCOVERY_PURPOSE = "admin"
ELIGIBILITY_PURPOSE = "subsidy/eligibility"
APPLICATION_PURPOSE = "subsidy/application"


def create_agent1():
    task_agent1 = """Use the tool search_knowledge_base with collection="subsidy" and purpose="admin".
                    Retrieve subsidy entries only from the "subsidy" collection.
                    This explicitly refers to the dataset from RAGService/data/d0cdd7.subsidy.json.
                    Do not search the collection "subsidies".
                    For each promising subsidy, also use the tool search_knowledge_base with collection="subsidyDetails"
                    and purpose="subsidy/discovery" to enrich the result with additional detailed funding information.
                    The collection "subsidyDetails" explicitly refers to RAGService/data/d0cdd7.subsidyDetails.json.
                    Generate subsidy descriptions from those entries and use the publish tool to post each
                    description to the topic zodiac/subsidy/new.
                    Each description should contain:
                    - Criteria to get the subsidy
                    - Form and extent of the subsidy
                    - Purpose of the subsidy
                    - Important detailed funding information if available
                    - Any other relevant information useful for customers to evaluate whether the subsidy is interesting
                    Do not use the default collection, do not query foerderprogramme_export, and do not query subsidies.
                    """
    agent1_id = create_agent(
        runOnce=False,
        text=task_agent1,
        purpose=DISCOVERY_PURPOSE,
        memoryWindow=5,
        intervalMs=60000,
    )
    assert agent1_id is not None, "Failed to create Agent 1 for extended subsidy discovery."

    agents = httpx.get(f"{AGENT_URL}/agents", timeout=5.0).json()
    agent1_info = next((a for a in agents if a.get("id") == agent1_id), None)
    assert agent1_info is not None, f"Failed to retrieve info for Agent 1: {agent1_info}"
    assert agent1_info.get("intervalMs") == 60000, (
        f"Expected Agent 1 intervalMs to be 60000 but got {agent1_info.get('intervalMs')}"
    )
    assert DISCOVERY_PURPOSE in agent1_info.get("purposes", []), (
        f"Expected Agent 1 to have purpose '{DISCOVERY_PURPOSE}' but got {agent1_info.get('purposes')}"
    )
    return agent1_id


def create_agent2():
    task_agent2 = """Use the tool search_knowledge_base with purpose="subsidy/eligibility" and the following collections:
    - collection="clientRole" to retrieve the customer list and customer role information from RAGService/data/d0cdd7.clientRole.json
    - collection="companySize" to interpret company size information from RAGService/data/d0cdd7.companySize.json
    - collection="businessSector" to interpret business sector information from RAGService/data/d0cdd7.businessSector.json
    - collection="legalEntity" to interpret legal entity information from RAGService/data/d0cdd7.legalEntity.json
    - collection="location" to interpret location information from RAGService/data/d0cdd7.location.json
    - collection="state" to interpret state information from RAGService/data/d0cdd7.state.json
    - collection="district" to interpret district information from RAGService/data/d0cdd7.district.json
    - collection="cityLocation" to interpret city location information from RAGService/data/d0cdd7.cityLocation.json

    Retrieve the customer list only from the "clientRole" collection and use the other collections only as lookup and interpretation context.
    Use "clientRole" as the customer database.
    Do not use the default collection, do not query foerderprogramme_export, do not query the "customers" collection, and do not query the "subsidies" collection.
    Use the tool create_agent_and_subscribe to create one sub-agent for each customer with the following properties:

    How to create a sub-agent ALL OF THE FOLLOWING POINTS MUST BE FULFILLED:
    1. Treat each relevant entry from the "clientRole" collection as a customer profile.
    2. Give each sub-agent its customer description as context.
    3. Add the interpreted context from the collections companySize, businessSector, legalEntity, location, state, district and cityLocation.
    4. Each sub-agent must listen to the topic zodiac/subsidy/new.
    5. Give the Agents the following task as a quote: "You are {ALL AVAILABLE INFOS HERE}. Evaluate each incoming subsidy description
    against your customer description. If a subsidy fits and seems appropriate, publish a subsidy proposal to
    zodiac/subsidy/customer/<your-customer-id>/proposal. Dont spawn a sub-agent."
    6. The Purpose has to be "subsidy/eligibility" for creating all sub-agents.

    The collection "clientRole" must be used as the customer source. The collection "customers" must not be used.
    Give the sub-agent the quoted task unchanged.
    """

    agent2_id = create_agent(
        runOnce=True,
        text=task_agent2,
        purpose=ELIGIBILITY_PURPOSE,
        memoryWindow=5,
        intervalMs=400,
    )
    assert agent2_id is not None, "Failed to create Agent 2 for extended subsidy eligibility."

    agents = httpx.get(f"{AGENT_URL}/agents", timeout=5.0).json()
    agent2_info = next((a for a in agents if a.get("id") == agent2_id), None)
    assert agent2_info is not None, f"Failed to retrieve info for Agent 2: {agent2_info}"
    assert ELIGIBILITY_PURPOSE in agent2_info.get("purposes", []), (
        f"Expected Agent 2 to have purpose '{ELIGIBILITY_PURPOSE}' but got {agent2_info.get('purposes')}"
    )
    return agent2_id


def create_agent3():
    task_agent3 = """Use the tool search_knowledge_base with purpose="subsidy/application" and the following collections:
    - collection="fundingPlan" to retrieve application guidance from RAGService/data/d0cdd7.fundingPlan.json
    - collection="subsidyDetails" to retrieve additional detailed subsidy information from RAGService/data/d0cdd7.subsidyDetails.json when needed

    For each incoming subsidy proposal, retrieve matching application guidance only from the "fundingPlan" collection.
    If useful, enrich the evaluation with additional details from the "subsidyDetails" collection.
    Use that information to evaluate if the proposal is actionable and, if so, send an email to the customer using the tool_send_email.
    Do not use the default collection, do not query foerderprogramme_export, do not query the "subsidies" collection, and do not query the "customers" collection.
    """

    agent3_id = create_agent(
        runOnce=False,
        text=task_agent3,
        purpose=APPLICATION_PURPOSE,
        memoryWindow=5,
        listenTopic=customer_proposal_topic,
    )
    assert agent3_id is not None, "Failed to create Agent 3 for extended subsidy application."

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


def test_subsidy_demo_with_extended_rag_collections():
    client.set_purpose_setting("filter_on_subscribe", False)
    client.set_purpose_setting("filter_on_publish", True)
    client.set_purpose_setting("filter_hybrid", False)

    reserve_topic(new_subsidy_topic, aip=[DISCOVERY_PURPOSE, ELIGIBILITY_PURPOSE])
    reserve_topic(customer_proposal_topic, aip=[ELIGIBILITY_PURPOSE, APPLICATION_PURPOSE])

    create_agent3()
    create_agent2()
    time.sleep(10)
    create_agent1()


@pytest.fixture(autouse=True)
def cleanup_agents():
    yield
