"use client";

// /docs 使用文档：全员可读（复用 chat 的 Markdown 渲染，GFM/公式零新依赖），
// 管理员可页内编辑（textarea + 实时预览 + 保存 → PUT /docs/content）。
import { useCallback, useEffect, useState } from "react";
import { BookOpen, Check, Pencil, X } from "lucide-react";
import { Markdown } from "@/components/chat/markdown";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { ErrorNote, PageSkeleton } from "@/components/ui/EmptyState";
import { getDocsContent, putDocsContent } from "@/lib/api-modules";
import { relTime } from "@/lib/format";
import { makePageT } from "@/lib/i18n-page";
import { useAuthStore } from "@/lib/auth-store";
import { useUIStore } from "@/lib/store";
import type { Lang } from "@/lib/i18n";
import { STRINGS } from "./strings";

export default function DocsPage() {
  const { lang } = useUIStore();
  const user = useAuthStore((s) => s.user);
  const tr = makePageT(lang, STRINGS);
  const isAdmin = user?.role === "admin";

  const [doc, setDoc] = useState<{ markdown: string; updated_at: number; updated_by: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [showPreview, setShowPreview] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    setError(false);
    getDocsContent()
      .then((r) => {
        setDoc({ markdown: r.markdown, updated_at: r.updated_at, updated_by: r.updated_by });
      })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    void Promise.resolve().then(() => load());
  }, [load]);

  const startEdit = () => {
    setDraft(doc?.markdown ?? "");
    setSaveError(false);
    setEditing(true);
  };

  const save = async () => {
    setSaving(true);
    setSaveError(false);
    try {
      const r = await putDocsContent(draft);
      setDoc({ markdown: r.markdown, updated_at: r.updated_at, updated_by: r.updated_by });
      setEditing(false);
    } catch {
      setSaveError(true);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="h-full overflow-y-auto p-6 page-in">
      <div className="mx-auto flex max-w-[880px] flex-col gap-4">
        <header className="flex items-end justify-between gap-3">
          <div>
            <h1 className="font-serif text-xl font-semibold text-fg">{tr("docs.title")}</h1>
            <p className="mt-0.5 text-xs text-muted">{tr("docs.desc")}</p>
          </div>
          {isAdmin && !editing && (
            <Button size="sm" variant="outline" icon={<Pencil size={13} />} onClick={startEdit}>
              {tr("docs.edit")}
            </Button>
          )}
        </header>

        {loading && <PageSkeleton />}
        {!loading && error && <ErrorNote message={tr("docs.loadFail")} retry={load} />}

        {!loading && !error && editing && (
          <Card>
            <CardHeader
              icon={<Pencil size={16} />}
              title={tr("docs.edit")}
              right={
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setShowPreview((v) => !v)}
                  >
                    {showPreview ? tr("docs.source") : tr("docs.preview")}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    icon={<X size={13} />}
                    disabled={saving}
                    onClick={() => setEditing(false)}
                  >
                    {tr("docs.cancel")}
                  </Button>
                  <Button
                    size="sm"
                    icon={saving ? undefined : <Check size={13} />}
                    disabled={saving}
                    onClick={() => void save()}
                  >
                    {saving ? tr("docs.saving") : tr("docs.save")}
                  </Button>
                </div>
              }
            />
            {saveError && (
              <div className="mb-3">
                <ErrorNote message={tr("docs.saveFail")} />
              </div>
            )}
            <div className={showPreview ? "grid grid-cols-1 gap-4 lg:grid-cols-2" : ""}>
              <textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder={tr("docs.ph")}
                spellCheck={false}
                className="h-[62vh] min-h-[320px] w-full resize-none rounded-[8px] border border-border-light bg-surface-sunken p-3 font-mono text-[13px] leading-relaxed text-fg outline-none focus:border-accent"
              />
              {showPreview && (
                <div className="h-[62vh] min-h-[320px] overflow-y-auto rounded-[8px] border border-border-light bg-surface p-3">
                  <Markdown>{draft || tr("docs.ph")}</Markdown>
                </div>
              )}
            </div>
          </Card>
        )}

        {!loading && !error && !editing && doc && (
          <Card>
            <CardHeader icon={<BookOpen size={16} />} title={tr("docs.title")} />
            {doc.markdown ? (
              <Markdown>{doc.markdown}</Markdown>
            ) : (
              <p className="text-sm text-muted">{tr("docs.empty")}</p>
            )}
            {doc.updated_at > 0 && (
              <div className="mt-2 border-t border-border-light pt-2 text-[11px] text-muted">
                {tr("docs.updated")} {relTime(doc.updated_at, lang as Lang)}
                {doc.updated_by && (
                  <>
                    {" "}{tr("docs.updatedBy")} {doc.updated_by}
                  </>
                )}
              </div>
            )}
          </Card>
        )}
      </div>
    </div>
  );
}
