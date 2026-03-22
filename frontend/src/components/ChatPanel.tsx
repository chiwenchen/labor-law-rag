"use client";
import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import { ChatMessage, CitedArticle } from "@/types";
import { postQuery } from "@/lib/api";

interface Props {
  sessionId: string | null;
  messages: ChatMessage[];
  onNewMessage: (userMsg: ChatMessage, assistantMsg: ChatMessage, sessionId: string) => void;
  onArticlesChange: (articles: CitedArticle[]) => void;
}

export default function ChatPanel({ sessionId, messages, onNewMessage, onArticlesChange }: Props) {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleSubmit() {
    const question = input.trim();
    if (!question || loading) return;
    if (question.length > 500) {
      alert("問題長度不得超過 500 字");
      return;
    }

    setInput("");
    setLoading(true);

    const userMsg: ChatMessage = { role: "user", content: question };

    try {
      const data = await postQuery(question, sessionId ?? undefined);
      const assistantMsg: ChatMessage = {
        role: "assistant",
        content: data.is_out_of_scope
          ? "此問題超出勞基法範圍，無法提供答案。"
          : data.answer ?? "",
        cited_articles: data.cited_articles,
        warning: data.warning,
        is_out_of_scope: data.is_out_of_scope,
      };
      onNewMessage(userMsg, assistantMsg, data.session_id);
      if (data.cited_articles?.length) onArticlesChange(data.cited_articles);
    } catch {
      const errorMsg: ChatMessage = { role: "assistant", content: "發生錯誤，請稍後重試。" };
      onNewMessage(userMsg, errorMsg, sessionId ?? "");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex-1 flex flex-col bg-slate-800 min-w-0">
      <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4">
        {messages.length === 0 && (
          <div className="text-slate-500 text-sm text-center mt-20">
            輸入勞基法相關問題開始查詢
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[80%] rounded-xl px-4 py-3 text-sm leading-relaxed ${
                msg.role === "user"
                  ? "bg-blue-700 text-white rounded-br-sm"
                  : "bg-slate-900 text-slate-200 rounded-bl-sm"
              }`}
            >
              {msg.role === "assistant" && (
                <div className="text-blue-400 font-semibold text-xs mb-2">🤖 AI 回覆</div>
              )}
              {msg.role === "assistant" ? (
                <div className="prose prose-invert prose-sm max-w-none prose-p:my-1 prose-headings:my-2 prose-ul:my-1 prose-ol:my-1 prose-li:my-0">
                  <ReactMarkdown>{msg.content}</ReactMarkdown>
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
                    <span
                      key={c.article_number}
                      className="bg-blue-950 border border-blue-700 text-blue-300 px-2 py-1 rounded-full text-xs"
                    >
                      §{c.article_number}
                    </span>
                  ))}
                  <span className="text-slate-600 text-xs border border-slate-700 px-2 py-1 rounded-full">
                    相關度 {Math.round(msg.cited_articles[0].similarity * 100)}%
                  </span>
                </div>
              )}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-slate-900 text-slate-400 rounded-xl px-4 py-3 text-sm">
              查詢中...
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
          placeholder="輸入您的勞基法問題... （Ctrl+Enter 送出）"
          rows={2}
          className="flex-1 bg-slate-800 border border-slate-700 text-slate-200 placeholder-slate-500 rounded-lg px-4 py-2.5 text-sm outline-none focus:border-blue-500 resize-none"
          disabled={loading}
          maxLength={500}
        />
        <button
          onClick={handleSubmit}
          disabled={loading || !input.trim()}
          className="bg-blue-700 text-white rounded-lg px-4 py-2.5 text-sm font-medium hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          送出
        </button>
      </div>
    </div>
  );
}
