"use client";
/**
 * 语音通话 hook：push-to-talk 状态机 + 语音 WebSocket 协议客户端。
 *
 * 服务端协议见 backend/app/api/v1/voice.py：JSON 控制/事件帧 + 下行二进制帧
 * （输入侧只发送最终识别文本；下行
 * 每句一个 tts_start 元事件 + 44.1 kHz PCM16 帧 + tts_end）。播放端按到达
 * 顺序入队，AudioBuffer 按元事件携带的采样率创建（浏览器自动重采样到
 * 输出设备速率）。
 *
 * 沉浸式改版：本 hook 不再持有对话文本（旧版把字幕攒在弹窗里），而是把
 * 转写/回答增量通过回调交给宿主组件写入聊天 store——通话期间 chat 页面
 * 照常流式显示。tts_start 携带的原始句子（含 markdown 公式）暴露为
 * speakingSentence，供「板书」浮窗渲染 KaTeX。播放链路串了
 * DynamicsCompressor + makeup gain，与后端的逐句响度归一化（loudness.py）
 * 叠加，进一步抹平句间/句内音量起伏。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE, voiceTicket } from "@/lib/api";
import type { Lang } from "@/lib/i18n";

type SpeechRecognitionAlternativeLike = { transcript: string };
type SpeechRecognitionResultLike = {
  isFinal: boolean;
  length: number;
  [index: number]: SpeechRecognitionAlternativeLike;
};
type SpeechRecognitionResultListLike = {
  length: number;
  [index: number]: SpeechRecognitionResultLike;
};
type SpeechRecognitionEventLike = Event & {
  resultIndex: number;
  results: SpeechRecognitionResultListLike;
};
type SpeechRecognitionErrorEventLike = Event & {
  error: string;
  message?: string;
};
type BrowserSpeechRecognition = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null;
  onend: (() => void) | null;
};
type BrowserSpeechRecognitionConstructor = new () => BrowserSpeechRecognition;

declare global {
  interface Window {
    SpeechRecognition?: BrowserSpeechRecognitionConstructor;
    webkitSpeechRecognition?: BrowserSpeechRecognitionConstructor;
  }
}

function browserSpeechErrorCode(error: string): string | null {
  switch (error) {
    case "aborted":
      return null;
    case "not-allowed":
    case "audio-capture":
      return "voice_permission_denied";
    case "service-not-allowed":
    case "network":
      return "voice_service_unavailable";
    case "no-speech":
      return "empty_transcript";
    default:
      return "voice_service_unavailable";
  }
}

export type VoicePhase =
  | "idle" | "connecting" | "ready" | "recording"
  | "recognizing" | "thinking" | "speaking" | "ended";

/** error 为后端 error 事件 code 或浏览器语音 API 的本地错误码。 */
export function useVoiceCall({ lang, onSessionBound, onTurnBegin, onAnswerDelta, onTurnEnd, onTurnError }: {
  lang: Lang;
  onSessionBound?: (sessionId: string) => void;
  /** 一轮开始（STT 结果就绪）：宿主把用户消息落进聊天流并置 streaming。 */
  onTurnBegin?: (userText: string) => void;
  /** 回答增量：宿主节流写入 pendingAnswer，页面正常流式渲染。 */
  onAnswerDelta?: (content: string) => void;
  /** 一轮结束（文本流完成，音频可能仍在播放）。 */
  onTurnEnd?: (sessionId: string | null) => void;
  /** 一轮中途失败（agent_error 或浏览器/协议错误会中断在途轮次）。 */
  onTurnError?: (code: string) => void;
}) {
  const [phase, setPhase] = useState<VoicePhase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [statusKey, setStatusKey] = useState<string | null>(null);
  const [speakingSentence, setSpeakingSentence] = useState<string | null>(null);
  const [callSeconds, setCallSeconds] = useState(0);

  const phaseRef = useRef<VoicePhase>("idle");
  const wsRef = useRef<WebSocket | null>(null);
  const playCtxRef = useRef<AudioContext | null>(null);
  const playChainRef = useRef<AudioNode | null>(null);
  const playSrcRef = useRef<AudioBufferSourceNode | null>(null);
  const queueRef = useRef<AudioBuffer[]>([]);
  const playingRef = useRef(false);
  const pendingTtsRateRef = useRef<number>(16000);
  const endedByUserRef = useRef(false);
  const sessionIdRef = useRef<string | null>(null);
  const startedAtRef = useRef<number | null>(null);
  const recognitionRef = useRef<BrowserSpeechRecognition | null>(null);
  const recognitionGenerationRef = useRef(0);
  const recognitionFinalTextRef = useRef("");
  const recognitionSubmittedRef = useRef(false);
  const recognitionHoldingRef = useRef(false);
  const recognitionStopRequestedRef = useRef(false);
  const recognitionFailedRef = useRef(false);
  const recognitionRestartTimerRef = useRef<number | null>(null);
  const startRecognitionRef = useRef<(generation: number) => void>(() => undefined);
  const cbRef = useRef({ onSessionBound, onTurnBegin, onAnswerDelta, onTurnEnd, onTurnError });
  useEffect(() => {
    cbRef.current = { onSessionBound, onTurnBegin, onAnswerDelta, onTurnEnd, onTurnError };
  }, [onSessionBound, onTurnBegin, onAnswerDelta, onTurnEnd, onTurnError]);

  const goto = useCallback((p: VoicePhase) => {
    phaseRef.current = p;
    setPhase(p);
  }, []);

  // ---- browser Speech Recognition -----------------------------------------

  const submitRecognition = useCallback((generation: number, recognition?: BrowserSpeechRecognition) => {
    if (generation !== recognitionGenerationRef.current || recognitionSubmittedRef.current) return;
    if (recognition && recognitionRef.current && recognitionRef.current !== recognition) return;
    recognitionSubmittedRef.current = true;
    const current = recognitionRef.current;
    if (current) {
      current.onresult = null;
      current.onerror = null;
      current.onend = null;
    }
    recognitionRef.current = null;
    const text = recognitionFinalTextRef.current.trim();
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      setError("network");
      goto("ended");
      return;
    }
    try {
      ws.send(JSON.stringify({ type: "utterance_end", text }));
    } catch {
      setError("network");
      goto("ended");
      return;
    }
    goto("recognizing");
  }, [goto]);

  const startRecognition = useCallback((generation: number) => {
    if (generation !== recognitionGenerationRef.current
        || !recognitionHoldingRef.current
        || recognitionFailedRef.current
        || endedByUserRef.current) return;
    const Recognition = window.SpeechRecognition ?? window.webkitSpeechRecognition;
    if (!Recognition) {
      recognitionFailedRef.current = true;
      recognitionHoldingRef.current = false;
      setError("voice_not_supported");
      goto("ready");
      return;
    }

    let recognition: BrowserSpeechRecognition;
    try {
      recognition = new Recognition();
    } catch {
      recognitionFailedRef.current = true;
      recognitionHoldingRef.current = false;
      setError("voice_service_unavailable");
      goto("ready");
      return;
    }
    recognition.lang = lang === "zh" ? "zh-CN" : "en-US";
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;
    const finalizedIndexes = new Set<number>();
    recognition.onresult = (event) => {
      if (generation !== recognitionGenerationRef.current || recognitionRef.current !== recognition) return;
      const startIndex = Math.max(0, event.resultIndex || 0);
      for (let i = startIndex; i < event.results.length; i++) {
        const result = event.results[i];
        if (!result?.isFinal || finalizedIndexes.has(i)) continue;
        finalizedIndexes.add(i);
        const transcript = result[0]?.transcript;
        if (transcript) recognitionFinalTextRef.current += transcript;
      }
    };
    recognition.onerror = (event) => {
      if (generation !== recognitionGenerationRef.current || recognitionRef.current !== recognition) return;
      const code = browserSpeechErrorCode(event.error);
      if (!code) return;
      recognitionFailedRef.current = true;
      recognitionHoldingRef.current = false;
      recognitionStopRequestedRef.current = true;
      if (recognitionRestartTimerRef.current !== null) {
        window.clearTimeout(recognitionRestartTimerRef.current);
        recognitionRestartTimerRef.current = null;
      }
      setError(code);
      if (phaseRef.current === "recording") goto("ready");
      recognition.onresult = null;
      recognition.onerror = null;
      recognition.onend = null;
      recognitionRef.current = null;
      try { recognition.abort(); } catch { /* noop */ }
    };
    recognition.onend = () => {
      if (generation !== recognitionGenerationRef.current || recognitionRef.current !== recognition) return;
      recognitionRef.current = null;
      recognition.onresult = null;
      recognition.onerror = null;
      recognition.onend = null;
      if (recognitionHoldingRef.current && !recognitionFailedRef.current
          && !recognitionStopRequestedRef.current && !endedByUserRef.current) {
        // Chrome/Edge may end a continuous session while the pointer is still
        // down.  Recreate it asynchronously and retain finalTextRef.
        if (recognitionRestartTimerRef.current === null) {
          recognitionRestartTimerRef.current = window.setTimeout(() => {
            recognitionRestartTimerRef.current = null;
            startRecognitionRef.current(generation);
          }, 0);
        }
        return;
      }
      submitRecognition(generation, recognition);
    };
    recognitionRef.current = recognition;
    try {
      recognition.start();
    } catch {
      recognitionFailedRef.current = true;
      recognitionHoldingRef.current = false;
      recognitionRef.current = null;
      recognition.onresult = null;
      recognition.onerror = null;
      recognition.onend = null;
      setError("voice_service_unavailable");
      goto("ready");
    }
  }, [goto, lang, submitRecognition]);

  useEffect(() => {
    startRecognitionRef.current = startRecognition;
  }, [startRecognition]);

  // ---- playback queue ------------------------------------------------------

  const ensurePlayCtx = useCallback(() => {
    if (!playCtxRef.current) {
      const ctx = new AudioContext();
      // 压缩器把句内/句间的响度差再抹平一层（后端已做逐句 RMS 归一化）：
      // threshold/knee/ratio 取广播级语音参数，makeup gain 补回损耗。
      const comp = ctx.createDynamicsCompressor();
      comp.threshold.value = -22;
      comp.knee.value = 24;
      comp.ratio.value = 5;
      comp.attack.value = 0.004;
      comp.release.value = 0.22;
      const gain = ctx.createGain();
      gain.gain.value = 1.2;
      comp.connect(gain);
      gain.connect(ctx.destination);
      playCtxRef.current = ctx;
      playChainRef.current = comp;
    }
    if (playCtxRef.current.state === "suspended") void playCtxRef.current.resume();
    return playCtxRef.current;
  }, []);

  // Recursive by design (onended chains the next sentence); the ref breaks
  // the self-reference so the callback identity stays stable for lint.
  const drainRef = useRef<() => void>(() => undefined);
  const drainQueue = useCallback(() => {
    if (playingRef.current) return;
    const buf = queueRef.current.shift();
    if (!buf) {
      if (phaseRef.current === "speaking") goto("ready");
      return;
    }
    const ctx = ensurePlayCtx();
    const node = ctx.createBufferSource();
    node.buffer = buf;
    node.connect(playChainRef.current ?? ctx.destination);
    playingRef.current = true;
    playSrcRef.current = node;
    node.onended = () => {
      playingRef.current = false;
      playSrcRef.current = null;
      drainRef.current();
    };
    node.start();
  }, [ensurePlayCtx, goto]);
  useEffect(() => { drainRef.current = drainQueue; }, [drainQueue]);

  const stopSpeaking = useCallback(() => {
    queueRef.current.length = 0;
    playingRef.current = false;
    try { playSrcRef.current?.stop(); } catch { /* already ended */ }
    playSrcRef.current = null;
    setSpeakingSentence(null);
    if (phaseRef.current === "speaking") goto("ready");
  }, [goto]);

  const enqueuePcm = useCallback((pcm: ArrayBuffer, sampleRate: number) => {
    const ctx = ensurePlayCtx();
    const src16 = new Int16Array(pcm);
    if (src16.length === 0) return;
    const floats = new Float32Array(src16.length);
    for (let i = 0; i < src16.length; i++) floats[i] = src16[i] / 32768;
    const buf = ctx.createBuffer(1, floats.length, sampleRate);
    buf.copyToChannel(floats, 0);
    queueRef.current.push(buf);
    drainQueue();
  }, [drainQueue, ensurePlayCtx]);

  // ---- WS event handling ----------------------------------------------------

  const handleEvent = useCallback((ev: Record<string, unknown>) => {
    switch (ev.type) {
      case "session_bound":
        sessionIdRef.current = (ev.session_id as string) || null;
        goto("ready");
        if (sessionIdRef.current) cbRef.current.onSessionBound?.(sessionIdRef.current);
        break;
      case "stt_start":
        setStatusKey(null);
        goto("recognizing");
        break;
      case "stt_result":
        setSpeakingSentence(null);
        cbRef.current.onTurnBegin?.(String(ev.text || ""));
        goto("thinking");
        break;
      case "step":
      case "tool_start":
      case "tool_progress":
      case "tool_warning":
        setStatusKey("tool");
        break;
      case "retry":
        setStatusKey("retry");
        break;
      case "answer_delta":
        cbRef.current.onAnswerDelta?.(String(ev.content || ""));
        if (phaseRef.current === "thinking") setStatusKey(null);
        break;
      case "tts_start":
        pendingTtsRateRef.current = Number(ev.sample_rate) || 16000;
        // 板书素材：tts_start 携带该句的原始 markdown（公式未清洗）。
        setSpeakingSentence(String(ev.text || "") || null);
        goto("speaking");
        break;
      case "tts_end":
        break;
      case "tts_error":
        setStatusKey("tts_err");
        break;
      case "turn_end":
        setSpeakingSentence(null);
        if (phaseRef.current !== "speaking" && !playingRef.current) goto("ready");
        cbRef.current.onTurnEnd?.((ev.session_id as string) || sessionIdRef.current);
        break;
      case "bye":
        goto("ended");
        break;
      case "error": {
        const code = String(ev.code || "agent");
        setError(code);
        if (code === "voice_disabled" || code === "session_not_found") {
          goto("ended");
        } else {
          // In-flight agent/TTS failures need host cleanup; pre-turn protocol
          // errors such as busy or empty_transcript leave the chat stream alone.
          if (phaseRef.current === "recognizing" || phaseRef.current === "thinking"
              || phaseRef.current === "speaking") {
            cbRef.current.onTurnError?.(code);
          }
          if (phaseRef.current !== "ready") goto("ready");
        }
        break;
      }
      default:
        break;
    }
  }, [goto]);

  // ---- lifecycle -------------------------------------------------------------

  const teardownRecognition = useCallback(() => {
    recognitionGenerationRef.current += 1;
    recognitionHoldingRef.current = false;
    recognitionStopRequestedRef.current = true;
    recognitionFailedRef.current = true;
    recognitionSubmittedRef.current = true;
    if (recognitionRestartTimerRef.current !== null) {
      window.clearTimeout(recognitionRestartTimerRef.current);
      recognitionRestartTimerRef.current = null;
    }
    const recognition = recognitionRef.current;
    recognitionRef.current = null;
    if (recognition) {
      recognition.onresult = null;
      recognition.onerror = null;
      recognition.onend = null;
      try { recognition.abort(); } catch { /* noop */ }
    }
    recognitionFinalTextRef.current = "";
  }, []);

  const teardownTransport = useCallback(() => {
    teardownRecognition();
    const ws = wsRef.current;
    wsRef.current = null;
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
      ws.onclose = null;
      ws.close();
    }
  }, [teardownRecognition]);

  const hangUp = useCallback(() => {
    endedByUserRef.current = true;
    try { wsRef.current?.send(JSON.stringify({ type: "end" })); } catch { /* noop */ }
    stopSpeaking();
    teardownTransport();
    void playCtxRef.current?.close().catch(() => undefined);
    playCtxRef.current = null;
    playChainRef.current = null;
    goto("ended");
  }, [goto, stopSpeaking, teardownTransport]);

  const start = useCallback(async (sessionId: string | null, workspaceId: string | null) => {
    if (phaseRef.current !== "idle") return; // dev StrictMode 双挂载只允许一条连接
    recognitionFinalTextRef.current = "";
    recognitionSubmittedRef.current = false;
    setError(null); setStatusKey(null); setSpeakingSentence(null);
    setCallSeconds(0);
    startedAtRef.current = Date.now();
    goto("connecting");
    try {
      const { ticket } = await voiceTicket();
      // 票据到手后再复位：StrictMode 双效应的 cleanup 会在 start() 的
      // await 间隙把它置 true，太早复位会被它盖掉。
      endedByUserRef.current = false;
      // 后端 WS 路由是 /api/v1/voice/ws：基址必须保留 API_BASE 的 /api/v1
      // 前缀，直连分支只换协议（http→ws、https→wss），同源分支拼当前 host
      // （生产同源走 nginx 的 WS 升级 location，不能依赖 next rewrite）。
      const wsBase = API_BASE.startsWith("http")
        ? API_BASE.replace(/^http/, "ws")
        : `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}${API_BASE}`;
      const ws = new WebSocket(`${wsBase}/voice/ws?ticket=${encodeURIComponent(ticket)}`);
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;
      ws.onopen = () => {
        ws.send(JSON.stringify({
          type: "start",
          session_id: sessionId,
          workspace_id: workspaceId,
          lang,
        }));
      };
      ws.onmessage = (ev) => {
        if (typeof ev.data === "string") {
          try { handleEvent(JSON.parse(ev.data)); } catch { /* skip malformed */ }
        } else {
          enqueuePcm(ev.data as ArrayBuffer, pendingTtsRateRef.current);
        }
      };
      ws.onclose = () => {
        if (!endedByUserRef.current) {
          setError("network");
          goto("ended");
        }
      };
    } catch {
      setError("network");
      goto("ended");
    }
  }, [enqueuePcm, goto, handleEvent, lang]);

  // 通话时长（指示器上的 mm:ss）：从 start 起计时，ended 停止。
  useEffect(() => {
    if (phase === "idle" || phase === "ended" || startedAtRef.current === null) return;
    const id = window.setInterval(() => {
      if (startedAtRef.current !== null) {
        setCallSeconds(Math.floor((Date.now() - startedAtRef.current) / 1000));
      }
    }, 1000);
    return () => window.clearInterval(id);
  }, [phase]);

  // ---- push-to-talk -----------------------------------------------------------

  const beginTalk = useCallback(() => {
    if (phaseRef.current !== "ready") return;
    setError(null);
    setStatusKey(null);
    recognitionGenerationRef.current += 1;
    const generation = recognitionGenerationRef.current;
    recognitionFinalTextRef.current = "";
    recognitionSubmittedRef.current = false;
    recognitionHoldingRef.current = true;
    recognitionStopRequestedRef.current = false;
    recognitionFailedRef.current = false;
    try {
      const Recognition = window.SpeechRecognition ?? window.webkitSpeechRecognition;
      if (!Recognition) {
        recognitionHoldingRef.current = false;
        recognitionFailedRef.current = true;
        setError("voice_not_supported");
        goto("ready");
        return;
      }
      ensurePlayCtx(); // resume playback ctx inside the user gesture
      startRecognition(generation);
      if (recognitionRef.current) goto("recording");
    } catch {
      recognitionHoldingRef.current = false;
      recognitionFailedRef.current = true;
      setError("voice_service_unavailable");
      goto("ready");
    }
  }, [ensurePlayCtx, goto, startRecognition]);

  /** 文本兜底输入：跳过浏览器 STT，直接把打好的文本当本轮转写发上
   *  同一条 WS——回复仍走 TTS 语音通道。正在播报时先打断（barge-in）。 */
  const sendText = useCallback((raw: string) => {
    const text = raw.trim();
    if (!text) return;
    if (phaseRef.current !== "ready" && phaseRef.current !== "speaking") return;
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      setError("network");
      goto("ended");
      return;
    }
    if (phaseRef.current === "speaking") stopSpeaking();
    setError(null);
    setStatusKey(null);
    ensurePlayCtx(); // 文本回复的 TTS 播放也依赖用户手势解锁的 AudioContext
    try {
      ws.send(JSON.stringify({ type: "utterance_end", text }));
    } catch {
      setError("network");
      goto("ended");
      return;
    }
    goto("recognizing");
  }, [ensurePlayCtx, goto, stopSpeaking]);

  const endTalk = useCallback(() => {
    if (phaseRef.current !== "recording") return;
    recognitionHoldingRef.current = false;
    recognitionStopRequestedRef.current = true;
    if (recognitionRestartTimerRef.current !== null) {
      window.clearTimeout(recognitionRestartTimerRef.current);
      recognitionRestartTimerRef.current = null;
    }
    const generation = recognitionGenerationRef.current;
    const recognition = recognitionRef.current;
    if (recognition) {
      try {
        recognition.stop();
      } catch {
        submitRecognition(generation, recognition);
      }
    } else {
      submitRecognition(generation);
    }
    goto("recognizing");
  }, [goto, submitRecognition]);

  useEffect(() => () => {
    endedByUserRef.current = true;
    stopSpeaking();
    teardownTransport();
    void playCtxRef.current?.close().catch(() => undefined);
  }, [stopSpeaking, teardownTransport]);

  return {
    phase, error, statusKey, speakingSentence, callSeconds,
    start, hangUp, beginTalk, endTalk, sendText, stopSpeaking,
  };
}
