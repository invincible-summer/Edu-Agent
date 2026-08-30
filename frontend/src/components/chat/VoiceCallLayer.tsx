"use client";
/**
 * 语音通话层（P10 沉浸式改版）：不再弹出对话卡——通话期间 chat 页面照常
 * 显示，语音轮次实时写入消息流（转写即用户消息、answer_delta 节流进
 * pendingAnswer、turn_end 落定），本层只补三件「电话感」：
 *
 *   1. 左上角「小手机」指示器：迷你手机造型 + 声波 + 通话时长，点开
 *      可停止播报/挂断；
 *   2. 顶部「板书」浮窗：老师正在朗读的句子含公式时，原文以 KaTeX
 *      渲染在虚化小黑板上（听公式的同时能看清楚它长什么样）；
 *   3. 底部控制条：按住说话 / 停止播报 / 挂断，替代被临时收起的输入框
 *      （输入框只是隐藏不卸载，草稿不丢）。
 *
 * 采集/协议/播放全在 useVoiceCall；会话写入与 store 的世代守卫和
 * handleSend（chat 页文字流）同构，语音轮与文字轮共享同一套渲染路径。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2, Mic, PhoneOff, Presentation, Smartphone, VolumeX } from "lucide-react";
import { AnchoredPopover } from "@/components/ui/AnchoredPopover";
import { cn } from "@/lib/cn";
import { t, type Lang } from "@/lib/i18n";
import { listSessions, loadSession } from "@/lib/api";
import { useChatStore } from "@/lib/store";
import { notifySessionChanged } from "@/lib/ws-settings";
import { Markdown, containsMathMarkdown } from "@/components/chat/markdown";
import { useVoiceCall, type VoicePhase } from "@/lib/voice/useVoiceCall";

const MINUTE = 60;

function fmtDuration(total: number): string {
  const mm = Math.floor(total / MINUTE).toString().padStart(2, "0");
  const ss = (total % MINUTE).toString().padStart(2, "0");
  return `${mm}:${ss}`;
}

/* ---- 板书：正在朗读的句子含公式 → 虚化小黑板渲染原文 ------------------ */

export function FormulaBoard({ lang, sentence }: { lang: Lang; sentence: string | null }) {
  const [recent, setRecent] = useState<string | null>(null);
  useEffect(() => {
    // setState 经 rAF/timeout 延迟触发（react-hooks/set-state-in-effect）。
    if (sentence && containsMathMarkdown(sentence)) {
      const raf = requestAnimationFrame(() => setRecent(sentence));
      return () => cancelAnimationFrame(raf);
    }
    // 朗读结束/换到纯文字句：多亮一会儿，读公式需要回看时间。
    const delay = sentence === null ? 2600 : 450;
    const timer = window.setTimeout(() => setRecent(null), delay);
    return () => window.clearTimeout(timer);
  }, [sentence]);

  if (!recent) return null;
  return (
    <div className="pointer-events-none absolute inset-x-0 top-10 z-10 flex justify-center px-4">
      <div className="voice-board board-in pointer-events-auto flex max-h-[42vh] w-full max-w-[min(94%,620px)] flex-col overflow-hidden">
        <div className="flex items-center gap-1.5 px-3.5 pb-1 pt-2.5">
          <Presentation size={12} className="shrink-0" />
          <span className="text-[0.66rem] font-medium tracking-wide">{t(lang, "chat.voice.call.board.title")}</span>
          <span className="board-chalk-dash mx-1.5 flex-1" aria-hidden />
        </div>
        <div className="voice-board-body">
          <Markdown className="chat-prose">{recent}</Markdown>
        </div>
      </div>
    </div>
  );
}

/* ---- 左上角小手机指示器 --------------------------------------------------- */

