"use client";
import { useEffect, useState } from "react";
import { getLaws } from "@/lib/api";
import { SupportedLaw } from "@/types";

interface Props {
  selectedLawIds: string[]; // [] means all laws selected
  onChange: (ids: string[]) => void;
}

export default function LawScopeSelector({ selectedLawIds, onChange }: Props) {
  const [laws, setLaws] = useState<SupportedLaw[]>([]);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    getLaws().then(setLaws).catch(console.error);
  }, []);

  // [] means all selected; otherwise the array lists the selected law_ids
  const allSelected = selectedLawIds.length === 0;
  const selectedCount = allSelected ? laws.length : selectedLawIds.length;
  const summaryLabel = allSelected || selectedCount === laws.length ? "全部" : `${selectedCount} 部`;

  function toggle(lawId: string) {
    let next: string[];
    if (allSelected) {
      // All selected → deselect just this one
      next = laws.map((l) => l.law_id).filter((id) => id !== lawId);
    } else if (selectedLawIds.includes(lawId)) {
      next = selectedLawIds.filter((id) => id !== lawId);
      // If all deselected → revert to all selected
      if (next.length === 0) next = [];
    } else {
      next = [...selectedLawIds, lawId];
      // If all manually checked → normalize to [] (all selected)
      if (next.length === laws.length) next = [];
    }
    onChange(next);
  }

  function selectAll() {
    onChange([]);
  }

  const isChecked = (lawId: string) => allSelected || selectedLawIds.includes(lawId);

  if (laws.length === 0) return null;

  return (
    <div className="border-t border-slate-800 mt-2 pt-1">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex justify-between items-center px-1 py-1.5 text-left"
      >
        <span className="text-slate-500 text-[10px] uppercase tracking-wide">
          法規範圍{" "}
          <span className="text-blue-400 normal-case font-medium">({summaryLabel})</span>
        </span>
        <span className="text-slate-600 text-[10px]">{expanded ? "▼" : "▶"}</span>
      </button>

      {expanded && (
        <div className="pb-1">
          <div className="flex justify-end px-1 mb-1">
            <button
              onClick={selectAll}
              className="text-blue-500 text-[9px] hover:text-blue-400 transition-colors"
            >
              全選
            </button>
          </div>
          <div className="flex flex-col gap-0.5 max-h-48 overflow-y-auto">
            {laws.map((law) => (
              <label
                key={law.law_id}
                className="flex items-center gap-1.5 px-1 py-0.5 cursor-pointer hover:bg-slate-800 rounded"
              >
                <input
                  type="checkbox"
                  checked={isChecked(law.law_id)}
                  onChange={() => toggle(law.law_id)}
                  className="accent-blue-500 flex-shrink-0"
                />
                <span
                  className={`text-[10px] leading-tight ${
                    isChecked(law.law_id) ? "text-slate-300" : "text-slate-500"
                  }`}
                >
                  {law.law_name}
                </span>
              </label>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
