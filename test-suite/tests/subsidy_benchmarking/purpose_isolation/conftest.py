from ..shared.matrix import PBAC_MATRIX


# pytest Subsidy_tests/purpose_isolation --run-config=cell_VBM-TTT.yaml --junitxml=results/VBM-TTT.xml
def pytest_generate_tests(metafunc):
    if {"vector_on", "broker_on", "mcp_on"} <= set(metafunc.fixturenames):
        cell_id = metafunc.config.getoption("run_config")
        selected = _filter_matrix_by_config(cell_id)  # reads YAML "matrix_cells", defaults to all 8
        metafunc.parametrize("vector_on,broker_on,mcp_on", selected)