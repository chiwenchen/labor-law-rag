"use client";
import { useEffect, useState } from "react";
import { getArticle } from "@/lib/api";
import { LawArticle, CitedArticle } from "@/types";

interface Props {
  citedArticles: CitedArticle[];
}

export default function ArticlePanel({ citedArticles }: Props) {
  const [articles, setArticles] = useState<LawArticle[]>([]);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (citedArticles.length === 0) return;
    Promise.all(citedArticles.map((c) => getArticle(c.article_number, c.law_id)))
      .then(setArticles)
      .catch(console.error);
    setCollapsed(new Set(citedArticles.slice(1).map((c) => c.article_number)));
  }, [citedArticles]);

  if (articles.length === 0) {
    return (
      <aside className="w-60 bg-slate-900 p-3 text-xs text-slate-600 flex items-center justify-center shrink-0">
        引用法條將顯示於此
      </aside>
    );
  }

  return (
    <aside className="w-60 bg-slate-900 flex flex-col p-3 gap-2 overflow-y-auto shrink-0">
      <span className="text-blue-400 font-bold text-xs tracking-wide uppercase">法條原文</span>
      {articles.map((article) => {
        const isCollapsed = collapsed.has(article.article_number);
        return (
          <div key={article.article_number} className="bg-slate-800 rounded p-3">
            <button
              className="w-full text-left"
              onClick={() =>
                setCollapsed((prev) => {
                  const next = new Set(prev);
                  if (isCollapsed) {
                    next.delete(article.article_number);
                  } else {
                    next.add(article.article_number);
                  }
                  return next;
                })
              }
            >
              <div className="text-green-400 font-bold text-xs mb-1">
                {article.law_name} 第 {article.article_number} 條{article.title ? `（${article.title}）` : ""}
              </div>
              <div className="text-slate-500 text-[10px]">{isCollapsed ? "展開原文 ▼" : "收合 ▲"}</div>
            </button>
            {!isCollapsed && (
              <p className="text-slate-400 text-[11px] leading-relaxed mt-2 whitespace-pre-wrap">
                {article.content}
              </p>
            )}
            {article.version && (
              <div className="text-slate-600 text-[10px] mt-2">修正日期：{article.version}</div>
            )}
          </div>
        );
      })}
    </aside>
  );
}
