"use client";
import { useState, useRef, KeyboardEvent, ClipboardEvent } from "react";
import { useRouter } from "next/navigation";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

type Step = "email" | "otp" | "role";

export default function LoginPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("email");
  const [email, setEmail] = useState("");
  const [otp, setOtp] = useState(["", "", "", "", "", ""]);
  const [pendingToken, setPendingToken] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const otpRefs = useRef<(HTMLInputElement | null)[]>([]);

  async function handleSendOtp() {
    setError("");
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/auth/otp/send`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
        credentials: "include",
      });
      if (!res.ok) {
        const data = await res.json();
        setError(data.detail ?? "寄送失敗，請稍後再試");
        return;
      }
      setStep("otp");
    } catch {
      setError("網路錯誤，請稍後再試");
    } finally {
      setLoading(false);
    }
  }

  async function handleVerifyOtp(otpOverride?: string) {
    setError("");
    setLoading(true);
    const otpStr = otpOverride ?? otp.join("");
    try {
      const res = await fetch(`${API_BASE}/api/auth/otp/verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, otp: otpStr }),
        credentials: "include",
      });
      if (!res.ok) {
        const data = await res.json();
        setError(data.detail ?? "驗證失敗");
        return;
      }
      const data = await res.json();
      if (data.is_new_user) {
        setPendingToken(data.pending_token);
        setStep("role");
      } else {
        router.push("/");
      }
    } catch {
      setError("網路錯誤，請稍後再試");
    } finally {
      setLoading(false);
    }
  }

  async function handleRegister(role: "hr" | "employee") {
    setError("");
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pending_token: pendingToken, role }),
        credentials: "include",
      });
      if (!res.ok) {
        const data = await res.json();
        setError(data.detail ?? "註冊失敗");
        return;
      }
      router.push("/");
    } catch {
      setError("網路錯誤，請稍後再試");
    } finally {
      setLoading(false);
    }
  }

  function handleOtpInput(index: number, value: string) {
    if (!/^\d?$/.test(value)) return;
    const next = [...otp];
    next[index] = value;
    setOtp(next);
    if (value && index < 5) {
      otpRefs.current[index + 1]?.focus();
    } else if (value && index === 5 && next.every((d) => d !== "")) {
      handleVerifyOtp(next.join(""));
    }
  }

  function handleOtpKeyDown(index: number, e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Backspace" && !otp[index] && index > 0) {
      otpRefs.current[index - 1]?.focus();
    }
    if (e.key === "Enter" && otp.join("").length === 6) handleVerifyOtp();
  }

  function handleOtpPaste(e: ClipboardEvent<HTMLInputElement>) {
    e.preventDefault();
    const digits = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, 6).split("");
    if (digits.length === 0) return;
    const next = [...otp];
    digits.forEach((d, i) => { next[i] = d; });
    setOtp(next);
    const focusIndex = Math.min(digits.length, 5);
    otpRefs.current[focusIndex]?.focus();
  }

  return (
    <div className="min-h-screen bg-slate-900 flex items-center justify-center p-4">
      <div className="bg-slate-800 rounded-xl p-8 w-full max-w-sm shadow-xl border border-slate-700">
        <h1 className="text-white font-bold text-xl mb-1">勞基法查詢系統</h1>
        <p className="text-slate-400 text-sm mb-6">
          {step === "email" && "輸入 Email 以收取驗證碼"}
          {step === "otp" && `驗證碼已寄至 ${email}`}
          {step === "role" && "請選擇你的身份"}
        </p>

        {error && (
          <div className="bg-red-900/40 border border-red-700 text-red-300 text-sm rounded-lg px-3 py-2 mb-4">
            {error}
          </div>
        )}

        {/* Step 1: Email */}
        {step === "email" && (
          <div className="flex flex-col gap-3">
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSendOtp()}
              placeholder="your@email.com"
              className="bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-white placeholder-slate-500 text-sm focus:outline-none focus:border-blue-500"
            />
            <button
              onClick={handleSendOtp}
              disabled={loading || !email}
              className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded-lg py-2 text-sm font-medium transition-colors"
            >
              {loading ? "寄送中..." : "寄送驗證碼"}
            </button>
          </div>
        )}

        {/* Step 2: OTP */}
        {step === "otp" && (
          <div className="flex flex-col gap-4">
            <div className="flex gap-2 justify-center">
              {otp.map((digit, i) => (
                <input
                  key={i}
                  ref={(el) => { otpRefs.current[i] = el; }}
                  type="text"
                  inputMode="numeric"
                  maxLength={1}
                  value={digit}
                  onChange={(e) => handleOtpInput(i, e.target.value)}
                  onKeyDown={(e) => handleOtpKeyDown(i, e)}
                  onPaste={handleOtpPaste}
                  className="w-10 h-12 bg-slate-900 border border-slate-600 rounded-lg text-center text-white text-lg font-mono focus:outline-none focus:border-blue-500"
                />
              ))}
            </div>
            <button
              onClick={handleVerifyOtp}
              disabled={loading || otp.join("").length !== 6}
              className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded-lg py-2 text-sm font-medium transition-colors"
            >
              {loading ? "驗證中..." : "驗證"}
            </button>
            <button
              onClick={() => { setStep("email"); setOtp(["", "", "", "", "", ""]); setError(""); }}
              className="text-slate-500 hover:text-slate-300 text-xs text-center transition-colors"
            >
              ← 重新輸入 email
            </button>
          </div>
        )}

        {/* Step 3: Role */}
        {step === "role" && (
          <div className="flex flex-col gap-3">
            <button
              onClick={() => handleRegister("hr")}
              disabled={loading}
              className="bg-slate-700 hover:bg-slate-600 border border-slate-600 hover:border-blue-500 text-left rounded-lg p-4 transition-colors disabled:opacity-50"
            >
              <div className="text-white font-medium text-sm">人資（HR）</div>
              <div className="text-slate-400 text-xs mt-1">管理合規、勞資問題</div>
            </button>
            <button
              onClick={() => handleRegister("employee")}
              disabled={loading}
              className="bg-slate-700 hover:bg-slate-600 border border-slate-600 hover:border-blue-500 text-left rounded-lg p-4 transition-colors disabled:opacity-50"
            >
              <div className="text-white font-medium text-sm">員工</div>
              <div className="text-slate-400 text-xs mt-1">了解個人權益</div>
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
