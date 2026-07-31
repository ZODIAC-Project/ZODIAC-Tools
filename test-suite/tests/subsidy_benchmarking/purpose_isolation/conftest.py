from pathlib import Path

import yaml

from ..shared.matrix import PBAC_MATRIX


# pytest Subsidy_tests/purpose_isolation --run-config=cell_VBM-TTT.yaml --junitxml=results/VBM-TTT.xml
def _filter_matrix_by_config(config: dict):
    """Filters PBAC_MATRIX down to the cell IDs listed in run_config['matrix_cells'].
    Returns the full matrix if no filter is specified."""
    requested = config.get("matrix_cells") if config else None
    if not requested:
        return PBAC_MATRIX
    selected = [p for p in PBAC_MATRIX if p.id in requested]
    unknown = set(requested) - {p.id for p in PBAC_MATRIX}
    if unknown:
        raise ValueError(f"Unknown matrix_cells in run_config: {unknown}")
    return selected


def pytest_generate_tests(metafunc):
    if {"vector_on", "broker_on", "mcp_on"} <= set(metafunc.fixturenames):
        path = metafunc.config.getoption("run_config", default=None)
        config = yaml.safe_load(Path(path).read_text()) if path else {}
        metafunc.parametrize("vector_on,broker_on,mcp_on", _filter_matrix_by_config(config))