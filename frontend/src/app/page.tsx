"use client";
import { useState, useCallback } from "react";
import Sidebar from "@/components/Sidebar";
import ChatPanel from "@/components/ChatPanel";
import ArticlePanel from "@/components/ArticlePanel";
import { ChatMessage, CitedArticle } from "@/types";

export default function Home() {
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [citedArticles, setCitedArticles] = useState<CitedArticle[]>([]);

  const handleSelectSession = useCallback(async (sessionId: string) => {
    const { getSessionHistory } = await import("@/lib/api");
    setActiveSessionId(sessionId);
    setCitedArticles([]);
    const history = await getSessionHistory(sessionId);
    const msgs: ChatMessage[] = history.flatMap((h: any) => [
      { role: "user" as const, content: h.question },
      {
        role: "assistant" as const,
        content: h.answer ?? "此問題超出勞基法範圍。",
        cited_articles: h.cited_articles,
      },
    ]);
    setMessages(msgs);
    const lastCited = history.findLast((h: any) => h.cited_articles?.length)?.cited_articles;
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
      if (!activeSessionId) setActiveSessionId(sessionId);
    },
    [activeSessionId]
  );

  return (
    <main className="flex h-screen bg-slate-800 text-white overflow-hidden">
      <Sidebar
        activeSessionId={activeSessionId}
        onSelectSession={handleSelectSession}
        onNewSession={handleNewSession}
      />
      <ChatPanel
        sessionId={activeSessionId}
        messages={messages}
        onNewMessage={handleNewMessage}
        onArticlesChange={setCitedArticles}
      />
      <ArticlePanel citedArticles={citedArticles} />
    </main>
  );
}
