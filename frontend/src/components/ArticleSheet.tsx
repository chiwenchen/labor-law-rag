"use client";
import { useEffect, useState } from "react";
import { CitedArticle, LawArticle } from "@/types";
import { getArticle } from "@/lib/api";

interface Props {
  article: CitedArticle | null;
  onClose: () => void;
}

function ArticleSheetBody({ article }: { article: CitedArticle | null }) {
  const [lawArticle, setLawArticle] = useState<LawArticle | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!article) {
      setLawArticle(null);
      setError(false);
      return;
    }
    setLawArticle(null);
    setError(false);
    setLoading(true);
    getArticle(article.article_number, article.law_id)
      .then(setLawArticle)
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [article]);

  // Guard: article is null (sheet is closed)
  if (!article) return null;

  if (loading) {
    return <div className="px-4 pb-6 text-slate-500 text-sm">查詢中...</div>;
  }
  if (error || !lawArticle) {
    return <div className="px-4 pb-6 text-red-400 text-sm">無法載入條文</div>;
  }
  return (
    <div className="px-4 pb-6">
      <p className="text-slate-400 text-[11px] leading-relaxed whitespace-pre-wrap">
        {lawArticle.content}
      </p>
      {lawArticle.version && (
        <div className="text-slate-600 text-[10px] mt-2">修正日期：{lawArticle.version}</div>
      )}
    </div>
  );
}

export default function ArticleSheet({ article, onClose }: Props) {
  return (
    <div className="md:hidden">
      {/* Backdrop */}
      {article && (
        <div className="fixed inset-0 z-50 bg-black/50" onClick={onClose} />
      )}
      {/* Sheet — always in DOM, slides in/out */}
      <div
        className={`fixed bottom-0 left-0 right-0 z-50 bg-slate-900 rounded-t-2xl border-t border-slate-700 transition-transform duration-300 ${
          article ? "translate-y-0" : "translate-y-full"
        }`}
      >
        {/* Drag handle */}
        <div className="flex justify-center pt-3 pb-1 shrink-0">
          <div className="w-8 h-1 bg-slate-600 rounded-full" />
        </div>
        {/* Header */}
        <div className="flex justify-between items-start px-4 pb-3 shrink-0">
          <div className="text-green-400 font-bold text-sm">
            {article?.law_name} 第 {article?.article_number} 條
          </div>
          <button onClick={onClose} className="text-slate-500 text-xl leading-none">
            ✕
          </button>
        </div>
        {/* Scrollable content */}
        <div className="max-h-[70vh] overflow-y-auto">
          <ArticleSheetBody article={article} />
        </div>
      </div>
    </div>
  );
}
