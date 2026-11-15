"""Simulated users: 50 test accounts that use the deployed app the way people would.

Every account is `sim-NN@example.com`, signs in with the app's simulated credentials
provider and is in the `simulated` cohort from the token to the tables to `runs.csv`. A
seeded driver plays each account's persona inside a daily budget of at most half the LLM
quota. Simulated traffic measures the system (latency, quota, degraded mode, errors); its
ratings only prove the feedback path works and are never a quality measure.
"""
