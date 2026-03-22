import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "勞基法查詢助手",
  description: "HR 勞基法 RAG 查詢系統",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-TW">
      <body className="bg-slate-900">{children}</body>
    </html>
  );
}
