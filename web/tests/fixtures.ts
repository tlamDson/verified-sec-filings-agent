// What the API sends, as the tests use it. The Apple and NVIDIA figures are the ones the
// Python tools return from the recorded SEC companyfacts fixtures. The passage, the answer
// texts and the users are SIMULATED: made up for tests, never real filing text or people.

import type {
  AnswerEvent,
  Chart,
  ChatEvent,
  Citation,
  FactCard,
  NoticeCard,
  PeersCard,
  RatioCard,
  RiskDiffCard,
  Usage,
} from "@/lib/chat/types";

export const THREAD = "thread-0001";
export const APPLE = { ticker: "AAPL", name: "Apple Inc." };
export const NVIDIA = { ticker: "NVDA", name: "Nvidia" };
export const APPLE_10K = {
  accession: "0000320193-25-000079",
  form: "10-K",
  filed: "2025-10-31",
  url: "https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/0000320193-25-000079-index.htm",
};
export const PASSAGE_KEY = "9999999999-25-000008/mdna/0";

export const usage: Usage = { used: 1, limit: 20, resets_at: "2026-11-14T00:00:00Z" };

export const revenue: FactCard = {
  kind: "fact",
  call_id: "c1",
  company: APPLE,
  concept: "revenue",
  label: "Revenue",
  unit: "USD",
  fiscal_year: 2024,
  fiscal_period: "FY",
  status: "found",
  value: "391035000000",
  period_start: "2023-10-01",
  period_end: "2024-09-28",
  source: APPLE_10K,
  restated: false,
  original_value: "391035000000",
  original_filed: "2024-11-01",
};

export const restated: FactCard = {
  ...revenue,
  call_id: "c7",
  company: { ticker: "SIMW", name: "SIM Widgets Inc." },
  value: "1250000000",
  source: { ...APPLE_10K, accession: "9999999999-25-000011", form: "10-K/A", filed: "2025-06-02" },
  restated: true,
  original_value: "1200000000",
  original_filed: "2025-02-20",
};

export const notReported: FactCard = {
  ...revenue,
  call_id: "c8",
  fiscal_year: 2019,
  status: "not_reported",
  value: null,
  period_start: null,
  period_end: null,
  source: null,
  original_value: null,
  original_filed: null,
};

export const grossMargin: RatioCard = {
  kind: "ratio",
  call_id: "c2",
  company: APPLE,
  ratio: "gross_margin",
  label: "Gross margin",
  formula: "gross_profit / revenue * 100",
  unit: "percent",
  fiscal_year: 2024,
  fiscal_period: "FY",
  status: "computed",
  value: "46.206350",
  reason: null,
  period_start: "2023-10-01",
  period_end: "2024-09-28",
  inputs: [
    {
      concept: "gross_profit",
      label: "Gross profit",
      value: "180683000000",
      unit: "USD",
      fiscal_year: 2024,
      period_end: "2024-09-28",
      source: APPLE_10K,
    },
    {
      concept: "revenue",
      label: "Revenue",
      value: "391035000000",
      unit: "USD",
      fiscal_year: 2024,
      period_end: "2024-09-28",
      source: APPLE_10K,
    },
  ],
};

export const peers: PeersCard = {
  kind: "peers",
  call_id: "c3",
  metric: "gross_margin",
  label: "Gross margin",
  unit: "percent",
  fiscal_year: 2024,
  fiscal_period: "FY",
  same_period_end: false,
  note: "Each company is compared on its own fiscal year; fiscal years can end in different months, so compare the period end dates before reading the ranking as same-period.",
  rows: [
    {
      rank: 1,
      company: NVIDIA,
      status: "computed",
      value: "72.717573",
      period_end: "2024-01-28",
      reason: null,
    },
    {
      rank: 2,
      company: APPLE,
      status: "computed",
      value: "46.206350",
      period_end: "2024-09-28",
      reason: null,
    },
    {
      rank: null,
      company: { ticker: "MSFT", name: "Microsoft" },
      status: "not_reported",
      value: null,
      period_end: null,
      reason: "not reported for fiscal 2024 FY: gross_profit, revenue",
    },
  ],
};

