"use client";
import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import {
  getAdminUsers,
  getAdminUserSessions,
  updateUserCredits,
  updateUserAccessRole,
} from "@/lib/api";
import type { AdminUser, AdminSession } from "@/types";

interface FlashState {
  userId: string;
  type: "success" | "error";
}

export default function AdminPage() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const limit = 20;

  const [expandedUserId, setExpandedUserId] = useState<string | null>(null);
  const [sessions, setSessions] = useState<AdminSession[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);

  const [editingCreditsId, setEditingCreditsId] = useState<string | null>(null);
  const [editingCreditsValue, setEditingCreditsValue] = useState("");
  const [flash, setFlash] = useState<FlashState | null>(null);

  const fetchUsers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getAdminUsers(page, limit);
      setUsers(data.users);
      setTotal(data.total);
    } catch {
      setError("無法載入使用者列表");
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  const totalSessions = users.reduce((sum, u) => sum + u.session_count, 0);
  const startIndex = (page - 1) * limit + 1;
  const endIndex = Math.min(page * limit, total);
  const totalPages = Math.ceil(total / limit);

  async function handleExpandUser(userId: string) {
    if (expandedUserId === userId) {
      setExpandedUserId(null);
      setSessions([]);
      return;
    }
    setExpandedUserId(userId);
    setSessionsLoading(true);
    try {
      const data = await getAdminUserSessions(userId);
      setSessions(data.sessions);
    } catch {
      setSessions([]);
    } finally {
      setSessionsLoading(false);
    }
  }

  async function handleAccessRoleChange(userId: string, newRole: "admin" | "user") {
    try {
      const updated = await updateUserAccessRole(userId, newRole);
      setUsers((prev) =>
        prev.map((u) => (u.id === userId ? { ...u, access_role: updated.access_role } : u))
      );
      triggerFlash(userId, "success");
    } catch {
      triggerFlash(userId, "error");
    }
  }

  function startEditingCredits(userId: string, currentCredits: number) {
    setEditingCreditsId(userId);
    setEditingCreditsValue(String(currentCredits));
  }

  async function saveCredits(userId: string) {
    const newCredits = parseInt(editingCreditsValue, 10);
    if (isNaN(newCredits) || newCredits < 0) {
      triggerFlash(userId, "error");
      setEditingCreditsId(null);
      return;
    }
    try {
      const updated = await updateUserCredits(userId, newCredits);
      setUsers((prev) =>
        prev.map((u) => (u.id === userId ? { ...u, credits: updated.credits } : u))
      );
      triggerFlash(userId, "success");
    } catch {
      triggerFlash(userId, "error");
    } finally {
      setEditingCreditsId(null);
    }
  }

  function cancelEditingCredits() {
    setEditingCreditsId(null);
  }

  function triggerFlash(userId: string, type: "success" | "error") {
    setFlash({ userId, type });
    setTimeout(() => setFlash(null), 500);
  }

  function formatDate(dateStr: string | null): string {
    if (!dateStr) return "—";
    return new Date(dateStr).toLocaleDateString("zh-TW", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function roleBadge(role: string) {
    const styles: Record<string, string> = {
      hr: "bg-blue-900/20 text-blue-400",
      employee: "bg-green-900/20 text-green-400",
      admin: "bg-red-900/20 text-red-400",
    };
    const labels: Record<string, string> = {
      hr: "HR",
      employee: "員工",
      admin: "管理員",
    };
    return (
      <span className={`text-xs px-2 py-0.5 rounded font-medium ${styles[role] ?? "bg-slate-700 text-slate-300"}`}>
        {labels[role] ?? role}
      </span>
    );
  }

  function flashClass(userId: string): string {
    if (!flash || flash.userId !== userId) return "";
    return flash.type === "success"
      ? "bg-green-900/30 transition-colors duration-500"
      : "bg-red-900/30 transition-colors duration-500";
  }

  return (
    <div className="min-h-screen bg-slate-800 text-white">
      {/* Top nav */}
      <nav className="bg-slate-900 border-b border-slate-700 px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link href="/" className="text-slate-400 hover:text-slate-200 text-sm transition-colors">
            ← 返回查詢
          </Link>
          <h1 className="text-lg font-bold text-white">使用者管理</h1>
        </div>
      </nav>

      <div className="max-w-6xl mx-auto px-6 py-6">
        {/* Stats summary */}
        {!loading && !error && (
          <div className="flex gap-4 mb-6">
            <div className="bg-slate-900 border border-slate-700 rounded-lg px-4 py-3">
              <div className="text-slate-500 text-xs">使用者總數</div>
              <div className="text-xl font-bold text-white">{total}</div>
            </div>
            <div className="bg-slate-900 border border-slate-700 rounded-lg px-4 py-3">
              <div className="text-slate-500 text-xs">對話總數</div>
              <div className="text-xl font-bold text-white">{totalSessions}</div>
            </div>
          </div>
        )}

        {/* Error state */}
        {error && (
          <div className="text-center py-20">
            <p className="text-red-400 mb-4">{error}</p>
            <button
              onClick={fetchUsers}
              className="bg-blue-700 hover:bg-blue-600 text-white px-4 py-2 rounded text-sm transition-colors"
            >
              重新載入
            </button>
          </div>
        )}

        {/* Loading skeleton */}
        {loading && (
          <div className="bg-slate-900 rounded-lg border border-slate-700 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-700 text-slate-400 text-xs">
                  <th className="text-left px-4 py-3 font-medium">Email</th>
                  <th className="text-left px-4 py-3 font-medium">LLM角色</th>
                  <th className="text-left px-4 py-3 font-medium">存取權限</th>
                  <th className="text-left px-4 py-3 font-medium">Credits</th>
                  <th className="text-left px-4 py-3 font-medium">最後活動</th>
                  <th className="text-left px-4 py-3 font-medium">對話數</th>
                </tr>
              </thead>
              <tbody>
                {Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i} className="border-b border-slate-800">
                    <td className="px-4 py-3"><div className="h-4 w-48 bg-slate-700 rounded animate-pulse" /></td>
                    <td className="px-4 py-3"><div className="h-4 w-12 bg-slate-700 rounded animate-pulse" /></td>
                    <td className="px-4 py-3"><div className="h-4 w-20 bg-slate-700 rounded animate-pulse" /></td>
                    <td className="px-4 py-3"><div className="h-4 w-12 bg-slate-700 rounded animate-pulse" /></td>
                    <td className="px-4 py-3"><div className="h-4 w-28 bg-slate-700 rounded animate-pulse" /></td>
                    <td className="px-4 py-3"><div className="h-4 w-8 bg-slate-700 rounded animate-pulse" /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Empty state */}
        {!loading && !error && users.length === 0 && (
          <div className="text-center py-20 text-slate-500">尚無使用者</div>
        )}

        {/* User table */}
        {!loading && !error && users.length > 0 && (
          <>
            <div className="bg-slate-900 rounded-lg border border-slate-700 overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-700 text-slate-400 text-xs">
                    <th className="text-left px-4 py-3 font-medium">Email</th>
                    <th className="text-left px-4 py-3 font-medium">LLM角色</th>
                    <th className="text-left px-4 py-3 font-medium">存取權限</th>
                    <th className="text-left px-4 py-3 font-medium">Credits</th>
                    <th className="text-left px-4 py-3 font-medium">最後活動</th>
                    <th className="text-left px-4 py-3 font-medium">對話數</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((user) => (
                    <UserRow
                      key={user.id}
                      user={user}
                      isExpanded={expandedUserId === user.id}
                      sessions={expandedUserId === user.id ? sessions : []}
                      sessionsLoading={expandedUserId === user.id && sessionsLoading}
                      editingCredits={editingCreditsId === user.id}
                      editingCreditsValue={editingCreditsValue}
                      flashClass={flashClass(user.id)}
                      onToggleExpand={() => handleExpandUser(user.id)}
                      onAccessRoleChange={(role) => handleAccessRoleChange(user.id, role)}
                      onStartEditCredits={() => startEditingCredits(user.id, user.credits)}
                      onCreditsValueChange={setEditingCreditsValue}
                      onSaveCredits={() => saveCredits(user.id)}
                      onCancelEditCredits={cancelEditingCredits}
                      formatDate={formatDate}
                      roleBadge={roleBadge}
                    />
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            <div className="flex items-center justify-between mt-4 text-sm text-slate-400">
              <span>
                顯示 {startIndex}-{endIndex}，共 {total} 位使用者
              </span>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  className="px-3 py-1.5 rounded bg-slate-700 hover:bg-slate-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors text-xs"
                >
                  上一頁
                </button>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages}
                  className="px-3 py-1.5 rounded bg-slate-700 hover:bg-slate-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors text-xs"
                >
                  下一頁
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

interface UserRowProps {
  user: AdminUser;
  isExpanded: boolean;
  sessions: AdminSession[];
  sessionsLoading: boolean;
  editingCredits: boolean;
  editingCreditsValue: string;
  flashClass: string;
  onToggleExpand: () => void;
  onAccessRoleChange: (role: "admin" | "user") => void;
  onStartEditCredits: () => void;
  onCreditsValueChange: (value: string) => void;
  onSaveCredits: () => void;
  onCancelEditCredits: () => void;
  formatDate: (date: string | null) => string;
  roleBadge: (role: string) => React.ReactNode;
}

function UserRow({
  user,
  isExpanded,
  sessions,
  sessionsLoading,
  editingCredits,
  editingCreditsValue,
  flashClass: flashCls,
  onToggleExpand,
  onAccessRoleChange,
  onStartEditCredits,
  onCreditsValueChange,
  onSaveCredits,
  onCancelEditCredits,
  formatDate,
  roleBadge,
}: UserRowProps) {
  return (
    <>
      <tr
        onClick={onToggleExpand}
        className={`border-b border-slate-800 cursor-pointer hover:bg-slate-800/50 transition-colors ${flashCls}`}
      >
        <td className="px-4 py-3 text-slate-200">{user.email}</td>
        <td className="px-4 py-3">{roleBadge(user.role)}</td>
        <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
          <select
            value={user.access_role}
            onChange={(e) => onAccessRoleChange(e.target.value as "admin" | "user")}
            className="bg-slate-800 border border-slate-600 text-slate-200 text-xs rounded px-2 py-1 outline-none focus:border-blue-500"
          >
            <option value="user">一般使用者</option>
            <option value="admin">管理員</option>
          </select>
        </td>
        <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
          {editingCredits ? (
            <input
              type="number"
              value={editingCreditsValue}
              onChange={(e) => onCreditsValueChange(e.target.value)}
              onBlur={onSaveCredits}
              onKeyDown={(e) => {
                if (e.key === "Enter") onSaveCredits();
                if (e.key === "Escape") onCancelEditCredits();
              }}
              autoFocus
              className="bg-slate-800 border border-blue-500 text-slate-200 text-xs rounded px-2 py-1 w-20 outline-none"
            />
          ) : (
            <button
              onClick={onStartEditCredits}
              className="text-slate-200 hover:text-blue-400 transition-colors tabular-nums"
            >
              {user.credits}
            </button>
          )}
        </td>
        <td className="px-4 py-3 text-slate-400 text-xs">{formatDate(user.last_active)}</td>
        <td className="px-4 py-3 text-slate-300">{user.session_count}</td>
      </tr>

      {/* Expanded sessions panel */}
      {isExpanded && (
        <tr>
          <td colSpan={6} className="bg-[#0f172a] px-6 py-4">
            {sessionsLoading ? (
              <div className="flex items-center gap-2 text-slate-500 text-xs py-2">
                <span className="inline-block w-3 h-3 border-2 border-slate-500 border-t-transparent rounded-full animate-spin" />
                載入中...
              </div>
            ) : sessions.length === 0 ? (
              <div className="text-slate-500 text-xs py-2">尚無對話紀錄</div>
            ) : (
              <div className="space-y-1">
                <div className="text-slate-500 text-[10px] uppercase tracking-wide mb-2">
                  對話紀錄（{sessions.length}）
                </div>
                {sessions.map((s) => (
                  <div
                    key={s.id}
                    className="flex items-center justify-between bg-slate-900/50 rounded px-3 py-2 text-xs"
                  >
                    <span className="text-slate-300 truncate max-w-[40%]">{s.title}</span>
                    <span className="text-slate-500">{s.query_count} 則查詢</span>
                    <span className="text-slate-600">{formatDate(s.created_at)}</span>
                  </div>
                ))}
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  );
}
