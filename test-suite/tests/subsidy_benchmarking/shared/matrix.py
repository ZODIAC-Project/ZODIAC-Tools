import pytest

PBAC_MATRIX = [
    pytest.param(False, False, False, id="VBM-FFF"),
    pytest.param(True,  False, False, id="VBM-TFF"),
    pytest.param(False, True,  False, id="VBM-FTF"),
    pytest.param(False, False, True,  id="VBM-FFT"),
    pytest.param(True,  True,  False, id="VBM-TTF"),
    pytest.param(True,  False, True,  id="VBM-TFT"),
    pytest.param(False, True,  True,  id="VBM-FTT"),
    pytest.param(True,  True,  True,  id="VBM-TTT"),
]
