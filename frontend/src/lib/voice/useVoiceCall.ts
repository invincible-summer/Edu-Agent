"use client";
/**
 * 语音通话 hook：push-to-talk 状态机 + 语音 WebSocket 协议客户端。
 *
 * 服务端协议见 backend/app/api/v1/voice.py：JSON 控制/事件帧 + 二进制帧
 * （上行 16 kHz 单声道 PCM16，由 public/voice-pcm-worklet.js 产生；下行
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

export type VoicePhase =
  | "idle" | "connecting" | "ready" | "recording"
  | "recognizing" | "thinking" | "speaking" | "ended";

/** error 为后端 error 事件 code 或客户端本地码（network/mic）。 */
export function useVoiceCall({ lang, onSessionBound, onTurnBegin, onAnswerDelta, onTurnEnd, onTurnError }: {
  lang: Lang;
  onSessionBound?: (sessionId: string) => void;
  /** 一轮开始（STT 结果就绪）：宿主把用户消息落进聊天流并置 streaming。 */
  onTurnBegin?: (userText: string) => void;
  /** 回答增量：宿主节流写入 pendingAnswer，页面正常流式渲染。 */
  onAnswerDelta?: (content: string) => void;
  /** 一轮结束（文本流完成，音频可能仍在播放）。 */
  onTurnEnd?: (sessionId: string | null) => void;
  /** 一轮中途失败（agent_error / stt 崩溃等会中断在途轮次）。 */
  onTurnError?: (code: string) => void;
}) {
  const [phase, setPhase] = useState<VoicePhase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [statusKey, setStatusKey] = useState<string | null>(null);
  const [speakingSentence, setSpeakingSentence] = useState<string | null>(null);
  const [callSeconds, setCallSeconds] = useState(0);

  const phaseRef = useRef<VoicePhase>("idle");
  const wsRef = useRef<WebSocket | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const ctxRef = useRef<AudioContext | null>(null);
  const nodeRef = useRef<AudioWorkletNode | null>(null);
  const playCtxRef = useRef<AudioContext | null>(null);
  const playChainRef = useRef<AudioNode | null>(null);
  const playSrcRef = useRef<AudioBufferSourceNode | null>(null);
  const queueRef = useRef<AudioBuffer[]>([]);
  const playingRef = useRef(false);
  const pendingTtsRateRef = useRef<number>(16000);
  const endedByUserRef = useRef(false);
  const sessionIdRef = useRef<string | null>(null);
  const startedAtRef = useRef<number | null>(null);
  const cbRef = useRef({ onSessionBound, onTurnBegin, onAnswerDelta, onTurnEnd, onTurnError });
  useEffect(() => {
    cbRef.current = { onSessionBound, onTurnBegin, onAnswerDelta, onTurnEnd, onTurnError };
  }, [onSessionBound, onTurnBegin, onAnswerDelta, onTurnEnd, onTurnError]);

  const goto = useCallback((p: VoicePhase) => {
    phaseRef.current = p;
    setPhase(p);
  }, []);

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
      case "warning":
        setStatusKey("truncated");
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
          // 在途轮次被中断（agent_error / stt 崩溃）需要宿主收尾；
          // 轮前错误（busy/too_short…）不动聊天流。
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

  const teardownTransport = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    try { nodeRef.current?.disconnect(); } catch { /* noop */ }
    nodeRef.current = null;
    void ctxRef.current?.close().catch(() => undefined);
    ctxRef.current = null;
    const ws = wsRef.current;
    wsRef.current = null;
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
      ws.onclose = null;
      ws.close();
    }
  }, []);

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

  const beginTalk = useCallback(async () => {
    if (phaseRef.current !== "ready") return;
    setError(null);
    setStatusKey(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      streamRef.current = stream;
      const ctx = new AudioContext();
      ctxRef.current = ctx;
      await ctx.audioWorklet.addModule("/voice-pcm-worklet.js");
      const src = ctx.createMediaStreamSource(stream);
      const node = new AudioWorkletNode(ctx, "voice-pcm");
      nodeRef.current = node;
      node.port.onmessage = (e: MessageEvent<Int16Array>) => {
        const ws = wsRef.current;
        if (ws && ws.readyState === WebSocket.OPEN && e.data?.buffer) ws.send(e.data);
      };
      // Worklet nodes are pulled only when connected to a destination; a
      // zero-gain sink keeps the graph live without echoing the mic.
      const sink = ctx.createGain();
      sink.gain.value = 0;
      src.connect(node);
      node.connect(sink);
      sink.connect(ctx.destination);
      ensurePlayCtx(); // resume playback ctx inside the user gesture
      goto("recording");
    } catch {
      setError("mic");
    }
  }, [ensurePlayCtx, goto]);

  const endTalk = useCallback(() => {
    if (phaseRef.current !== "recording") return;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    try { nodeRef.current?.disconnect(); } catch { /* noop */ }
    nodeRef.current = null;
    void ctxRef.current?.close().catch(() => undefined);
    ctxRef.current = null;
    try { wsRef.current?.send(JSON.stringify({ type: "utterance_end" })); } catch { /* noop */ }
    goto("recognizing");
  }, [goto]);

  useEffect(() => () => {
    endedByUserRef.current = true;
    stopSpeaking();
    teardownTransport();
    void playCtxRef.current?.close().catch(() => undefined);
  }, [stopSpeaking, teardownTransport]);

  return {
    phase, error, statusKey, speakingSentence, callSeconds,
    start, hangUp, beginTalk, endTalk, stopSpeaking,
  };
}
