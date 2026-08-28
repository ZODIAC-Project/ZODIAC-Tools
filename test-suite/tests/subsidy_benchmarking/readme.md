# Subsidy benchmark/testing setup [WIP]
## 1. What works at the moment 
- logic tests (/logic)
- purpose routing tests (/purpose_routing)
- parts of the purpose isolation tests (/purpose_isolation)

## 2. What am I still working on
> Momentan funktioniert bei den purpose isolation tests nur der test case bei dem keine faults injected werden. Heißt wenn man den test mit folgendem command startet läuft das scenario durch und es werden alle PBAC layers genutzt. Entweder man startet den Test mit dem unten gezeigten command mehrmals hintereinander oder man erhöht den parameter --amount-messages. Das kommt einem mehrmaligen Testen gleich.

```
uv run pytest tests/subsidy_benchmarking/purpose_isolation/test_workload.py -vv -s --broker-enabled --mcp-enabled --vector-enabled --amount-messages=1 --randomness=False
```
## What are the tests testing? What is the motivation behind the tests?
### logic tests: 
 We are testing the capabilities of the llm/agents to function in our subsidy based scenario. These tests are all llm based and therfore not deterministic - some can always fail and is does not mean that the test is faulty. It can be used as an idicator of how good the llm will performe in the other tests that represent bigger example scenarios. 

### purpose routing tests:
 We are demonstrating the ability of our system to rout messaged using the broker based PBAC. One test is showing it in the simplest form using two agents and the other test can be configured to spawn n amount of agents. In the test we expect the Agents to be able to respond to the message by sending a response.

### purpose isolation tests:
**test_workload.py:**
 At the moment we are starting a example system where two agents use every layer of the PBAC in an example scenario. One agents gets a request message with a subsidy and then uses rag to match a customer to the subsidy. This matching couple is send to the second agents wich formats the couple and sends a mock email. This can be used to get a sense about the ability of the llm and the routing in our system. It can also be used to generate workload for a longer period of time. 
**test_components.py:**
 This test was originally made to test the on/off functionality of each PBAC layer (For making it simpler to construct the workload test). But it can also be used as a normal test. 

## How to run the tests 
**logic tests:** 
```
uv run pytest tests/subsidy_benchmarking/logic/ -vv -s
```
**purpose routing tests:**
```
uv run pytest tests/subsidy_benchmarking/purpose_routing/test_purpose_routing/test_reduced.py -vv -s
uv run pytest tests/subsidy_benchmarking/purpose_routing/test_n_agent.py -vv -s --n-agents=5
```
**purpose isolation tests - test_workload.py:**
```
uv run pytest tests/subsidy_benchmarking/purpose_isolation/test_workload.py -vv -s --broker-enabled --mcp-enabled --vector-enabled --amount-messages=2 --randomness=False
```
**purpose isolation tests - test_components.py:**
```
uv run pytest tests/subsidy_benchmarking/purpose_isolation/test_components.py -vv -s 
```