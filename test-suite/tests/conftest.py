import pytest
from . import helper

def _retain_agents(request):
    return request.node.get_closest_marker("retain_agents") is not None


@pytest.fixture(autouse=True)
def cleanup_agents(request):
    """Autouse fixture that deletes agents after each test unless test is marked to retain them."""
    yield
    if _retain_agents(request):
        return
    try:
        helper.delete_all_agents()
    except Exception:
        # don't fail tests because cleanup failed
        pass
    
def pytest_addoption(parser):
    parser.addoption(
        "--run-config", action="store", default=None,
        help="Path to YAML file with run-specific test parameters",
    )
    parser.addoption(
        "--broker-enabled", action="store_true", default=False,
        help="Enable broker purpose filtering for workload tests",
    )
    parser.addoption(
        "--mcp-enabled", action="store_true", default=False,
        help="Enable MCP purpose filtering for workload tests",
    )
    parser.addoption(
        "--vector-enabled", action="store_true", default=False,
        help="Enable vector purpose filtering for workload tests",
    )
    parser.addoption(
        "--amount-messages", action="store", type=int, default=1,
        help="Number of messages to simulate in workload tests",
    )
    parser.addoption(
        "--randomness", action="store", default="False",
        help="Whether to inject random faults in the workload scenario. Use True/False.",
    )
    
