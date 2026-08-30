"use client";
/**
 * 语音通话面板（P10）：按住说话的电话式对话。
 *
 * 采集/协议/播放全在 useVoiceCall；本组件只做状态呈现——顶部状态行、
 * 实时字幕（用户识别文本 + 老师流式回答）、中央按住说话大按钮、
 * 播报停止与挂断。语音轮次由后端写入当前会话，关闭时由父组件刷新。
 */
import { useEffect, useRef } from "react";
import { Loader2, Mic, PhoneOff, VolumeX } from "lucide-react";
import { Modal } from "@/components/ui/Modal";
import { cn } from "@/lib/cn";
import { t, type Lang } from "@/lib/i18n";
import { useVoiceCall } from "@/lib/voice/useVoiceCall";

/** 展示用轻量清洗：语音场景的回答文本去 markdown 记号即可朗读阅读。 */
function plainForDisplay(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, "（代码请看对话）")
    .replace(/[`*$#>|]/g, "")
    .replace(/\[(.*?)\]\(.*?\)/g, "$1")
    .trim();
}

export function VoiceCallModal({ open, onClose, lang, sessionId, workspaceId, onSessionBound, onTurnsDone }: {
  open: boolean;
  onClose: () => void;
  lang: Lang;
  sessionId: string | null;
  workspaceId: string | null;
  onSessionBound?: (sid: string) => void;
  /** 挂断回调（无论是否有轮次）；sid 为本次通话绑定的会话。 */
  onTurnsDone?: (sid: string | null) => void;
}) {
  const tr = (k: string, fb?: string) => t(lang, k, fb);
  const turnsRef = useRef(0);
  const boundSidRef = useRef<string | null>(sessionId);
  // Keep the latest parent callback without re-creating the hook binding.
  const parentBoundRef = useRef(onSessionBound);
  useEffect(() => { parentBoundRef.current = onSessionBound; }, [onSessionBound]);

  const voice = useVoiceCall({
    lang,
    onSessionBound: (sid) => {
      boundSidRef.current = sid;
      parentBoundRef.current?.(sid);
    },
    onTurnEnd: (sid) => {
      if (sid) boundSidRef.current = sid;
      turnsRef.current += 1;
    },
  });

  useEffect(() => {
    if (open && voice.phase === "idle") {
      turnsRef.current = 0;
      boundSidRef.current = sessionId;
      void voice.start(sessionId, workspaceId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const handleClose = () => {
    voice.hangUp();
    onTurnsDone?.(turnsRef.current > 0 ? boundSidRef.current : null);
    onClose();
  };

  const statusLine = () => {
    if (voice.error) return tr(`chat.voice.call.err.${voice.error}`, voice.error);
    switch (voice.phase) {
      case "connecting": return tr("chat.voice.call.connecting");
      case "ready": return tr("chat.voice.call.ready");
      case "recording": return tr("chat.voice.call.release");
      case "recognizing": return tr("chat.voice.call.recognizing");
      case "thinking": return tr("chat.voice.call.thinking");
      case "speaking": return tr("chat.voice.call.speaking");
      case "ended": return tr("chat.voice.call.err.network");
      default: return "";
    }
  };

  const extraStatus = () => {
    if (!voice.statusKey || voice.phase === "ended") return null;
    return tr(`chat.voice.call.${voice.statusKey}`, voice.statusKey);
  };

  const holdable = voice.phase === "ready";
  const busy = voice.phase === "recognizing" || voice.phase === "thinking" || voice.phase === "speaking";

  return (
    <Modal open={open} onClose={handleClose} title={tr("chat.voice.call.title")} width={440}>
      <div className="flex flex-col gap-3">
        <p className="text-[0.72rem] leading-relaxed text-muted">{tr("chat.voice.call.desc")}</p>

        {/* 状态行 */}
        <div className={cn(
          "flex items-center gap-2 rounded-[8px] border px-3 py-2 text-[0.75rem]",
          voice.error ? "border-danger/30 bg-danger/5 text-danger"
            : voice.phase === "recording" ? "border-danger/25 bg-danger/5 text-fg-secondary"
              : "border-border bg-surface-sunken/50 text-fg-secondary",
        )}>
          {voice.phase === "connecting" && <Loader2 size={13} className="animate-spin text-accent" />}
          {voice.phase === "recording" && (
            <span className="relative flex h-2 w-2 shrink-0">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-danger opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-danger" />
            </span>
          )}
          {(busy || voice.phase === "ready") && !voice.error && (
            <span className={cn("h-2 w-2 shrink-0 rounded-full", voice.phase === "ready" ? "bg-success" : "animate-pulse bg-accent")} />
          )}
          <span className="min-w-0 flex-1">{statusLine()}</span>
          {extraStatus() && <span className="shrink-0 text-[0.68rem] text-muted">{extraStatus()}</span>}
        </div>

        {/* 实时字幕 */}
        <div className="flex min-h-36 max-h-56 flex-col gap-2 overflow-y-auto rounded-[10px] border border-border bg-surface-sunken/40 p-3 text-[0.8rem] leading-relaxed">
          {voice.userText && (
            <div>
              <div className="mb-0.5 text-[0.66rem] font-medium text-muted">{tr("chat.voice.call.you")}</div>
              <p className="whitespace-pre-wrap text-fg">{voice.userText}</p>
            </div>
          )}
          {(voice.assistantText || voice.phase === "thinking" || voice.phase === "speaking") && (
            <div>
              <div className="mb-0.5 text-[0.66rem] font-medium text-muted">{tr("chat.voice.call.teacher")}</div>
              <p className="whitespace-pre-wrap text-fg-secondary">
                {plainForDisplay(voice.assistantText) ||
                  (voice.phase === "thinking" ? tr("chat.voice.call.thinking") : tr("chat.voice.call.speaking"))}
              </p>
            </div>
          )}
          {!voice.userText && !voice.assistantText && voice.phase !== "thinking" && voice.phase !== "speaking" && (
            <div className="flex flex-1 items-center justify-center text-[0.72rem] text-muted">
              {tr("chat.voice.call.ready")}
            </div>
          )}
        </div>

        {/* 按住说话大按钮 */}
        <div className="flex flex-col items-center gap-2 py-1">
          <button
            type="button"
            disabled={!holdable}
            onPointerDown={(e) => { e.preventDefault(); if (holdable) void voice.beginTalk(); }}
            onPointerUp={() => voice.endTalk()}
            onPointerLeave={() => voice.endTalk()}
            onPointerCancel={() => voice.endTalk()}
            onContextMenu={(e) => e.preventDefault()}
            style={{ touchAction: "none" }}
            className={cn(
              "flex h-20 w-20 select-none items-center justify-center rounded-full border shadow-sm transition-all",
              voice.phase === "recording"
                ? "scale-105 border-danger bg-danger text-white"
                : holdable
                  ? "border-accent/40 bg-accent-soft/60 text-accent-strong hover:bg-accent-soft"
                  : "cursor-not-allowed border-border bg-surface-sunken text-muted",
            )}
            aria-label={tr("chat.voice.call.hold")}
          >
            {voice.phase === "recording"
              ? <Mic size={26} className="animate-pulse" />
              : busy ? <Loader2 size={22} className="animate-spin" /> : <Mic size={26} />}
          </button>
          <span className="text-[0.7rem] text-muted">
            {voice.phase === "recording" ? tr("chat.voice.call.release") : tr("chat.voice.call.hold")}
          </span>
        </div>

        {/* 操作行 */}
        <div className="flex items-center justify-center gap-2">
          {voice.phase === "speaking" && (
            <button
              onClick={() => voice.stopSpeaking()}
              className="flex items-center gap-1.5 rounded-[10px] border border-border px-3 py-1.5 text-[0.75rem] text-fg-secondary transition-colors hover:bg-surface-hover"
            >
              <VolumeX size={13} /> {tr("chat.voice.call.stopAudio")}
            </button>
          )}
          <button
            onClick={handleClose}
            className="flex items-center gap-1.5 rounded-[10px] bg-danger px-4 py-1.5 text-[0.75rem] font-medium text-white shadow-sm transition-opacity hover:opacity-90"
          >
            <PhoneOff size={13} /> {tr("chat.voice.call.hangup")}
          </button>
        </div>
      </div>
    </Modal>
  );
}
