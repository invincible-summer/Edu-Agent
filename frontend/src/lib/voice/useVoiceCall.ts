"use client";
/**
 * 语音通话 hook：push-to-talk 状态机 + 语音 WebSocket 协议客户端。
 *
 * 服务端协议见 backend/app/api/v1/voice.py：JSON 控制/事件帧 + 二进制帧
 * （上行 16 kHz 单声道 PCM16，由 public/voice-pcm-worklet.js 产生；下行
 * 每句一个 tts_start 元事件 + 44.1 kHz PCM16 帧 + tts_end）。播放端按到达
 * 顺序入队，AudioBuffer 按元事件携带的采样率创建（浏览器自动重采样到
 * 输出设备速率）。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE, voiceTicket } from "@/lib/api";
import type { Lang } from "@/lib/i18n";

export type VoicePhase =
  | "idle" | "connecting" | "ready" | "recording"
  | "recognizing" | "thinking" | "speaking" | "ended";

/** error 为后端 error 事件 code 或客户端本地码（network/mic）。 */
export function useVoiceCall({ lang, onSessionBound, onTurnEnd }: {
  lang: Lang;
  onSessionBound?: (sessionId: string) => void;
  onTurnEnd?: (sessionId: string | null) => void;
}) {
  const [phase, setPhase] = useState<VoicePhase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [userText, setUserText] = useState("");
  const [assistantText, setAssistantText] = useState("");
  const [statusKey, setStatusKey] = useState<string | null>(null);

  const phaseRef = useRef<VoicePhase>("idle");
  const wsRef = useRef<WebSocket | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const ctxRef = useRef<AudioContext | null>(null);
  const nodeRef = useRef<AudioWorkletNode | null>(null);
  const playCtxRef = useRef<AudioContext | null>(null);
  const playSrcRef = useRef<AudioBufferSourceNode | null>(null);
  const queueRef = useRef<AudioBuffer[]>([]);
  const playingRef = useRef(false);
  const pendingTtsRateRef = useRef<number>(16000);
  const endedByUserRef = useRef(false);
  const sessionIdRef = useRef<string | null>(null);
  const cbRef = useRef({ onSessionBound, onTurnEnd });
  useEffect(() => { cbRef.current = { onSessionBound, onTurnEnd }; }, [onSessionBound, onTurnEnd]);

  const goto = useCallback((p: VoicePhase) => {
    phaseRef.current = p;
    setPhase(p);
  }, []);

  // ---- playback queue ------------------------------------------------------

  const ensurePlayCtx = useCallback(() => {
    if (!playCtxRef.current) playCtxRef.current = new AudioContext();
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
    node.connect(ctx.destination);
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
        setUserText(String(ev.text || ""));
        setAssistantText("");
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
        setAssistantText((prev) => prev + String(ev.content || ""));
        if (phaseRef.current === "thinking") setStatusKey(null);
        break;
      case "tts_start":
        pendingTtsRateRef.current = Number(ev.sample_rate) || 16000;
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
        if (phaseRef.current !== "speaking" && !playingRef.current) goto("ready");
        cbRef.current.onTurnEnd?.((ev.session_id as string) || sessionIdRef.current);
        break;
      case "bye":
        goto("ended");
        break;
      case "error": {
        const code = String(ev.code || "agent");
        setError(code);
        if (code === "voice_disabled" || code === "session_not_found") goto("ended");
        else if (phaseRef.current !== "ready") goto("ready");
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
    goto("ended");
  }, [goto, stopSpeaking, teardownTransport]);

  const start = useCallback(async (sessionId: string | null, workspaceId: string | null) => {
    if (phaseRef.current !== "idle") return; // dev StrictMode 双挂载只允许一条连接
    setUserText(""); setAssistantText(""); setError(null); setStatusKey(null);
    sessionIdRef.current = sessionId;
    endedByUserRef.current = false;
    goto("connecting");
    try {
      const { ticket } = await voiceTicket();
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
    phase, error, userText, assistantText, statusKey,
    start, hangUp, beginTalk, endTalk, stopSpeaking,
  };
}
