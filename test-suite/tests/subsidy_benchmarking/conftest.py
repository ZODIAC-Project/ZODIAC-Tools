from email import parser
from pathlib import Path
import pytest
import uuid
from .. import helper
import yaml

@pytest.fixture
def run_id():
    """
    Random 8-char string, unique per test run. Prevents
    topic/purpose collisions between test runs (e.g. from retained MQTT
    messages left over from a previous run).
    """
    return uuid.uuid4().hex[:8]

@pytest.fixture
def topic_factory(run_id):
    """
    Builds a unique topic string, e.g.
    topic_factory("input") → zodiac/test/<run_id>/input.
    
    :param run_id: Unique string for this test run, provided by the `run_id` fixture.
    :return: A function that takes a name and returns a unique topic string.
    """
    def _make(name: str) -> str:
        return f"zodiac/test/{run_id}/{name}"
    return _make

@pytest.fixture
def purpose_factory(run_id):
    """
    Builds a unique purpose string per call, e.g.
    purpose_factory("allowed") → p-<run_id>-1-allowed.
    
    :param run_id: Unique string for this test run, provided by the `run_id` fixture.
    :return: A function that takes a label and returns a unique purpose string.
    """
    counter = {"n": 0}
    def _make(label: str = "") -> str:
        counter["n"] += 1
        return f"p-{run_id}-{counter['n']}-{label}"
    return _make

@pytest.fixture(autouse=True)
def cleanup_agents():
    yield
    helper.delete_all_agents()

@pytest.fixture(scope="session")
def run_config(pytestconfig):
    """
    Loads a YAML file passed via --run-config=path.yaml
    on the command line, for externally-driven runs. 
    Returns {} if no file is given, so tests
    still run locally with sensible defaults.
    
    :param pytestconfig: Description
    :return: Dictionary of run-specific parameters from the YAML file or {} if no file is given.
    """
    path = pytestconfig.getoption("run_config")
    if not path:
        return {}
    data = yaml.safe_load(Path(path).read_text())
    return data or {}


@pytest.fixture(scope="session")
def scale_pairs(pytestconfig):
    """Number of customer/subsidy pairs for the scale benchmark test."""
    return pytestconfig.getoption("scale_pairs")

@pytest.fixture(autouse=True)
def configure_purpose_filtering(mqtt_client):
    """Configure the fresh MQTT connection used by this benchmark test."""
    mqtt_client.set_purpose_setting("filter_on_subscribe", False)
    mqtt_client.set_purpose_setting("filter_on_publish", True)
    mqtt_client.set_purpose_setting("filter_hybrid", False)


def pytest_addoption(parser):
    parser.addoption(
        "--n-agents",
        action="store",
        type=int,
        default=None,
        help="Number of agents for purpose-routing tests",
    )
    parser.addoption(
        "--scale-pairs",
        action="store",
        type=int,
        default=15,
        help="Number of customer/subsidy pairs for the scale benchmark test",
    )
    
