"use client";
/**
 * 语音通话层（P10 沉浸式改版）：不再弹出对话卡——通话期间 chat 页面照常
 * 显示，语音轮次实时写入消息流（转写即用户消息、answer_delta 节流进
 * pendingAnswer、turn_end 落定），本层只补三件「电话感」：
 *
 *   1. 左上角「小手机」指示器：迷你手机造型 + 声波 + 通话时长，点开
 *      可停止播报/挂断；
 *   2. 顶部「板书」黑板：接通即常驻、挂断才收起；上下双面板只记老师
 *      讲到的公式句（KaTeX 原文渲染），写满后擦掉更久的那块再写新的；
 *   3. 底部控制条：按住说话 / 停止播报 / 挂断，渲染在原输入框上方——
 *      通话期间输入框保持可用，打字消息经同一条 WS 发出（sendText），
 *      老师的回复仍走 TTS 语音通道；浏览器不支持语音识别时可纯打字通话。
 *
 * 采集/协议/播放全在 useVoiceCall；会话写入与 store 的世代守卫和
 * handleSend（chat 页文字流）同构，语音轮与文字轮共享同一套渲染路径。
 */
import { Fragment, useCallback, useEffect, useRef, useState } from "react";
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

/* ---- 板书：上下双面板只记公式句，接通常驻、挂断才关 --------------------- */

type BoardSlot = { key: number; text: string } | null;

/** 擦除动画时长（ms）：与 globals.css 的 panel-erase 时长保持一致。 */
const BOARD_ERASE_MS = 450;

export function FormulaBoard({ lang, sentence, active }: {
  lang: Lang;
  sentence: string | null;
  /** 已接通（ready 起至通话结束）：黑板常驻，挂断随通话层卸载才消失。 */
  active: boolean;
}) {
  const [slots, setSlots] = useState<[BoardSlot, BoardSlot]>([null, null]);
  const [erasing, setErasing] = useState<0 | 1 | null>(null);
  const lastWrittenRef = useRef<0 | 1 | null>(null);
  const lastTextRef = useRef<string | null>(null);
  const keyRef = useRef(0);

  useEffect(() => {
    if (!sentence || !containsMathMarkdown(sentence)) return;
    if (sentence === lastTextRef.current) return; // 同句重播不重复上板
    lastTextRef.current = sentence;
    // 先写上面、再写下面；两块都满时擦掉「更久没写」的那块（保留最近写的）。
    const target: 0 | 1 = slots[0] === null
      ? 0
      : slots[1] === null
        ? 1
        : lastWrittenRef.current === 0 ? 1 : 0;
    const write = () => {
      keyRef.current += 1;
      const key = keyRef.current;
      lastWrittenRef.current = target;
      setSlots((prev) => {
        const next: [BoardSlot, BoardSlot] = [prev[0], prev[1]];
        next[target] = { key, text: sentence };
        return next;
      });
      setErasing(null);
    };
    if (slots[target] === null) {
      // setState 经 rAF 延迟触发（react-hooks/set-state-in-effect）。
      const raf = requestAnimationFrame(write);
      return () => cancelAnimationFrame(raf);
    }
    setErasing(target);
    const timer = window.setTimeout(write, BOARD_ERASE_MS);
    return () => window.clearTimeout(timer);
  }, [sentence, slots]);

  if (!active) return null;
  return (
    <div className="pointer-events-none absolute inset-x-0 top-10 z-10 flex justify-center px-4">
      <div className="voice-board board-in pointer-events-auto flex max-h-[46vh] w-full max-w-[min(94%,620px)] flex-col overflow-hidden">
        <div className="flex items-center gap-1.5 px-3.5 pb-1 pt-2.5">
          <Presentation size={12} className="shrink-0" />
          <span className="text-[0.66rem] font-medium tracking-wide">{t(lang, "chat.voice.call.board.title")}</span>
          <span className="board-chalk-dash mx-1.5 flex-1" aria-hidden />
        </div>
        <div className="voice-board-body flex flex-col">
          {slots.map((slot, i) => (
            <Fragment key={i}>
              {i === 1 && <div className="voice-board-divider" aria-hidden />}
              <div className="voice-board-panel">
                {slot ? (
                  <div key={slot.key} className={erasing === i ? "panel-erase" : "panel-write"}>
                    <Markdown className="chat-prose">{slot.text}</Markdown>
                  </div>
                ) : i === 0 ? (
                  <p className="text-[0.72rem] text-white/55">{t(lang, "chat.voice.call.board.empty")}</p>
                ) : null}
              </div>
            </Fragment>
          ))}
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

/* ---- 底部控制条（位于输入框上方，打字消息走同一条语音 WS） ---------------- */

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
    <div className="px-4 pb-1.5 pt-1">
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
        {voice.error === "voice_not_supported"
          ? tr("chat.voice.call.textNote")
          : voice.phase === "recording"
            ? tr("chat.voice.call.release")
            : tr("chat.voice.call.desc.short")}
      </p>
      <p className="mx-auto mt-1 max-w-[760px] text-center text-[0.58rem] leading-relaxed text-muted/60">
        {tr("chat.voice.call.browserNote")}
      </p>
    </div>
  );
}

/* ---- 通话层本体 ------------------------------------------------------------ */

/** 通话期间暴露给宿主页面的文本通道：打字消息改走语音 WS（回复仍 TTS 播报），
 *  停止按钮在语音轮次里对应打断播报。 */
export type VoiceTextController = {
  sendText: (text: string) => void;
  stopSpeaking: () => void;
};

export function VoiceCallLayer({ lang, sessionId, workspaceId, onClose, onRegisterController }: {
  lang: Lang;
  sessionId: string | null;
  workspaceId: string | null;
  onClose: () => void;
  onRegisterController?: (ctl: VoiceTextController | null) => void;
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

  // 把文本通道注册给宿主页面；卸载时置空，输入框回落到文字流路径。
  useEffect(() => {
    onRegisterController?.({ sendText: voice.sendText, stopSpeaking: voice.stopSpeaking });
    return () => onRegisterController?.(null);
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

  // 接通（ready 起）板书常驻；connecting/ended 不算接通。
  const boardActive = voice.phase === "ready" || voice.phase === "recording"
    || voice.phase === "recognizing" || voice.phase === "thinking" || voice.phase === "speaking";

  return (
    <>
      <CallBadge lang={lang} voice={voice} onHangUp={handleHangUp} />
      <FormulaBoard lang={lang} sentence={voice.speakingSentence} active={boardActive} />
      <CallBar lang={lang} voice={voice} onHangUp={handleHangUp} />
    </>
  );
}
