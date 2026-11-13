"""Constants the tool tests share. Pytest puts this directory on sys.path (`pythonpath`).

Facts come from the recorded companyfacts fixtures of Apple and NVIDIA. Every company,
filing and sentence named SIM... is simulated, made up for a test, never real data.
"""

FACTS_VERSION = "x-test"
APPLE_CIK = 320193
NVIDIA_CIK = 1045810
SIM_CIK = 9999999999
