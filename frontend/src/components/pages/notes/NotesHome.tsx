"use client";
// 笔记首页（未选笔记时的中栏）：统计卡、今日到期温故（记得/模糊/忘了）、
// 未解析链接（一键建笔记）、最近编辑。
import { useEffect, useState } from "react";
import {
  ArrowRight, Brain, FileText, Link2, NotebookPen, Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { cn } from "@/lib/cn";
import { getDueReviews, submitNoteReview } from "@/lib/api-notes";
import { relTime } from "@/lib/format";
import type { DueReview, VaultSnapshot } from "@/lib/types-notes";

export function NotesHome({
  vault, tr, lang, onOpenNote, onCreateNote, onGenerate, onVaultChanged,
}: {
  vault: VaultSnapshot;
  tr: (k: string, fallback?: string) => string;
  lang: "zh" | "en";
  onOpenNote: (id: string) => void;
  onCreateNote: (title: string) => void;
  onGenerate: () => void;
  onVaultChanged: () => void;
}) {
  const [due, setDue] = useState<DueReview[]>([]);
  const [reviewing, setReviewing] = useState<string | null>(null);

  const loadDue = () => {
    void getDueReviews().then((r) => setDue(r.due)).catch(() => setDue([]));
  };
  useEffect(loadDue, [vault.stats.due_review_count]);

  const review = async (noteId: string, quality: number) => {
    setReviewing(noteId);
    try {
      await submitNoteReview(noteId, quality);
    } catch { /* inline degrade */ } finally {
      setReviewing(null);
      loadDue();
      onVaultChanged();
    }
  };

  const stats = vault.stats;
  const recent = vault.notes.slice(0, 6);

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6">
      {/* 统计 */}
      <div className="grid grid-cols-3 gap-3">
        <StatCard icon={<FileText size={15} />} label={tr("home.stats.notes")}
          value={stats.note_count} tone="accent" />
        <StatCard icon={<Link2 size={15} />} label={tr("home.stats.links")}
          value={stats.link_count} tone="info" />
        <StatCard icon={<Brain size={15} />} label={tr("home.stats.due")}
          value={stats.due_review_count} tone={stats.due_review_count > 0 ? "accent2" : "muted"} />
      </div>

      {/* 今日温故 */}
      <section className="mt-6">
        <h3 className="mb-1 text-sm font-semibold text-fg">{tr("home.due.title")}</h3>
        <p className="mb-2.5 text-[11px] text-muted">{tr("home.due.desc")}</p>
        {due.length === 0 ? (
          <div className="rounded-[10px] border border-dashed border-border px-4 py-4 text-center text-xs text-muted">
            {tr("home.due.empty")}
          </div>
        ) : (
          <div className="space-y-2">
            {due.map(({ note }) => (
              <div key={note.id}
                className="flex flex-wrap items-center gap-2 rounded-[10px] border border-border bg-surface px-3 py-2.5">
                <NotebookPen size={14} className="text-accent2" />
                <button
                  onClick={() => onOpenNote(note.id)}
                  className="min-w-0 flex-1 cursor-pointer truncate text-left text-xs font-medium text-fg hover:text-accent">
                  {note.title}
                </button>
                <span className="text-[10px] text-muted tnum">
                  {tr("tb.words", "{n} 字").replace("{n}", String(note.word_count))}
                  {" · SM-2 ×"}{note.review.repetitions}
                </span>
                <div className="flex gap-1">
                  {([["remember", 5], ["fuzzy", 3], ["forgot", 1]] as const)
                    .map(([key, q]) => (
                      <Button key={key} variant="outline" size="sm" disabled={reviewing === note.id}
                        className={cn(
                          q === 5 && "hover:border-success hover:text-success",
                          q === 3 && "hover:border-warning hover:text-warning",
                          q === 1 && "hover:border-danger hover:text-danger",
                        )}
                        onClick={() => void review(note.id, q)}>
                        {tr(`home.due.${key}`)}
                      </Button>
                    ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* 未解析链接 */}
        <section>
          <h3 className="mb-1 text-sm font-semibold text-fg">{tr("home.unresolved.title")}</h3>
          <p className="mb-2.5 text-[11px] text-muted">{tr("home.unresolved.desc")}</p>
          {stats.unresolved_links.length === 0 ? (
            <div className="rounded-[10px] border border-dashed border-border px-4 py-4 text-center text-xs text-muted">
              —
            </div>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {stats.unresolved_links.slice(0, 16).map((title) => (
                <button key={title}
                  onClick={() => onCreateNote(title)}
                  className="flex cursor-pointer items-center gap-1 rounded-full border border-dashed border-border px-2.5 py-1 text-xs text-muted transition-colors hover:border-accent2 hover:text-accent2">
                  <Link2 size={11} /> {title}
                </button>
              ))}
            </div>
          )}
        </section>

        {/* 最近编辑 */}
        <section>
          <h3 className="mb-2.5 text-sm font-semibold text-fg">{tr("home.recent.title")}</h3>
          {recent.length === 0 ? (
            <EmptyState
              icon={<NotebookPen size={22} />}
              title={tr("notes.empty.title")}
              desc={tr("notes.empty.desc")}
              action={
                <Button size="sm" variant="accent2" icon={<Sparkles size={13} />} onClick={onGenerate}>
                  {tr("notes.generate")}
                </Button>
              }
            />
          ) : (
            <div className="space-y-1">
              {recent.map((n) => (
                <button key={n.id}
                  onClick={() => onOpenNote(n.id)}
                  className="group flex w-full cursor-pointer items-center gap-2 rounded-[8px] px-2 py-1.5 text-left transition-colors hover:bg-surface-hover">
                  <FileText size={12} className="shrink-0 text-muted" />
                  <span className="min-w-0 flex-1 truncate text-xs text-fg">{n.title}</span>
                  {n.review.enabled && <NotebookPen size={10} className="shrink-0 text-accent2" />}
                  <span className="shrink-0 text-[10px] text-muted">{relTime(n.updated_at, lang)}</span>
                  <ArrowRight size={11} className="shrink-0 text-muted opacity-0 transition-opacity group-hover:opacity-100" />
                </button>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function StatCard({
  icon, label, value, tone,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  tone: "accent" | "info" | "accent2" | "warning" | "muted";
}) {
  const tones = {
    accent: "text-accent bg-accent-soft",
    info: "text-info bg-info/10",
    accent2: "text-accent2 bg-accent2/10",
    warning: "text-warning bg-warning/10",
    muted: "text-muted bg-surface-hover",
  } as const;
  return (
    <div className="flex items-center gap-3 rounded-[10px] border border-border bg-surface px-3.5 py-3 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md">
      <span className={cn("flex size-8 items-center justify-center rounded-lg", tones[tone])}>
        {icon}
      </span>
      <div>
        <div className="text-lg font-semibold text-fg tnum leading-none">{value}</div>
        <div className="mt-1 text-[11px] text-muted">{label}</div>
      </div>
    </div>
  );
}
