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
    
