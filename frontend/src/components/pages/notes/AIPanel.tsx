"use client";
// 笔记助手面板（VSCode Copilot 式）：对话线程（SSE 流式）+ 内联修改提案卡
// （协作模式）+ 计划批复条（计划模式）。确认动作集中在输入框区域（ZCode 式），
// 模式选择器在输入框左下角：计划 / 协作 / 完全授权 / 聊天问答。
// 支持图片附件：上传（/notes/upload，OCR 预览）→ 发送时包 <ocr_material>
// 前缀 + attachments（MULTIMODAL 配置时走视觉通道）。
import { useEffect, useRef, useState } from "react";
import type { LucideIcon } from "lucide-react";
import {
  Bot, Check, ChevronDown, CircleStop, ClipboardList, Eraser, FileText,
  MessageSquarePlus, Pencil, Trash2,
  HelpCircle, ImagePlus, Loader2, PanelRightClose, PencilLine, ScanLine,
  Send, Sparkles, Wrench, X, Zap,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { MiniMarkdown } from "@/components/chat/markdown";
import { useClickOutside } from "@/components/sidebar/Dropdown";
import { cn } from "@/lib/cn";
import {
  applySuggestion, clearNotesThread, createNotesThread, deleteNotesThread,
  dismissSuggestion, getSuggestions, notesChatStream, notesUpload, patchNotesThread,
} from "@/lib/api-notes";
import { useNotesStore } from "@/lib/store-notes";
import type { AgentMode, NoteSuggestion } from "@/lib/types-notes";
import { ProposalCard } from "./ProposalCard";

const MODES: { key: AgentMode; icon: LucideIcon; labelKey: string; descKey: string }[] = [
  { key: "plan", icon: ClipboardList, labelKey: "ai.mode.plan", descKey: "ai.mode.plan.desc" },
  { key: "collab", icon: PencilLine, labelKey: "ai.mode.collab", descKey: "ai.mode.collab.desc" },
  { key: "auto", icon: Zap, labelKey: "ai.mode.auto", descKey: "ai.mode.auto.desc" },
  { key: "ask", icon: HelpCircle, labelKey: "ai.mode.ask", descKey: "ai.mode.ask.desc" },
];

function stageLabel(stage: string): string {
  return ({ thinking: "正在分析", analyzing: "正在分析", retrieving: "正在检索教材",
    collecting: "正在整理上下文", drafting: "正在生成修改提案", writing: "正在写入笔记" } as Record<string, string>)[stage] || stage;
}

function toolLabel(name: string): string {
  return ({ knowledge_search: "正在检索教材", notes_read: "正在读取笔记",
    notes_search: "正在检索笔记仓库", notes_propose: "正在生成修改提案",
    notes_write: "正在写入笔记", notes_create: "正在创建笔记" } as Record<string, string>)[name] || `正在执行 ${name}`;
}

export function AIPanel({
  tr,
  onRemoteUpdate,
  onVaultChanged,
}: {
  tr: (k: string, fallback?: string) => string;
  onRemoteUpdate: (noteId: string, content: string, revision: number, title: string) => void;
  onVaultChanged: () => void;
}) {
  const {
    currentId, detail, agentMode, setAgentMode, thread, loadThread, loadThreads,
    threads, activeThreadId, setActiveThread, vault, toggleAiPanel,
  } = useNotesStore();
  const [input, setInput] = useState("");
  const [proposals, setProposals] = useState<NoteSuggestion[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [streamAnswer, setStreamAnswer] = useState("");
  const [pendingUser, setPendingUser] = useState("");
  const [streamStep, setStreamStep] = useState("");
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const [modeMenuOpen, setModeMenuOpen] = useState(false);
  const [imgAttachments, setImgAttachments] = useState<{ id: string; filename: string }[]>([]);
  const [ocrText, setOcrText] = useState("");
  const [ocrLoading, setOcrLoading] = useState(false);
  const [imgError, setImgError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const modeMenuRef = useClickOutside<HTMLDivElement>(
    () => setModeMenuOpen(false), modeMenuOpen);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const pendingProposals = proposals.filter((p) => p.status === "pending");
  const lastMsg = thread[thread.length - 1];
  const hasPlan = agentMode === "plan" && !streaming
    && lastMsg?.role === "assistant" && Boolean(lastMsg.content.trim());
  const activeMode = MODES.find((m) => m.key === agentMode) ?? MODES[1];

  useEffect(() => { void loadThreads().then(() => loadThread()); }, [loadThread, loadThreads]);
  useEffect(() => {
    let alive = true;
    getSuggestions("pending")
      .then((r) => { if (alive) setProposals(r.suggestions); })
      .catch(() => { /* keep old */ });
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [thread.length, streamAnswer, proposals.length]);

  const handleImage = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    if (imgAttachments.length >= 3) {
      setImgError(tr("ai.upload.limit", "最多 {n} 张图片").replace("{n}", "3"));
      return;
    }
    const img = files[0];
    const isImg = /^image\/(png|jpe?g|webp|bmp|tiff)$/i.test(img.type)
      || /\.(png|jpe?g|webp|bmp|tiff)$/i.test(img.name);
    if (!isImg) {
      setImgError(tr("ai.upload.unsupported"));
      return;
    }
    setImgError("");
    setOcrLoading(true);
    try {
      const res = await notesUpload([img]);
      const okr = res.results.filter((r) => r.id && !r.error);
      if (okr.length === 0) {
        setImgError(res.results[0]?.error || tr("ai.error"));
      } else {
        setImgAttachments((prev) => [
          ...prev, { id: okr[0].id!, filename: okr[0].filename },
        ]);
        const preview = okr[0]?.preview_text?.trim() || "";
        if (preview) setOcrText(preview);
      }
    } catch (e) {
      setImgError("OCR: " + (e instanceof Error ? e.message : String(e)));
    } finally {
      setOcrLoading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const send = async (action = "") => {
    if (streaming) return;
    const trimmed = input.trim();
    const ocr = ocrText.trim();
    if (!action && !trimmed && !ocr && imgAttachments.length === 0) return;
    const message = ocr
      ? `<ocr_material>${ocr}</ocr_material>\n\n${trimmed || tr("ai.img.default")}`
      : trimmed;
    const attachments = [...imgAttachments];
    const draft = { input, ocrText, attachments: [...imgAttachments] };
    setOcrText("");
    setImgAttachments([]);
    setImgError("");
    setError("");
    setStreamAnswer("");
    setStreaming(true);
    const controller = new AbortController();
    abortRef.current = controller;
    useNotesStore.setState({ aiStreaming: true });
    let completed = false;
    try {
      const context = currentId
        ? { note_id: currentId, scope: "note" }
        : { scope: "vault" };
      for await (const ev of notesChatStream(
        {
          message, context, mode: agentMode, action,
          attachments: attachments.length > 0 ? attachments : undefined,
          thread_id: activeThreadId,
        }, controller.signal)) {
        switch (ev.type) {
          case "run_start":
            setInput("");
            setPendingUser(message);
            setStreamStep(tr("ai.analyzing", "正在分析"));
            break;
          case "answer":
            if (ev.is_delta) setStreamAnswer((prev) => prev + String(ev.content ?? ""));
            break;
          case "step":
            setStreamStep(stageLabel(String(ev.stage ?? "")));
            break;
          case "tool_start":
            setStreamStep(toolLabel(String(ev.name ?? "")));
            break;
          case "note_updated":
            onRemoteUpdate(String(ev.note_id ?? ""), String(ev.content ?? ""),
              Number(ev.revision ?? 0), String(ev.title ?? ""));
            setToast(tr("ai.updated", "助手已更新《{title}》").replace("{title}", String(ev.title ?? "")));
            setTimeout(() => setToast(""), 4000);
            break;
          case "note_suggestion": {
            const sg = ev.suggestion as NoteSuggestion | undefined;
            if (sg) setProposals((prev) => [sg, ...prev]);
            onVaultChanged();
            break;
          }
          case "error":
            setError(String(ev.message ?? tr("ai.error")));
            setInput((current) => current || draft.input);
            setOcrText((current) => current || draft.ocrText);
            setImgAttachments((current) => current.length > 0 ? current : draft.attachments);
            break;
          case "done":
            completed = true;
            setStreamAnswer("");
            break;
          default:
            break;
        }
      }
    } catch (e) {
      setInput((current) => current || draft.input);
      setOcrText((current) => current || draft.ocrText);
      setImgAttachments((current) => current.length > 0 ? current : draft.attachments);
      if (!(e instanceof DOMException && e.name === "AbortError")) {
        setError(e instanceof Error ? e.message : tr("ai.error"));
      }
    } finally {
      if (!completed) {
        setInput((current) => current || draft.input);
        setOcrText((current) => current || draft.ocrText);
        setImgAttachments((current) => current.length > 0 ? current : draft.attachments);
      }
      setStreaming(false);
      setStreamStep("");
      abortRef.current = null;
      useNotesStore.setState({ aiStreaming: false, pendingAnswer: "" });
      void loadThread(activeThreadId).finally(() => setPendingUser(""));
      void loadThreads();
    }
  };

  const setProposalStatus = (id: string, status: NoteSuggestion["status"]) => {
    setProposals((prev) => prev.map((p) => (p.id === id ? { ...p, status } : p)));
  };

  const applyOne = async (id: string) => {
    try {
      const r = await applySuggestion(id);
      setProposalStatus(id, "applied");
      onVaultChanged();
      void loadThread();
      onRemoteUpdate(r.note.id, r.content, r.note.revision, r.note.title);
    } catch { /* inline degrade */ }
  };

  const dismissOne = async (id: string) => {
    try {
      await dismissSuggestion(id);
      setProposalStatus(id, "dismissed");
      onVaultChanged();
      void loadThread();
    } catch { /* ignore */ }
  };

  const applyAll = async () => {
    for (const p of pendingProposals) await applyOne(p.id);
  };

  const noteTitle = (id: string) =>
    vault?.notes.find((n) => n.id === id)?.title ?? detail?.note.title;

  return (
    <div className="flex h-full w-full flex-col border-l border-border bg-surface">
      {/* 头部：线程 + 当前上下文 + 面板动作 */}
      <div className="border-b border-border px-3 py-2">
        <div className="flex items-center gap-1.5">
          <Bot size={14} className="shrink-0 text-accent" />
          <select
            value={activeThreadId}
            disabled={streaming}
            onChange={(e) => void setActiveThread(e.target.value)}
            className="min-w-0 flex-1 truncate rounded-md border border-border bg-bg px-2 py-1 text-xs text-fg outline-none focus:border-accent"
          >
            {threads.map((item) => <option key={item.thread_id} value={item.thread_id}>{item.title}</option>)}
          </select>
          <button title="新建线程" className="rounded-md p-1.5 text-muted hover:bg-surface-hover hover:text-accent" onClick={() => void createNotesThread().then(({ thread: item }) => loadThreads().then(() => setActiveThread(item.thread_id)))}><MessageSquarePlus size={13} /></button>
          <button title="重命名线程" className="rounded-md p-1.5 text-muted hover:bg-surface-hover hover:text-accent" onClick={() => { const current = threads.find((item) => item.thread_id === activeThreadId); const title = window.prompt("线程名称", current?.title || ""); if (title?.trim()) void patchNotesThread(activeThreadId, { title }).then(() => loadThreads()); }}><Pencil size={13} /></button>
          {activeThreadId !== "default" && <button title="删除线程" className="rounded-md p-1.5 text-muted hover:bg-danger/10 hover:text-danger" onClick={() => { if (window.confirm("删除当前线程？正文中的链接会保留并显示失效。")) void deleteNotesThread(activeThreadId).then(() => loadThreads().then(() => setActiveThread("default"))); }}><Trash2 size={13} /></button>}
          <button
            onClick={() => { if (window.confirm(tr("ai.clear.confirm"))) void clearNotesThread(activeThreadId).then(() => loadThread(activeThreadId)); }}
            title={tr("ai.clear")} aria-label={tr("ai.clear")}
            className="rounded-md p-1.5 text-muted hover:bg-danger/10 hover:text-danger"
          ><Eraser size={13} /></button>
          <button onClick={toggleAiPanel} title={tr("tb.toggleAi")} className="rounded-md p-1.5 text-muted hover:bg-surface-hover hover:text-accent"><PanelRightClose size={14} /></button>
        </div>
        <div className="mt-1.5 flex min-w-0 flex-wrap items-center gap-1">
          <span className="flex min-w-0 items-center gap-1 rounded-md bg-accent-soft px-1.5 py-0.5 text-[10px] text-accent-strong">
            {currentId ? <FileText size={10} /> : <Sparkles size={10} />}
            <span className="truncate">{currentId ? `${tr("ai.context.note")} · ${detail?.note.title || ""}` : tr("ai.context.vault")}</span>
          </span>
          <span className="rounded-md bg-surface-hover px-1.5 py-0.5 text-[10px] text-muted">仓库 · {vault?.notes.length || 0} 篇</span>
        </div>
      </div>

      {/* 对话线程 */}
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 py-3">
        {thread.length === 0 && !streaming && (
          <div className="py-8 text-center text-xs text-muted">
            {tr("ai.placeholder")}
          </div>
        )}
        {thread.map((m, i) => (
          <div key={`${m.ts}-${i}`} className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}>
            <div className={cn(
              "max-w-[92%] rounded-[10px] px-2.5 py-1.5 text-xs leading-relaxed",
              m.role === "user" ? "bg-accent-soft text-fg" : "border border-border bg-bg text-fg-secondary",
            )}>
              {m.content.length > 1400 ? <details><summary className="cursor-pointer text-[10px] text-muted">展开完整消息</summary><div className="mt-1"><MiniMarkdown>{m.content}</MiniMarkdown></div></details> : <MiniMarkdown>{m.content}</MiniMarkdown>}
            </div>
          </div>
        ))}
        {pendingUser && <div className="flex justify-end"><div className="max-w-[92%] rounded-[10px] bg-accent-soft px-2.5 py-1.5 text-xs text-fg opacity-80"><MiniMarkdown>{pendingUser}</MiniMarkdown></div></div>}
        {pendingProposals.map((sg) => (
          <ProposalCard
            key={sg.id}
            proposal={sg}
            currentContent={sg.note_id === currentId ? (detail?.content ?? "") : ""}
            noteTitle={noteTitle(sg.note_id)}
            tr={tr}
            onApply={applyOne}
            onDismiss={dismissOne}
          />
        ))}
        {streaming && (
          <div className="flex justify-start">
            <div className="max-w-[92%] rounded-[10px] border border-border bg-bg px-2.5 py-1.5 text-xs leading-relaxed text-fg-secondary">
              {streamStep && (
                <div className="mb-1 flex items-center gap-1 text-[10px] text-muted">
                  <Wrench size={10} className="animate-pulse" /> {streamStep}
                </div>
              )}
              {streamAnswer ? <MiniMarkdown>{streamAnswer}</MiniMarkdown>
                : <span className="dot-loader" />}
            </div>
          </div>
        )}
        {error && <div className="text-xs text-danger">{error}</div>}
        {toast && (
          <div className="rounded-md bg-success/10 px-2 py-1 text-[11px] text-success">
            {toast}
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* 输入区：确认中枢 + 模式选择器 */}
      <div className="border-t border-border px-3 py-2">
        {hasPlan && (
          <div className="mb-2 flex items-center gap-1.5 rounded-md border border-accent/30 bg-accent-soft/60 px-2 py-1.5">
            <ClipboardList size={12} className="shrink-0 text-accent-strong" />
            <span className="min-w-0 flex-1 truncate text-[11px] text-accent-strong">
              {tr("ai.plan.pending")}
            </span>
            <Button
              variant="primary" size="sm" icon={<Check size={12} />}
              disabled={streaming}
              onClick={() => void send("approve_plan")}
            >
              {tr("ai.plan.approve")}
            </Button>
          </div>
        )}
        {agentMode === "collab" && pendingProposals.length > 0 && !streaming && (
          <div className="mb-2 flex items-center gap-1.5 rounded-md border border-accent2/30 bg-accent2/5 px-2 py-1.5">
            <span className="min-w-0 flex-1 truncate text-[11px] text-fg-secondary">
              {tr("ai.proposal.pendingBar", "待确认修改 {n} 条").replace(
                "{n}", String(pendingProposals.length))}
            </span>
            <Button
              variant="ghost" size="sm" icon={<X size={12} />}
              onClick={() => {
                for (const p of pendingProposals) void dismissOne(p.id);
              }}
            >
              {tr("ai.proposal.dismissAll")}
            </Button>
            <Button
              variant="primary" size="sm" icon={<Check size={12} />}
              onClick={() => void applyAll()}
            >
              {tr("ai.proposal.applyAll")}
            </Button>
          </div>
        )}
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
          placeholder={tr("ai.placeholder")}
          rows={2}
          className="max-h-28 min-h-[2.4rem] w-full resize-none rounded-[8px] border border-border bg-bg px-2.5 py-1.5 text-xs text-fg outline-none focus:border-accent"
        />
        {/* 图片附件：OCR 预览卡 + 附件 chips（随下一条消息一并提交） */}
        {ocrLoading && (
          <div className="mt-1.5 flex items-center gap-2 rounded-[8px] border border-accent/25 bg-accent-soft/30 px-2.5 py-1.5">
            <Loader2 size={12} className="animate-spin text-accent" />
            <span className="text-[11px] text-fg-secondary">{tr("ai.upload.ocr")}</span>
          </div>
        )}
        {ocrText && !ocrLoading && (
          <div className="mt-1.5 rounded-[8px] border border-accent/25 bg-accent-soft/30 px-2.5 py-1.5">
            <div className="flex items-center gap-1.5">
              <ScanLine size={12} className="shrink-0 text-accent" />
              <span className="flex-1 text-[10px] font-medium text-accent-strong">
                {tr("ai.ocr.preview")}
              </span>
              <button
                onClick={() => setOcrText("")}
                className="cursor-pointer text-muted transition-colors hover:text-danger"
                aria-label="clear OCR text"
              >
                <X size={12} />
              </button>
            </div>
            <p className="mt-1 max-h-20 overflow-y-auto whitespace-pre-wrap text-[11px] leading-relaxed text-fg-secondary">
              {ocrText}
            </p>
          </div>
        )}
        {imgAttachments.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {imgAttachments.map((a) => (
              <span key={a.id} className="flex items-center gap-1 rounded-md border border-border bg-bg px-1.5 py-0.5 text-[11px] text-fg-secondary">
                <ImagePlus size={11} className="shrink-0 text-accent" />
                <span className="max-w-36 truncate">{a.filename}</span>
                <button
                  onClick={() => setImgAttachments((prev) => prev.filter((x) => x.id !== a.id))}
                  className="cursor-pointer text-muted transition-colors hover:text-danger"
                  aria-label={`remove ${a.filename}`}
                >
                  <X size={11} />
                </button>
              </span>
            ))}
          </div>
        )}
        {imgError && <div className="mt-1.5 text-[11px] text-danger">{imgError}</div>}
        <div className="mt-1.5 flex items-center gap-1.5">
          <input
            ref={fileRef}
            type="file"
            accept="image/png,image/jpeg,image/webp,image/bmp,image/tiff"
            className="hidden"
            onChange={(e) => { void handleImage(e.target.files); }}
          />
          <button
            onClick={() => fileRef.current?.click()}
            title={tr("ai.upload")}
            aria-label={tr("ai.upload")}
            className="shrink-0 cursor-pointer rounded-md p-1.5 text-muted transition-colors hover:bg-surface-hover hover:text-accent"
          >
            <ImagePlus size={14} />
          </button>
          {/* 模式选择器（VSCode 式，输入框左下角） */}
          <div className="relative shrink-0" ref={modeMenuRef}>
            <button
              onClick={() => setModeMenuOpen((v) => !v)}
              title={tr("ai.mode.pick")}
              className="flex cursor-pointer items-center gap-1 rounded-md border border-border px-1.5 py-1 text-[11px] text-fg-secondary transition-colors hover:border-accent hover:text-accent"
            >
              <activeMode.icon size={12} className="text-accent" />
              {tr(activeMode.labelKey)}
              <ChevronDown size={10} className="text-muted" />
            </button>
            {modeMenuOpen && (
              <div className="absolute bottom-8 left-0 z-30 w-64 rounded-[10px] border border-border bg-surface p-1 shadow-lg">
                {MODES.map((m) => (
                  <button
                    key={m.key}
                    onClick={() => { setAgentMode(m.key); setModeMenuOpen(false); }}
                    className={cn(
                      "flex w-full cursor-pointer items-start gap-2 rounded-md px-2 py-1.5 text-left transition-colors",
                      agentMode === m.key ? "bg-accent-soft" : "hover:bg-surface-hover",
                    )}
                  >
                    <m.icon size={13} className={cn(
                      "mt-0.5 shrink-0",
                      agentMode === m.key ? "text-accent-strong" : "text-muted",
                    )} />
                    <span className="min-w-0">
                      <span className={cn(
                        "block text-xs",
                        agentMode === m.key ? "font-medium text-accent-strong" : "text-fg",
                      )}>
                        {tr(m.labelKey)}
                      </span>
                      <span className="block text-[10px] leading-snug text-muted">
                        {tr(m.descKey)}
                      </span>
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="ml-auto shrink-0">
            {streaming ? (
              <Button variant="outline" size="sm" icon={<CircleStop size={13} />}
                onClick={() => abortRef.current?.abort()}>
                {tr("ai.stop")}
              </Button>
            ) : (
              <Button variant="primary" size="sm" icon={<Send size={13} />}
                disabled={!input.trim() && !ocrText.trim() && imgAttachments.length === 0}
                onClick={() => void send()}>
                {tr("ai.send")}
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
