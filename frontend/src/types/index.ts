export interface CitedArticle {
  article_number: string;
  title: string | null;
  law_id: string;
  law_name: string;
  similarity: number;
}

export interface QueryResponse {
  session_id: string;
  is_out_of_scope: boolean;
  answer: string | null;
  warning: string | null;
  cited_articles: CitedArticle[];
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  cited_articles?: CitedArticle[];
  warning?: string | null;
  is_out_of_scope?: boolean;
}

export interface SessionSummary {
  id: string;
  title: string;
  created_at: string;
}

export interface LawArticle {
  article_number: string;
  title: string | null;
  content: string;
  last_updated: string | null;
  version: string | null;
  law_id: string;
  law_name: string;
}

export interface LawStatus {
  last_updated: string | null;
  status: string;
  total_active_articles: number;
}

export interface QueryHistoryItem {
  id: string;
  question: string;
  answer: string;
  cited_articles: CitedArticle[];
  max_similarity_score: number;
  created_at: string;
}

export type StreamEvent =
  | { type: "step"; step: string; label: string }
  | { type: "token"; text: string }
  | { type: "done"; session_id: string; cited_articles: CitedArticle[]; warning: string | null; answer: string }
  | { type: "out_of_scope"; session_id: string }
  | { type: "error"; message: string };

export interface SupportedLaw {
  law_id: string;
  law_name: string;
  article_count: number;
  last_updated: string | null;
  last_status: "success" | "failed" | "never_run";
}

export interface User {
  email: string;
  role: "hr" | "employee";
  access_role?: "admin" | "user";
}

export interface AdminUser {
  id: string;
  email: string;
  role: "hr" | "employee";
  access_role: "admin" | "user";
  credits: number;
  last_query_at: string | null;
  session_count: number;
}

export interface AdminSession {
  id: string;
  title: string;
  query_count: number;
  created_at: string;
  last_query_at: string | null;
}

export interface AdminUsersResponse {
  users: AdminUser[];
  total: number;
  page: number;
  limit: number;
}

export interface AdminUserSessionsResponse {
  sessions: AdminSession[];
  total: number;
  page: number;
  limit: number;
}