export const riskDiff: RiskDiffCard = {
  kind: "risk_diff",
  call_id: "c4",
  company: { ticker: "SIMW", name: "SIM Widgets Inc." },
  status: "compared",
  reason: null,
  current: {
    accession: "9999999999-25-000008",
    form: "10-K",
    filing_date: "2025-02-20",
    report_date: "2024-12-31",
    fiscal_year: 2024,
    url: "https://www.sec.gov/Archives/edgar/data/9999999999/sim-10k.htm",
  },
  previous: {
    accession: "9999999999-24-000002",
    form: "10-K",
    filing_date: "2024-02-20",
    report_date: "2023-12-31",
    fiscal_year: 2023,
    url: "https://www.sec.gov/Archives/edgar/data/9999999999/sim-10k-2023.htm",
  },
  added: 1,
  removed: 0,
  changed: 0,
  unchanged: 2,
  changes: [{ kind: "added", text: "SIMULATED new risk about supply.", previous_text: null }],
  changes_total: 1,
};

export const outOfScope: NoticeCard = {
  kind: "notice",
  call_id: "c5",
  tool: "get_fact",
  code: "unknown_company",
  message: "'ZZZZ' is not in the 98 companies this product covers",
};

export const filingCitation: Citation = {
  key: APPLE_10K.accession,
  kind: "filing",
  company: APPLE,
  form: "10-K",
  section: null,
  filing_date: APPLE_10K.filed,
  report_date: null,
  text: null,
  url: APPLE_10K.url,
};

export const passageCitation: Citation = {
  key: PASSAGE_KEY,
  kind: "passage",
  company: { ticker: "SIMW", name: "SIM Widgets Inc." },
  form: "10-K",
  section: "mdna",
  filing_date: "2025-02-20",
  report_date: "2024-12-31",
  text: "SIMULATED passage about supply constraints.",
  url: "https://www.sec.gov/Archives/edgar/data/9999999999/sim-10k.htm",
};

export const revenueTrend: Chart = {
  kind: "trend",
  title: "Revenue",
  unit: "USD",
  series: [
    {
      name: "AAPL",
      points: [
        { x: "FY2022", value: "394328000000", period_end: "2022-09-24" },
        { x: "FY2023", value: "383285000000", period_end: "2023-09-30" },
        { x: "FY2024", value: "391035000000", period_end: "2024-09-28" },
      ],
    },
  ],
};

export const marginTrend: Chart = {
  kind: "trend",
  title: "Gross margin",
  unit: "percent",
  series: [
    {
      name: "NVDA",
      points: [
        { x: "FY2023", value: "56.928894", period_end: "2023-01-29" },
        { x: "FY2024", value: "72.717573", period_end: "2024-01-28" },
      ],
    },
    {
      name: "AAPL",
      points: [{ x: "FY2024", value: "46.206350", period_end: "2024-09-28" }],
    },
  ],
};

export const ANSWER_TEXT = `SIMULATED: Apple reported revenue of $391,035 million for fiscal 2024 [${APPLE_10K.accession}]. Supply was constrained [${PASSAGE_KEY}].`;

export const answer: AnswerEvent = {
  thread_id: THREAD,
  turn: 1,
  status: "answered",
  reason: null,
  degraded: false,
  text: ANSWER_TEXT,
  cards: [revenue],
  citations: [filingCitation, passageCitation],
  charts: [],
  check: { verdict: "pass", figures: 1, traced: 1, removed: 0 },
};

export const degradedAnswer: AnswerEvent = {
  ...answer,
  status: "degraded",
  reason: "llm_unavailable",
  degraded: true,
  text: "The language model is unavailable right now, so this answer has no written explanation. Any figures and passages retrieved for your question are shown as returned by the tools. This is not investment advice.",
  citations: [filingCitation],
  check: null,
};

export const blockedAnswer: AnswerEvent = {
  ...answer,
  status: "blocked",
  reason: "untraced_figures",
  text: "The written answer was withheld because it stated figures that could not be traced to the filings. Any figures and passages retrieved for your question are shown as returned by the tools. This is not investment advice.",
  citations: [filingCitation],
  check: { verdict: "blocked", figures: 1, traced: 0, removed: 1 },
};

/** The events of one answered turn, in the order the API streams them. */
export const answeredTurn: ChatEvent[] = [
  { type: "turn", data: { thread_id: THREAD, cohort: "real", usage } },
  { type: "evidence", data: { cards: [revenue], citations: [filingCitation] } },
  { type: "answer", data: answer },
];

/** A send function that plays `events`, for components under test. */
export function playing(...turns: ChatEvent[][]) {
  const asked: { question: string; threadId: string }[] = [];
  const queue = [...turns];
  async function* send(question: string, threadId: string): AsyncGenerator<ChatEvent> {
    asked.push({ question, threadId });
    for (const event of queue.shift() ?? []) {
      yield event;
    }
  }
  return { send, asked };
}
