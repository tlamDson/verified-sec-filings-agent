# Recorded companyfacts fixtures

Real SEC data, not simulated. Recorded on 2026-11-13 from
`https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json` through `EdgarClient`
(rate-limited, `SEC_USER_AGENT`), then trimmed so the files stay small:

- only `us-gaap` tags that appear in `sec_agent.xbrl.concepts`, and no `description` text;
- only entries whose period `end` falls in these windows (inclusive):

| File                  | Company     | Windows of `end`                                  | Why                                                                           |
| --------------------- | ----------- | ------------------------------------------------- | ----------------------------------------------------------------------------- |
| `CIK0001045810.json` | NVIDIA      | 2012-01-29..2015-01-25, 2022-01-30..2025-01-26    | fiscal year ends in January (E1); the FY2014 10-K says `fy` 2013; 2024 split |
| `CIK0000320193.json` | Apple       | 2007-09-29..2010-09-25, 2022-09-24..2024-09-28    | 10-K/A of January 2010 restated FY2008 and FY2009 (E2); 53-week FY2023       |

Entries are otherwise unchanged. Tests read these files; they never call SEC.
