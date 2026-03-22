"use client";
import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import Sidebar from "@/components/Sidebar";
import { getLaws, updateLaw } from "@/lib/api";
import { SupportedLaw } from "@/types";

function StatusBadge({ status }: { status: SupportedLaw["last_status"] }) {
  if (status === "success")
    return <span className="text-green-400 text-xs">✓ 最新</span>;
  if (status === "failed")
    return <span className="text-red-400 text-xs">✗ 更新失敗</span>;
  return <span className="text-yellow-500 text-xs">⚠ 未載入</span>;
}

export default function LawsPage() {
  const [laws, setLaws] = useState<SupportedLaw[]>([]);
  const [updating, setUpdating] = useState<Record<string, boolean>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});

  const fetchLaws = useCallback(async () => {
    try {
      setLaws(await getLaws());
    } catch {
      // silent — table will be empty
    }
  }, []);

  useEffect(() => {
    fetchLaws();
  }, [fetchLaws]);

  async function handleUpdate(lawId: string) {
    setUpdating((prev) => ({ ...prev, [lawId]: true }));
    setErrors((prev) => ({ ...prev, [lawId]: "" }));
    try {
      await updateLaw(lawId);
      await fetchLaws(); // refresh row
    } catch (e) {
      setErrors((prev) => ({
        ...prev,
        [lawId]: e instanceof Error ? e.message : "更新失敗",
      }));
    } finally {
      setUpdating((prev) => ({ ...prev, [lawId]: false }));
    }
  }

  return (
    <main className="flex h-screen bg-slate-800 text-white overflow-hidden">
      <Sidebar
        activeSessionId={null}
        onSelectSession={() => {}}
        onNewSession={() => {}}
        selectedLawIds={[]}
        onLawScopeChange={() => {}}
        showLawScope={false}
      />

      <div className="flex-1 flex flex-col min-w-0 p-6">
        <div className="flex items-center gap-4 mb-6">
          <Link href="/" className="text-slate-400 hover:text-white text-sm transition-colors">
            ← 返回查詢
          </Link>
          <h1 className="text-white font-semibold text-lg">法規管理</h1>
        </div>

        <div className="bg-slate-900 rounded-lg border border-slate-700 overflow-hidden">
          {/* Table header */}
          <div className="grid grid-cols-[2fr_80px_140px_100px_80px] gap-4 px-4 py-2.5 bg-slate-950 text-slate-500 text-xs font-medium uppercase tracking-wide border-b border-slate-700">
            <span>法規名稱</span>
            <span>條文數</span>
            <span>最後更新</span>
            <span>狀態</span>
            <span></span>
          </div>

          {laws.length === 0 && (
            <div className="px-4 py-8 text-center text-slate-500 text-sm">
              載入中...
            </div>
          )}

          {laws.map((law, i) => (
            <div
              key={law.law_id}
              className={`grid grid-cols-[2fr_80px_140px_100px_80px] gap-4 px-4 py-3 items-center text-sm ${
                i > 0 ? "border-t border-slate-800" : ""
              }`}
            >
              <span className="text-slate-200 font-medium">{law.law_name}</span>
              <span className="text-slate-400 text-xs">
                {law.article_count > 0 ? law.article_count : "—"}
              </span>
              <span className="text-slate-500 text-xs">
                {law.last_updated
                  ? new Date(law.last_updated).toLocaleDateString("zh-TW")
                  : "尚未更新"}
              </span>
              <span>
                <StatusBadge status={law.last_status} />
                {errors[law.law_id] && (
                  <div className="text-red-400 text-[10px] mt-0.5 leading-tight">
                    {errors[law.law_id]}
                  </div>
                )}
              </span>
              <span>
                <button
                  onClick={() => handleUpdate(law.law_id)}
                  disabled={updating[law.law_id]}
                  className={`text-xs px-3 py-1.5 rounded transition-colors w-full ${
                    law.last_status === "never_run"
                      ? "bg-blue-700 text-white hover:bg-blue-600 disabled:opacity-50"
                      : "bg-slate-700 text-slate-300 hover:bg-slate-600 disabled:opacity-50"
                  } disabled:cursor-not-allowed`}
                >
                  {updating[law.law_id] ? (
                    <span className="inline-flex items-center gap-1">
                      <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24" fill="none">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                      </svg>
                      更新中
                    </span>
                  ) : law.last_status === "never_run" ? (
                    "載入"
                  ) : (
                    "更新"
                  )}
                </button>
              </span>
            </div>
          ))}
        </div>

        <p className="text-slate-600 text-xs mt-3">
          共 {laws.length} 部法規 · 資料來源：全國法規資料庫（kong0107/mojLawSplitJSON）
        </p>
      </div>
    </main>
  );
}
