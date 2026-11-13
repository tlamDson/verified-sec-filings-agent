# Recorded companyfacts fixtures

Real SEC data, not simulated. Recorded on 2026-11-13 from
`https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json` through `EdgarClient`
(rate-limited, `SEC_USER_AGENT`), then trimmed so the files stay small:

- only `us-gaap` tags that appear in `sec_agent.xbrl.concepts`, and no `description` text;
- only entries from filings whose `filed` date falls in these windows (inclusive), so every
  kept filing is complete (its own period and its comparatives):

| File                 | Company | Windows of `filed`                             | Why                                                                     |
| -------------------- | ------- | ---------------------------------------------- | ----------------------------------------------------------------------- |
| `CIK0001045810.json` | NVIDIA  | 2013-01-01..2016-04-30, 2022-02-01..2026-03-31 | fiscal year ends in January (E1); `fy` one year low until FY2014; split |
| `CIK0000320193.json` | Apple   | 2009-07-01..2011-10-31, 2022-10-01..2025-11-30 | 10-K/A of January 2010 restated FY2008 and FY2009 (E2); 53-week FY2023  |

Entries are otherwise unchanged. Tests read these files; they never call SEC.
