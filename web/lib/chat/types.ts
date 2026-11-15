// What the API sends for a turn (`sec_agent.api.events` and `sec_agent.api.cards`).
// Every value a tool returned arrives as its exact decimal text, never as a float.

export type Cohort = "real" | "simulated";

export interface Usage {
  used: number;
  limit: number;
  resets_at: string;
}

export interface CompanyTag {
  ticker: string;
  name: string;
}

export interface FilingSource {
  accession: string;
  form: string;
  filed: string;
  url: string;
}

export interface FactCard {
  kind: "fact";
  call_id: string;
  company: CompanyTag;
  concept: string;
  label: string;
  unit: string;
  fiscal_year: number;
  fiscal_period: string;
  status: "found" | "not_reported";
  value: string | null;
  period_start: string | null;
  period_end: string | null;
  source: FilingSource | null;
  restated: boolean;
  original_value: string | null;
  original_filed: string | null;
}

export interface RatioInput {
  concept: string;
  label: string;
  value: string;
  unit: string;
  fiscal_year: number | null;
  period_end: string;
  source: FilingSource;
}

export interface RatioCard {
  kind: "ratio";
  call_id: string;
  company: CompanyTag;
  ratio: string;
  label: string;
  formula: string;
  unit: string;
  fiscal_year: number;
  fiscal_period: string;
  status: "computed" | "not_reported" | "undefined";
  value: string | null;
  reason: string | null;
  period_start: string | null;
  period_end: string | null;
  inputs: RatioInput[];
}

export interface PeerRow {
  rank: number | null;
  company: CompanyTag;
  status: "found" | "computed" | "not_reported" | "undefined";
  value: string | null;
  period_end: string | null;
  reason: string | null;
}

export interface PeersCard {
  kind: "peers";
  call_id: string;
  metric: string;
  label: string;
  unit: string;
  fiscal_year: number;
  fiscal_period: string;
  same_period_end: boolean;
  note: string;
  rows: PeerRow[];
}

export interface RiskFiling {
  accession: string;
  form: string;
  filing_date: string;
  report_date: string;
  fiscal_year: number;
  url: string;
}

export interface RiskChange {
  kind: "added" | "removed" | "changed";
  text: string | null;
  previous_text: string | null;
}

export interface RiskDiffCard {
  kind: "risk_diff";
  call_id: string;
  company: CompanyTag;
  status: "compared" | "not_found";
  reason: string | null;
  current: RiskFiling | null;
  previous: RiskFiling | null;
  added: number;
  removed: number;
  changed: number;
  unchanged: number;
  changes: RiskChange[];
  changes_total: number;
}

export interface NoticeCard {
  kind: "notice";
  call_id: string;
  tool: string;
  code: string;
  message: string;
}

export type Card = FactCard | RatioCard | PeersCard | RiskDiffCard | NoticeCard;

export interface Citation {
  key: string;
  kind: "passage" | "filing";
  company: CompanyTag | null;
  form: string;
  section: string | null;
  filing_date: string;
  report_date: string | null;
  text: string | null;
  url: string;
}

export interface ChartPoint {
  x: string;
  value: string;
  period_end: string | null;
}

export interface ChartSeries {
  name: string;
  points: ChartPoint[];
}

export interface Chart {
  kind: "trend" | "peers";
  title: string;
  unit: string;
  series: ChartSeries[];
}

export interface CheckSummary {
  verdict: "pass" | "trimmed" | "blocked";
  figures: number;
  traced: number;
  removed: number;
}

export type TurnStatus = "answered" | "step_limit" | "degraded" | "blocked";

export interface TurnEvent {
  thread_id: string;
  cohort: Cohort;
  usage: Usage;
}

export interface EvidenceEvent {
  cards: Card[];
  citations: Citation[];
}

export interface AnswerEvent {
  thread_id: string;
  turn: number;
  status: TurnStatus;
  reason: string | null;
  degraded: boolean;
  text: string;
  cards: Card[];
  citations: Citation[];
  charts: Chart[];
  check: CheckSummary | null;
}

/** An error event of the stream, or a refusal of the request (which may add fields). */
export interface ErrorEvent {
  code: string;
  message: string;
  limit?: number;
  resets_at?: string;
}

export type ChatEvent =
  | { type: "turn"; data: TurnEvent }
  | { type: "evidence"; data: EvidenceEvent }
  | { type: "answer"; data: AnswerEvent }
  | { type: "error"; data: ErrorEvent };

export type Rating = "up" | "down";

export interface FeedbackRequest {
  threadId: string;
  turn: number;
  rating: Rating;
}

/** Sends one question and yields the events of its turn. */
export type SendQuestion = (question: string, threadId: string) => AsyncIterable<ChatEvent>;

/** Sends one rating; false when it was not kept. */
export type SendFeedback = (feedback: FeedbackRequest) => Promise<boolean>;