export function CallBadge({ lang, voice, onHangUp }: {
  lang: Lang;
  voice: ReturnType<typeof useVoiceCall>;
  onHangUp: () => void;
}) {
  const tr = (k: string, fb?: string) => t(lang, k, fb);
  const [open, setOpen] = useState(false);
  const anchorRef = useRef<HTMLButtonElement>(null);

  const dotCls = voice.error
    ? "bg-danger"
    : voice.phase === "ready"
      ? "bg-success"
      : voice.phase === "recording"
        ? "bg-danger animate-pulse"
        : "bg-accent animate-pulse";
  const waving = voice.phase === "speaking" || voice.phase === "recording";

  return (
    <div className="absolute left-10 top-2 z-20">
      <button
        ref={anchorRef}
        type="button"
        onClick={() => setOpen((o) => !o)}
        title={tr("chat.voice.call.inCall")}
        aria-label={tr("chat.voice.call.inCall")}
        aria-expanded={open}
        className="flex h-7 cursor-pointer items-center gap-2 rounded-full border border-accent/30 bg-surface/90 py-0.5 pl-1 pr-2.5 shadow-sm backdrop-blur transition-colors hover:border-accent/50"
      >
        {/* 迷你手机机身：渐变屏幕 + 听筒点，读作「正在通话的小手机」 */}
        <span className="relative flex h-5 w-5 shrink-0 items-center justify-center rounded-[5px] bg-gradient-to-b from-accent to-accent-strong text-white shadow-inner">
          <Smartphone size={11} strokeWidth={2.4} />
        </span>
        {/* 声波：老师说话/我说话时跳动 */}
        <span className="flex h-3.5 items-end gap-[2px]" aria-hidden>
          {[5, 9, 6, 10, 7].map((h, i) => (
            <span
              key={i}
              style={{ height: `${h}px`, animationDelay: `${i * 0.13}s` }}
              className={cn("w-[2px] rounded-full bg-accent/75", waving && "call-wave-bar")}
            />
          ))}
        </span>
        <span className="tnum text-[0.68rem] font-medium text-fg-secondary">{fmtDuration(voice.callSeconds)}</span>
        <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", dotCls)} />
      </button>

      <AnchoredPopover anchorRef={anchorRef} open={open} onClose={() => setOpen(false)} placement="bottom-start">
        <div className="w-44 rounded-[10px] border border-border bg-surface p-1.5 shadow-lg">
          <p className="px-2 pb-1 pt-0.5 text-[0.64rem] text-muted">{tr("chat.voice.call.controls")}</p>
          {voice.phase === "speaking" && (
            <button
              type="button"
              onClick={() => voice.stopSpeaking()}
              className="flex w-full items-center gap-2 rounded-[7px] px-2 py-1.5 text-[0.75rem] text-fg-secondary transition-colors hover:bg-surface-hover"
            >
              <VolumeX size={13} /> {tr("chat.voice.call.stopAudio")}
            </button>
          )}
          <button
            type="button"
            onClick={onHangUp}
            className="flex w-full items-center gap-2 rounded-[7px] px-2 py-1.5 text-[0.75rem] font-medium text-danger transition-colors hover:bg-danger/10"
          >
            <PhoneOff size={13} /> {tr("chat.voice.call.hangup")}
          </button>
        </div>
      </AnchoredPopover>
    </div>
  );
}

/* ---- 底部控制条（通话期间替代输入框） ------------------------------------ */

function statusLineFor(lang: Lang, phase: VoicePhase, error: string | null): string {
  const tr = (k: string, fb?: string) => t(lang, k, fb);
  if (error) return tr(`chat.voice.call.err.${error}`, error);
  switch (phase) {
    case "connecting": return tr("chat.voice.call.connecting");
    case "ready": return tr("chat.voice.call.ready");
    case "recording": return tr("chat.voice.call.release");
    case "recognizing": return tr("chat.voice.call.recognizing");
    case "thinking": return tr("chat.voice.call.thinking");
    case "speaking": return tr("chat.voice.call.speaking");
    case "ended": return tr("chat.voice.call.err.network");
    default: return "";
  }
}

