"use client";
import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ChatMessage, CitedArticle } from "@/types";
import { streamQuery } from "@/lib/api";

interface Props {
  sessionId: string | null;
  messages: ChatMessage[];
  onNewMessage: (userMsg: ChatMessage, assistantMsg: ChatMessage, sessionId: string) => void;
  onArticlesChange: (articles: CitedArticle[]) => void;
  selectedLawIds: string[];
  onOpenDrawer: () => void;
  onArticleSelect: (article: CitedArticle) => void;
}

interface Step {
  step: string;
  label: string;
}

const STEP_ICONS: Record<string, string> = {
  rewrite: "💬",
  hyde: "🔍",
  search: "📚",
  generate: "✍️",
};

export default function ChatPanel({ sessionId, messages, onNewMessage, onArticlesChange, selectedLawIds, onOpenDrawer, onArticleSelect }: Props) {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null);
  const [steps, setSteps] = useState<Step[]>([]);
  const [streamingContent, setStreamingContent] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (streamingContent) {
      bottomRef.current?.scrollIntoView({ behavior: "auto" });
    }
  }, [streamingContent]);

  async function handleSubmit() {
    const question = input.trim();
    if (!question || loading) return;
    if (question.length > 500) {
      alert("問題長度不得超過 500 字");
      return;
    }

    setInput("");
    setLoading(true);
    setPendingQuestion(question);
    setSteps([]);
    setStreamingContent("");

    const userMsg: ChatMessage = { role: "user", content: question };

    try {
      let finalAnswer = "";
      let finalCitedArticles: CitedArticle[] = [];
      let finalWarning: string | null = null;
      let finalSessionId = sessionId ?? "";
      let isOutOfScope = false;

      const historyPayload = messages
        .filter((m) => !m.is_out_of_scope)
        .slice(-6)
        .map((m) => ({ role: m.role, content: m.content }));

      for await (const event of streamQuery(
        question,
        sessionId ?? undefined,
        selectedLawIds.length > 0 ? selectedLawIds : undefined,
        historyPayload.length > 0 ? historyPayload : undefined,
      )) {
        if (event.type === "step") {
          setSteps((prev) => [...prev, { step: event.step, label: event.label }]);
        } else if (event.type === "token") {
          setStreamingContent((prev) => prev + event.text);
        } else if (event.type === "done") {
          finalAnswer = event.answer;
          finalCitedArticles = event.cited_articles;
          finalWarning = event.warning;
          finalSessionId = event.session_id;
        } else if (event.type === "out_of_scope") {
          isOutOfScope = true;
          finalSessionId = event.session_id;
        } else if (event.type === "error") {
          throw new Error(event.message);
        }
      }

      const assistantMsg: ChatMessage = {
        role: "assistant",
        content: isOutOfScope
          ? "此問題超出所選法規範圍，無法提供答案。"
          : finalAnswer,
        cited_articles: finalCitedArticles,
        warning: finalWarning,
        is_out_of_scope: isOutOfScope,
      };

      setPendingQuestion(null);
      setSteps([]);
      setStreamingContent("");
      onNewMessage(userMsg, assistantMsg, finalSessionId);
      if (finalCitedArticles.length) onArticlesChange(finalCitedArticles);
    } catch {
      const errorMsg: ChatMessage = { role: "assistant", content: "發生錯誤，請稍後重試。" };
      setPendingQuestion(null);
      setSteps([]);
      setStreamingContent("");
      onNewMessage(userMsg, errorMsg, sessionId ?? "");
    } finally {
      setLoading(false);
    }
  }

  const proseClass = "prose prose-invert prose-sm max-w-none prose-p:my-1 prose-headings:my-2 prose-ul:my-1 prose-ol:my-1 prose-li:my-0 prose-table:text-xs prose-th:bg-slate-700 prose-th:p-2 prose-td:p-2 prose-td:border-slate-700 prose-tr:border-slate-700";

  return (
    <div className="flex-1 flex flex-col bg-slate-800 min-w-0">
      {/* Mobile header bar */}
      <div className="md:hidden flex items-center gap-3 px-4 py-3 bg-slate-900 border-b border-slate-700 shrink-0">
        <button onClick={onOpenDrawer} className="text-slate-400 text-xl">☰</button>
        <span className="text-slate-200 text-sm font-medium flex-1">勞動法規查詢</span>
        <span className="text-slate-500 text-xs bg-slate-800 px-2 py-0.5 rounded-full">
          {selectedLawIds.length === 0 ? "全部法規" : `${selectedLawIds.length} 部`}
        </span>
      </div>
      <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4">
        {messages.length === 0 && (
          <div className="text-slate-500 text-sm text-center mt-20">
            輸入勞基法相關問題開始查詢
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[90%] md:max-w-[80%] rounded-xl px-4 py-3 text-sm leading-relaxed ${
                msg.role === "user"
                  ? "bg-blue-700 text-white rounded-br-sm"
                  : "bg-slate-900 text-slate-200 rounded-bl-sm"
              }`}
            >
              {msg.role === "assistant" && (
                <div className="text-blue-400 font-semibold text-xs mb-2">🤖 AI 回覆</div>
              )}
              {msg.role === "assistant" ? (
                <div className={proseClass}>
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                </div>
              ) : (
                <p className="whitespace-pre-wrap">{msg.content}</p>
              )}
              {msg.warning && (
                <div className="mt-2 text-yellow-400 text-xs bg-yellow-900/20 rounded p-2">
                  ⚠ {msg.warning}
                </div>
              )}
              {msg.cited_articles && msg.cited_articles.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2 items-center">
                  <span className="text-slate-500 text-xs">參考法條：</span>
                  {msg.cited_articles.map((c) => (
                    <button
                      key={`${c.law_id}-${c.article_number}`}
                      onClick={() => onArticleSelect(c)}
                      className="bg-blue-950 border border-blue-700 text-blue-300 px-3 py-1.5 rounded-full text-xs min-h-[32px]"
                      title={c.law_name}
                    >
                      {c.law_name} §{c.article_number}
                    </button>
                  ))}
                  <span className="text-slate-600 text-xs border border-slate-700 px-2 py-1 rounded-full">
                    相關度 {Math.round(msg.cited_articles[0].similarity * 100)}%
                  </span>
                </div>
              )}
            </div>
          </div>
        ))}

        {/* Pending user message */}
        {loading && pendingQuestion && (
          <div className="flex justify-end">
            <div className="max-w-[90%] md:max-w-[80%] rounded-xl px-4 py-3 text-sm leading-relaxed bg-blue-700 text-white rounded-br-sm">
              <p className="whitespace-pre-wrap">{pendingQuestion}</p>
            </div>
          </div>
        )}

        {/* Multi-step progress — shown during retrieval before first token */}
        {loading && steps.length > 0 && !streamingContent && (
          <div className="flex justify-start">
            <div className="bg-slate-900 rounded-xl px-4 py-3 text-sm space-y-2">
              {steps.map((s, i) => {
                const isLast = i === steps.length - 1;
                const icon = STEP_ICONS[s.step] ?? "•";
                return (
                  <div key={s.step} className="flex items-center gap-2.5">
                    {isLast ? (
                      <span className="text-base animate-bounce inline-block">{icon}</span>
                    ) : (
                      <span className="text-green-400 text-xs font-bold">✓</span>
                    )}
                    <span className={isLast ? "text-slate-300" : "text-slate-500 text-xs"}>
                      {s.label}
                      {isLast && <span className="animate-pulse">...</span>}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Streaming response bubble */}
        {loading && streamingContent && (
          <div className="flex justify-start">
            <div className="max-w-[90%] md:max-w-[80%] bg-slate-900 text-slate-200 rounded-xl px-4 py-3 text-sm leading-relaxed rounded-bl-sm">
              <div className="text-blue-400 font-semibold text-xs mb-2">🤖 AI 回覆</div>
              <div className={proseClass}>
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{streamingContent}</ReactMarkdown>
              </div>
              <span className="inline-block w-0.5 h-3.5 bg-blue-400 animate-pulse ml-0.5 align-middle" />
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <div className="p-3 bg-slate-900 border-t border-slate-700 flex gap-2 items-end">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
              e.preventDefault();
              handleSubmit();
            }
          }}
          placeholder="輸入問題..."
          rows={2}
          className="flex-1 bg-slate-800 border border-slate-700 text-slate-200 placeholder-slate-500 rounded-lg px-4 py-2.5 text-sm outline-none focus:border-blue-500 resize-none"
          disabled={loading}
          maxLength={500}
        />
        <button
          onClick={handleSubmit}
          disabled={loading || !input.trim()}
          className="bg-blue-700 text-white disabled:opacity-50 disabled:cursor-not-allowed transition-colors hover:bg-blue-600 rounded-full w-10 h-10 p-0 flex items-center justify-center text-lg md:rounded-lg md:w-auto md:h-auto md:px-4 md:py-2.5 md:text-sm md:font-medium"
        >
          <span className="md:hidden">↑</span>
          <span className="hidden md:inline">送出</span>
        </button>
      </div>
    </div>
  );
}
