export interface CitedArticle {
  article_number: string;
  title: string | null;
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
}

export interface LawStatus {
  last_updated: string | null;
  status: string;
  total_active_articles: number;
}
