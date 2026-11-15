---
title: sec-agent API
emoji: 📄
colorFrom: gray
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
short_description: API of the Verified SEC Filings Research Agent
---

# sec-agent API

The HTTP API of the Verified SEC Filings Research Agent, deployed from GitHub by
`.github/workflows/deploy-api.yml`. Do not edit this Space by hand: every deploy replaces
its files.

- `GET /healthz`: liveness.
- `GET /v1/me`, `POST /v1/chat`, `POST /v1/feedback`: called only by the web app, with a
  token signed with `API_AUTH_SECRET`.

Not investment advice: answers show historical numbers from public SEC filings.
