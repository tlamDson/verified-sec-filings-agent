"""Deterministic tools: every number an answer shows comes from one of these, never the model.

`get_fact`, `compute_ratio` and `compare_peers` read XBRL facts (`sec_agent.xbrl`);
`search_filings` and `diff_risk_factors` read filing text (`sec_agent.filings`,
`sec_agent.retrieval`). `catalog` lists them with their argument and result schemas.
"""
