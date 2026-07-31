import time
import httpx
import pytest
from tests.helper import *

new_subsidy_topic = "zodiac/subsidy/new"
customer_proposal_topic = "zodiac/subsidy/customer/+/proposal"
PURPOSE = "admin"

pytestmark = pytest.mark.retain_agents

# --- Setup logic that runs only ONCE ---

@pytest.fixture(scope="module", autouse=True)
def initial_setup():
    """Performs global configuration and topic reservation once per module."""
    client.set_purpose_setting("filter_on_subscribe", False)
    client.set_purpose_setting("filter_on_publish", True)
    client.set_purpose_setting("filter_hybrid", False)
    
    reserve_topic(new_subsidy_topic, aip=[PURPOSE])
    reserve_topic(customer_proposal_topic, aip=[PURPOSE])

# --- Helper Functions (Logic Unchanged) ---

def create_agent1():
    task_agent1 = """Use the tool search_knowledge_base with collection="subsidies" and purpose="admin".
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
        purpose=PURPOSE,
        memoryWindow=5,
        intervalMs=60000,
    )
    assert agent1_id is not None, "Failed to create Agent 1."

    agents = httpx.get(f"{AGENT_URL}/agents", timeout=5.0).json()
    agent1_info = next((a for a in agents if a.get("id") == agent1_id), None)
    assert agent1_info is not None
    assert agent1_info.get("intervalMs") == 60000
    assert PURPOSE in agent1_info.get("purposes", [])
    return agent1_id


def create_agent2():
    task_agent2 = """Use the tool search_knowledge_base with collection="customers" and purpose="admin".
    Retrieve the customer list only from the "customers" collection and create one sub-agent for each customer.  
    Do not use the default collection and do not query foerderprogramme_export.
    Use the tool spawn_agent to create sub-agents with the following properties:
    
    How to create a sub-agent ALL OF THE FOLLOWING POINTS MUST BE FULFILLED: 
    1. Give each sub-agent its customer description as context, passed via the "text" parameter when calling spawn_agent.
    2. Each sub-agent must listen to the topic zodiac/subsidy/new. 
    3. Give the Agents the following task as a quote: "You are {ALL AVAILABLE INFOS HERE}. Evaluate each incoming subsidy description
    against your customer description. If a subsidy fits and seems appropriate, publish a subsidy proposal to
    zodiac/subsidy/customer/<your-customer-id-cant-include-slashes>/proposal. Dont spawn a sub-agent."
    4. The Purpose has to be "admin" for creating all sub-agents. 
    
    Give the sub-agent the 3 points as a quote and dont change anything to it 
    """

    agent2_id = create_agent(
        runOnce=False,
        text=task_agent2,
        purpose=PURPOSE,
        memoryWindow=5,
        intervalMs=6000000,
    )
    assert agent2_id is not None, "Failed to create Agent 2."

    agents = httpx.get(f"{AGENT_URL}/agents", timeout=5.0).json()
    agent2_info = next((a for a in agents if a.get("id") == agent2_id), None)
    assert agent2_info is not None


def create_agent3():
    task_agent3 = """I am an agent that listens to subsidy proposals and evaluates if they are good. 
    If they are good, I send an email to the customer using the tool_send_email to the email . (Use a mock email adress for now.)"""

    agent3_id = create_agent(
        runOnce=False,
        text=task_agent3,
        purpose=PURPOSE,
        memoryWindow=5,
        listenTopic=customer_proposal_topic,
    )
    assert agent3_id is not None, "Failed to create Agent 3."

    agents = httpx.get(f"{AGENT_URL}/agents", timeout=5.0).json()
    agent3_info = next((a for a in agents if a.get("id") == agent3_id), None)
    assert agent3_info is not None
    assert agent3_info.get("listenTopic") == customer_proposal_topic
    assert PURPOSE in agent3_info.get("purposes", [])
    return agent3_id

# --- Independent Test Functions ---

def test_step_1():
    """Triggers the creation of Agent 3."""
    create_agent3()

def test_step_2():
    """Triggers the creation of Agent 2."""
    create_agent2()

def test_step_3():
    """Triggers the creation of Agent 1 after the original 10s delay."""
    create_agent1()

@pytest.fixture(autouse=True)
def cleanup_agents():
    yield