"use client";
import { useState, useCallback } from "react";
import Sidebar from "@/components/Sidebar";
import ChatPanel from "@/components/ChatPanel";
import ArticlePanel from "@/components/ArticlePanel";
import ArticleSheet from "@/components/ArticleSheet";
import { ChatMessage, CitedArticle, QueryHistoryItem } from "@/types";

export default function Home() {
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [citedArticles, setCitedArticles] = useState<CitedArticle[]>([]);
  const [sidebarRefreshKey, setSidebarRefreshKey] = useState(0);
  const [selectedLawIds, setSelectedLawIds] = useState<string[]>([]); // [] = all laws
  const [selectedArticle, setSelectedArticle] = useState<CitedArticle | null>(null);

  const handleSelectSession = useCallback(async (sessionId: string) => {
    const { getSessionHistory } = await import("@/lib/api");
    setActiveSessionId(sessionId);
    setCitedArticles([]);
    const history = await getSessionHistory(sessionId);
    const msgs: ChatMessage[] = history.flatMap((h: QueryHistoryItem) => [
      { role: "user" as const, content: h.question },
      {
        role: "assistant" as const,
        content: h.answer ?? "此問題超出勞基法範圍。",
        cited_articles: h.cited_articles,
      },
    ]);
    setMessages(msgs);
    const lastCited = history.findLast((h: QueryHistoryItem) => h.cited_articles?.length)?.cited_articles;
    if (lastCited) setCitedArticles(lastCited);
  }, []);

  const handleNewSession = useCallback(() => {
    setActiveSessionId(null);
    setMessages([]);
    setCitedArticles([]);
  }, []);

  const handleNewMessage = useCallback(
    (userMsg: ChatMessage, assistantMsg: ChatMessage, sessionId: string) => {
      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      if (!activeSessionId) {
        setActiveSessionId(sessionId);
        setSidebarRefreshKey((k) => k + 1);
      }
    },
    [activeSessionId]
  );

  return (
    <main className="flex h-screen bg-slate-800 text-white overflow-hidden">
      <Sidebar
        activeSessionId={activeSessionId}
        onSelectSession={handleSelectSession}
        onNewSession={handleNewSession}
        refreshKey={sidebarRefreshKey}
        selectedLawIds={selectedLawIds}
        onLawScopeChange={setSelectedLawIds}
        showLawScope={true}
      />
      <ChatPanel
        sessionId={activeSessionId}
        messages={messages}
        onNewMessage={handleNewMessage}
        onArticlesChange={setCitedArticles}
        selectedLawIds={selectedLawIds}
        onOpenDrawer={() => {}} // Mobile drawer toggle (reserved for future sidebar state)
        onArticleSelect={setSelectedArticle}
      />
      <ArticlePanel citedArticles={citedArticles} />
      <ArticleSheet article={selectedArticle} onClose={() => setSelectedArticle(null)} />
    </main>
  );
}
