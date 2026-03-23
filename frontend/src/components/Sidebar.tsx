"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { getSessions, getLawStatus } from "@/lib/api";
import { SessionSummary, LawStatus } from "@/types";
import LawScopeSelector from "@/components/LawScopeSelector";

interface Props {
  activeSessionId: string | null;
  onSelectSession: (id: string) => void;
  onNewSession: () => void;
  refreshKey?: number;
  selectedLawIds: string[];
  onLawScopeChange: (ids: string[]) => void;
  showLawScope?: boolean; // false on /laws page
  mobileOpen?: boolean;
  onMobileClose?: () => void;
}

export default function Sidebar({
  activeSessionId,
  onSelectSession,
  onNewSession,
  refreshKey,
  selectedLawIds,
  onLawScopeChange,
  showLawScope = true,
  mobileOpen = false,
  onMobileClose,
}: Props) {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [status, setStatus] = useState<LawStatus | null>(null);
  const pathname = usePathname();

  useEffect(() => {
    getSessions().then(setSessions).catch(console.error);
  }, [refreshKey]);

  useEffect(() => {
    getLawStatus().then(setStatus).catch(console.error);
  }, []);

  return (
    <aside
      className={`fixed inset-y-0 left-0 z-40 w-72 bg-slate-900 flex flex-col p-3 gap-3 shrink-0 transition-transform duration-300 relative md:relative md:translate-x-0 md:w-56 md:z-auto ${
        mobileOpen ? "translate-x-0" : "-translate-x-full"
      }`}
    >
      <button
        onClick={onMobileClose}
        className="md:hidden absolute top-3 right-3 text-slate-500 hover:text-slate-300 text-lg leading-none p-1"
        aria-label="關閉選單"
      >
        ✕
      </button>
      <span className="text-blue-400 font-bold text-xs tracking-wide uppercase">查詢紀錄</span>
      <button
        onClick={onNewSession}
        className="bg-blue-700 text-white rounded-md py-2 text-xs font-medium hover:bg-blue-600 transition-colors"
      >
        + 新增查詢
      </button>

      {showLawScope && (
        <LawScopeSelector
          selectedLawIds={selectedLawIds}
          onChange={onLawScopeChange}
        />
      )}

      <div className="flex-1 overflow-y-auto flex flex-col gap-1">
        {sessions.map((s) => (
          <button
            key={s.id}
            onClick={() => onSelectSession(s.id)}
            className={`text-left px-3 py-2 rounded text-xs transition-colors ${
              s.id === activeSessionId
                ? "bg-blue-950 border-l-2 border-blue-400 text-blue-300"
                : "text-slate-400 hover:bg-slate-800"
            }`}
          >
            {s.title}
          </button>
        ))}
      </div>

      {status && (
        <div className="bg-slate-950 rounded p-2 text-xs border border-slate-800">
          <div className="text-slate-500 text-[10px] mb-1">法條版本</div>
          <div className="text-slate-400">
            {status.last_updated
              ? new Date(status.last_updated).toLocaleDateString("zh-TW")
              : "尚未更新"}
          </div>
          <div
            className={`text-[10px] mt-1 ${
              status.status === "success" ? "text-green-500" : "text-yellow-500"
            }`}
          >
            {status.status === "success" ? "✓ 最新版本" : "⚠ 更新異常"}
          </div>
        </div>
      )}

      {/* Law management nav link */}
      <Link
        href="/laws"
        className={`text-xs text-center py-1.5 rounded transition-colors ${
          pathname === "/laws"
            ? "bg-blue-950 text-blue-300 border border-blue-700"
            : "text-slate-500 hover:text-slate-300 hover:bg-slate-800"
        }`}
      >
        📋 法規管理
      </Link>
    </aside>
  );
}