export function CallBar({ lang, voice, onHangUp }: {
  lang: Lang;
  voice: ReturnType<typeof useVoiceCall>;
  onHangUp: () => void;
}) {
  const tr = (k: string, fb?: string) => t(lang, k, fb);
  const holdable = voice.phase === "ready";
  const busy = voice.phase === "recognizing" || voice.phase === "thinking" || voice.phase === "speaking";
  const extraStatus = voice.statusKey && voice.phase !== "ended"
    ? tr(`chat.voice.call.${voice.statusKey}`, voice.statusKey)
    : null;

  return (
    <div className="px-4 pb-3 pt-1">
      <div className="mx-auto flex max-w-[820px] items-center gap-2.5 rounded-[14px] border border-border bg-surface p-2.5 shadow-md">
        {/* 状态区 */}
        <div className="flex min-w-0 flex-1 items-center gap-2.5 px-1.5">
          {voice.phase === "connecting" && <Loader2 size={15} className="shrink-0 animate-spin text-accent" />}
          {voice.phase === "recording" && (
            <span className="relative flex h-2.5 w-2.5 shrink-0">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-danger opacity-75" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-danger" />
            </span>
          )}
          {(busy || voice.phase === "ready") && voice.phase !== "connecting" && voice.phase !== "recording" && (
            <span className={cn("h-2.5 w-2.5 shrink-0 rounded-full", voice.phase === "ready" ? "bg-success" : "animate-pulse bg-accent")} />
          )}
          {voice.error && <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-danger" />}
          <div className="min-w-0">
            <p className={cn("truncate text-[0.78rem] font-medium", voice.error ? "text-danger" : "text-fg")}>
              {statusLineFor(lang, voice.phase, voice.error)}
            </p>
            <p className="truncate text-[0.66rem] text-muted">
              {extraStatus ?? tr("chat.voice.call.inCall")}
            </p>
          </div>
        </div>

        {/* 停止播报 */}
        {voice.phase === "speaking" && (
          <button
            type="button"
            onClick={() => voice.stopSpeaking()}
            className="flex h-9 shrink-0 items-center gap-1.5 rounded-[10px] border border-border px-2.5 text-[0.72rem] text-fg-secondary transition-colors hover:bg-surface-hover"
            title={tr("chat.voice.call.stopAudio")}
          >
            <VolumeX size={14} />
            <span className="hidden sm:inline">{tr("chat.voice.call.stopAudio")}</span>
          </button>
        )}

        {/* 按住说话 */}
        <div className="relative flex h-12 w-12 shrink-0 items-center justify-center">
          {voice.phase === "recording" && (
            <span className="call-pulse-ring absolute inset-0 rounded-full border-2 border-danger/50" aria-hidden />
          )}
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
              "flex h-12 w-12 select-none items-center justify-center rounded-full border shadow-sm transition-all",
              voice.phase === "recording"
                ? "scale-105 border-danger bg-danger text-white"
                : holdable
                  ? "border-accent/40 bg-accent-soft/60 text-accent-strong hover:bg-accent-soft"
                  : "cursor-not-allowed border-border bg-surface-sunken text-muted",
            )}
            aria-label={tr("chat.voice.call.hold")}
          >
            {voice.phase === "recording"
              ? <Mic size={20} className="animate-pulse" />
              : busy ? <Loader2 size={18} className="animate-spin" /> : <Mic size={20} />}
          </button>
        </div>

        {/* 挂断 */}
        <button
          type="button"
          onClick={onHangUp}
          className="flex h-9 shrink-0 items-center gap-1.5 rounded-[10px] bg-danger px-3 text-[0.75rem] font-medium text-white shadow-sm transition-opacity hover:opacity-90"
        >
          <PhoneOff size={14} />
          <span className="hidden sm:inline">{tr("chat.voice.call.hangup")}</span>
        </button>
      </div>
      <p className="mt-1.5 text-center text-[0.65rem] text-muted/70">
        {voice.phase === "recording" ? tr("chat.voice.call.release") : tr("chat.voice.call.desc.short")}
      </p>
      <p className="mx-auto mt-1 max-w-[760px] text-center text-[0.58rem] leading-relaxed text-muted/60">
        {tr("chat.voice.call.browserNote")}
      </p>
    </div>
  );
}

/* ---- 通话层本体 ------------------------------------------------------------ */

