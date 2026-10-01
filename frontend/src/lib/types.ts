export interface ProspectInput {
  prospect_name: string;
  company: string;
  job_title?: string | null;
  company_url?: string | null;
  referral?: string | null;
  x_post_url?: string | null;
}

export interface SearchResult {
  title: string;
  url: string;
  content: string;
  source_name: string;
  source_type: string;
  published_date: string | null;
  retrieved_date: string;
  query?: string | null;
}

export interface Evidence extends SearchResult {
  dedupe_key: string;
  relevance_score: number;
  source_quality_score: number;
  recency_score: number;
  rank_score: number;
  rationale: string;
}

export interface Signal {
  signal_type: string;
  title: string;
  description: string;
  source_name: string;
  source_url: string;
  published_date: string | null;
  retrieved_date: string;
  evidence: string;
  recency_score: number;
  source_quality_score: number;
  relevance_score: number;
}

export interface ResearchStats {
  queries_run: number;
  raw_results: number;
  after_dedupe: number;
  after_filtering: number;
  selected_evidence: number;
}

export interface ResearchBundle {
  company: string;
  company_url: string | null;
  mode: string;
  queries: string[];
  evidence: Evidence[];
  signals: Signal[];
  stats: ResearchStats;
  generated_at: string;
}

export interface RetrievedChunk {
  chunk_id: string;
  source: string;
  heading: string;
  text: string;
  score: number;
}

export type Severity = "LOW" | "MEDIUM" | "HIGH";

export interface Problem {
  title: string;
  description: string;
  rationale: string;
  severity: Severity;
  confidence: number;
  related_signals: string[];
  source_urls: string[];
}

export interface SolutionMatch {
  problem_title: string;
  service: string;
  how_it_helps: string;
  relevance_score: number;
  rationale: string;
  knowledge_sources: string[];
}

export type OutreachStatus = "DRAFT" | "EDITED" | "APPROVED";
export type OutreachChannel = "EMAIL" | "LINKEDIN";

export interface OutreachMessage {
  id: number;
  prospect_id: number;
  analysis_id: number | null;
  research_run_id: number | null;
  channel: OutreachChannel;
  status: OutreachStatus;
  subject: string;
  content: string;
  confidence: number;
  referenced_sources: string[];
  problem_title: string | null;
  service: string | null;
  created_at: string;
  updated_at: string;
}

export interface OutreachDraft {
  id?: number | null;
  channel: OutreachChannel;
  subject: string | null;
  body: string;
  status: OutreachStatus;
  confidence: number;
  referenced_sources: string[];
}

export interface AnalyzeResponse {
  prospect_id: number;
  analysis_id: number;
  run_id: number;
  mode: string;
  engine: string;
  bundle: ResearchBundle;
  knowledge: RetrievedChunk[];
  problems: Problem[];
  solutions: SolutionMatch[];
  outreach: OutreachDraft[];
}

export interface HealthResponse {
  status: string;
  app: string;
  version: string;
  environment: string;
  research_mode: string;
  analysis_mode: string;
  llm_provider: string;
  llm_model: string;
  rag_index_ready: boolean;
  knowledge_dir: string;
  database: string;
}
