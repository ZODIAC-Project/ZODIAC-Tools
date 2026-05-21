import pytest
from helper import *

def test_simple_fuzzy_assert():
    response = send("how do I center a div in CSS?")
    fuzzy_assert(response, "The message should provide instructions on centering a div in CSS.")

def test_fuzzy_assert_expected_failure():
    response = send("how do I center a div in CSS?")
    with pytest.raises(AssertionError):
        fuzzy_assert(response, "The message should provide instructions on how to bake a cake.")