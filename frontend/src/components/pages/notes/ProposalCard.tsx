"use client";
// 修改提案卡（协作模式）：LCS 行 diff 预览（replace）或追加片段高亮（append）
// + 确认应用 / 拒绝；已处理过的提案以状态徽标收尾。渲染在助手对话流内。
import { useState } from "react";
import { Check, Diff, X } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import { lineDiff } from "./editorActions";
import type { NoteSuggestion } from "@/lib/types-notes";

export function ProposalCard({
  proposal,
  currentContent,
  noteTitle,
  tr,
  onApply,
  onDismiss,
}: {
  proposal: NoteSuggestion;
  currentContent: string;
  noteTitle?: string;
  tr: (k: string, fallback?: string) => string;
  onApply: (id: string) => Promise<void> | void;
  onDismiss: (id: string) => Promise<void> | void;
}) {
  const [busy, setBusy] = useState(false);
  const [showDiff, setShowDiff] = useState(false);
  const merged = proposal.kind === "replace"
    ? proposal.proposed_content
    : currentContent.replace(/\s+$/, "") + "\n\n" + proposal.proposed_content.replace(/^\s+/, "");
  const diff = lineDiff(currentContent, merged);
  const decided = proposal.status !== "pending";

  return (
    <div className={cn(
      "rounded-[10px] border border-border border-l-2 bg-surface p-3 shadow-sm",
      decided ? "border-l-border-light opacity-80" : "border-l-accent",
    )}>
      <div className="mb-1.5 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <span className={cn(
              "rounded-md px-1.5 py-0.5 text-[10px]",
              proposal.kind === "replace"
                ? "bg-accent2/10 text-accent2" : "bg-success/10 text-success",
            )}>
              {proposal.kind === "replace"
                ? tr("ai.proposal.replace") : tr("ai.proposal.append")}
            </span>
            {noteTitle && (
              <span className="truncate text-xs font-medium text-fg">{noteTitle}</span>
            )}
          </div>
          <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-fg-secondary">
            {proposal.summary}
          </p>
        </div>
        {proposal.status === "applied" && (
          <span className="flex shrink-0 items-center gap-0.5 rounded-md bg-success/10 px-1.5 py-0.5 text-[10px] text-success">
            <Check size={10} /> {tr("ai.proposal.applied")}
          </span>
        )}
        {proposal.status === "dismissed" && (
          <span className="flex shrink-0 items-center gap-0.5 rounded-md bg-surface-hover px-1.5 py-0.5 text-[10px] text-muted">
            <X size={10} /> {tr("ai.proposal.dismissed")}
          </span>
        )}
      </div>
      <button
        onClick={() => setShowDiff((v) => !v)}
        className="mb-2 flex cursor-pointer items-center gap-1 text-[11px] text-muted transition-colors hover:text-accent"
      >
        <Diff size={12} /> {tr("ai.proposal.diff")}
      </button>
      {showDiff && (
        <div className="mb-2 max-h-64 overflow-y-auto rounded-md border border-border bg-bg p-2 font-mono text-[11px] leading-relaxed">
          {diff.length === 0 && (
            <div className="text-muted">（{tr("ai.proposal.append")} · {proposal.proposed_content.slice(0, 200)}…）</div>
          )}
          {diff.map((l, i) => (
            <div
              key={i}
              className={cn(
                "whitespace-pre-wrap break-all",
                l.kind === "add" && "bg-success/10 text-success",
                l.kind === "del" && "bg-danger/10 text-danger",
                l.kind === "same" && "text-muted",
              )}
            >
              {l.kind === "add" ? "+ " : l.kind === "del" ? "- " : "  "}
              {l.text}
            </div>
          ))}
        </div>
      )}
      {!decided && (
        <div className="flex justify-end gap-1.5">
          <Button
            variant="ghost" size="sm" disabled={busy}
            icon={<X size={13} />}
            onClick={async () => { setBusy(true); await onDismiss(proposal.id); setBusy(false); }}
          >
            {tr("ai.proposal.dismiss")}
          </Button>
          <Button
            variant="primary" size="sm" disabled={busy}
            icon={<Check size={13} />}
            onClick={async () => { setBusy(true); await onApply(proposal.id); setBusy(false); }}
          >
            {tr("ai.proposal.apply")}
          </Button>
        </div>
      )}
    </div>
  );
}
