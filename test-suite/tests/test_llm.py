import re
from .helper import *

def test_simple_message():
    send("Hello, world!")

def test_simple_response():
    response = send("respond with the word 'lasagna'")
    assert "lasagna" in response.lower(), f"message should contain 'lasagna' but was '{response}'"

def test_random_number():
    response = send("generate a random number between 1 and 100. Don't use any tools for this")
    # response might contain additional text, so we need to extract the number
    numbers = re.findall(r'\d+', response)
    assert numbers, f"No numbers found in response: '{response}'"
    number = int(numbers[0])
    assert 1 <= number <= 100, f"Number {number} is not between 1 and 100 (response was: '{response}')"

def test_math():
    response = send("what is 452 * 3?")
    #remove commas or other formatting from the response (1,356 is still acceptable)
    response = response.replace(',', '').replace('.', '')
    numbers = re.findall(r'\d+', response)
    assert numbers, f"No numbers found in response: '{response}'"
    # first number might not be the answer, so we need to check all numbers in the response
    found_correct_answer = False
    for num_str in numbers:
        number = int(num_str)
        if number == 1356:
            found_correct_answer = True
            break
    assert found_correct_answer, f"Correct answer 1356 not found in response: '{response}'"