export function VoiceCallLayer({ lang, sessionId, workspaceId, onClose }: {
  lang: Lang;
  sessionId: string | null;
  workspaceId: string | null;
  onClose: () => void;
}) {
  const router = useRouter();
  const turnsRef = useRef(0);
  const boundSidRef = useRef<string | null>(sessionId);
  // 会话世代守卫：语音轮进行中用户切走会话时，残余写入全部丢弃。
  const genRef = useRef<number | null>(null);
  const answerAccumRef = useRef("");
  const flushTimerRef = useRef<number | null>(null);

  const flushNow = useCallback(() => {
    if (flushTimerRef.current !== null) {
      window.clearTimeout(flushTimerRef.current);
      flushTimerRef.current = null;
    }
    useChatStore.getState().flushPending("", answerAccumRef.current);
  }, []);

  const refreshSessions = useCallback(() => {
    listSessions()
      .then((r) => {
        useChatStore.getState().setSessions(r.sessions);
        notifySessionChanged();
      })
      .catch(() => undefined);
  }, []);

  const reloadBoundSession = useCallback((sid: string) => {
    loadSession(sid)
      .then((detail) => {
        const st = useChatStore.getState();
        if (st.sessionId === sid) {
          st.loadFull(detail.messages || [], detail.knowledge_files || [], sid);
        }
      })
      .catch(() => undefined);
  }, []);

  const voice = useVoiceCall({
    lang,
    onSessionBound: (sid) => {
      boundSidRef.current = sid;
      // 只绑 store、不 router.replace：Next 16 里 bare /chat → /chat/<sid>
      // 的 replace 会整页重挂载（动态段 key 变化），通话层与 WS 会随之
      // 被拆除。URL 由挂断时的 handleHangUp 补齐。
      useChatStore.getState().setSessionId(sid);
    },
    onTurnBegin: (text) => {
      const st = useChatStore.getState();
      genRef.current = st.generation;
      answerAccumRef.current = "";
      st.setStreaming(true);
      st.resetPending();
      st.setMessages([...st.messages, { role: "user" as const, content: text }]);
    },
    onAnswerDelta: (content) => {
      answerAccumRef.current += content;
      if (flushTimerRef.current === null) {
        flushTimerRef.current = window.setTimeout(() => {
          flushTimerRef.current = null;
          useChatStore.getState().flushPending("", answerAccumRef.current);
        }, 50);
      }
    },
    onTurnEnd: (sid) => {
      if (sid) boundSidRef.current = sid;
      turnsRef.current += 1;
      flushNow();
      const st = useChatStore.getState();
      if (genRef.current === null || st.generation === genRef.current) {
        if (st.pendingAnswer || st.pendingThinking || st.pendingToolCalls.length > 0) st.commitAssistant();
        st.setStreaming(false);
        st.setRetry(null);
      }
      refreshSessions();
    },
    onTurnError: () => {
      // 中断的轮次以服务端落盘为准：重载替换本地半截流，避免不一致。
      flushNow();
      const st = useChatStore.getState();
      const sid = boundSidRef.current;
      if (sid && sid === st.sessionId) {
        reloadBoundSession(sid);
      } else {
        st.setStreaming(false);
        st.resetPending();
      }
    },
  });

  // 挂载即拨号（StrictMode 双效应由 hook 内 phaseRef 守卫兜住）。
  useEffect(() => {
    turnsRef.current = 0;
    boundSidRef.current = sessionId;
    void voice.start(sessionId, workspaceId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleHangUp = useCallback(() => {
    const hadTurns = turnsRef.current > 0;
    const sid = boundSidRef.current;
    voice.hangUp();
    flushNow();
    const st = useChatStore.getState();
    // 完成过轮次、或挂断时仍有轮次在途：以服务端落盘为准重载对齐，
    // 本地半截流/悬空的用户消息都会被替换掉。
    const turnInFlight = st.streaming;
    if (sid && sid === st.sessionId && (hadTurns || turnInFlight)) {
      reloadBoundSession(sid);
    } else if (st.streaming) {
      st.setStreaming(false);
      st.resetPending();
    }
    refreshSessions();
    onClose();
    // 通话期间刻意没有 router.replace（见 onSessionBound 注释）；挂断后
    // 再把 URL 对齐到本次通话绑定的会话，深链/刷新语义与文字轮一致。
    if (sid && (hadTurns || turnInFlight)) {
      router.replace(`/chat/${encodeURIComponent(sid)}`, { scroll: false });
    }
  }, [flushNow, onClose, refreshSessions, reloadBoundSession, router, voice]);

  return (
    <>
      <CallBadge lang={lang} voice={voice} onHangUp={handleHangUp} />
      <FormulaBoard lang={lang} sentence={voice.speakingSentence} />
      <CallBar lang={lang} voice={voice} onHangUp={handleHangUp} />
    </>
  );
}
