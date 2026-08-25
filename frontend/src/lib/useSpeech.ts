"use client";
/**
 * Web Speech API voice input hook (Chrome/Edge).
 *
 * Single-shot recognition: user clicks the mic, speaks, the final transcript
 * is appended to the chat textarea. Interim (partial) results stream into a
 * live preview so the user sees transcription happening.
 *
 * `lang` is the UI language, mapped to a BCP-47 tag for recognition accuracy:
 * zh -> zh-CN, en -> en-US. Switching language mid-session just needs the user
 * to pick the recognition locale that matches what they'll say.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import type { Lang } from "./i18n";

// Minimal typings for the Web Speech API (TS DOM lib doesn't always ship these).
interface SRAlternative { transcript: string; confidence: number; }
interface SRResult { isFinal: boolean; readonly length: number; [i: number]: SRAlternative; }
interface SRResultList { readonly length: number; [i: number]: SRResult; }
interface SREvent extends Event { resultIndex: number; results: SRResultList; }
interface SRErrorEvent extends Event { error: string; message: string; }
interface SpeechRecognitionLike extends EventTarget {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((e: SREvent) => void) | null;
  onerror: ((e: SRErrorEvent) => void) | null;
  onend: (() => void) | null;
  onstart: (() => void) | null;
}
type SRCtor = { new (): SpeechRecognitionLike };

function getCtor(): SRCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    SpeechRecognition?: SRCtor;
    webkitSpeechRecognition?: SRCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

function localeFor(lang: Lang): string {
  return lang === "zh" ? "zh-CN" : "en-US";
}

export interface UseSpeech {
  supported: boolean;
  listening: boolean;
  interim: string;
  error: string | null;
  start: () => void;
  stop: () => void;
}

export function useSpeechRecognition(
  lang: Lang,
  onFinal: (text: string) => void,
): UseSpeech {
  // SSR-safe: supported is false on server AND first client render, then
  // resolved in an effect. This keeps server/first-client HTML identical
  // (no hydration mismatch on the mic button's title/disabled state).
  const [supported, setSupported] = useState(false);
  useEffect(() => {
    // Deferred so setState doesn't run synchronously in the effect body
    // (react-hooks/set-state-in-effect); SSR/first-render parity is kept.
    const id = requestAnimationFrame(() => setSupported(getCtor() !== null));
    return () => cancelAnimationFrame(id);
  }, []);
  const [listening, setListening] = useState(false);
  const [interim, setInterim] = useState("");
  const [error, setError] = useState<string | null>(null);
  const recRef = useRef<SpeechRecognitionLike | null>(null);
  // Keep latest callback without re-creating the recognition instance.
  const onFinalRef = useRef(onFinal);
  useEffect(() => { onFinalRef.current = onFinal; }, [onFinal]);

  const stop = useCallback(() => {
    const rec = recRef.current;
    if (rec) {
      try { rec.stop(); } catch { /* ignore */ }
    }
    setListening(false);
    setInterim("");
  }, []);

  const start = useCallback(() => {
    const Ctor = getCtor();
    if (!Ctor) { setError("unsupported"); return; }
    // stop any existing instance first (browser allows only one)
    if (recRef.current) {
      try { recRef.current.abort(); } catch { /* ignore */ }
    }
    const rec = new Ctor();
    rec.lang = localeFor(lang);
    rec.continuous = false;      // single utterance; silence ends it
    rec.interimResults = true;   // stream partials
    rec.maxAlternatives = 1;
    rec.onstart = () => { setListening(true); setError(null); setInterim(""); };
    rec.onresult = (e: SREvent) => {
      let interimText = "";
      let finalText = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        const txt = r[0]?.transcript ?? "";
        if (r.isFinal) finalText += txt; else interimText += txt;
      }
      setInterim(interimText);
      if (finalText.trim()) {
        onFinalRef.current(finalText.trim());
        setInterim("");
      }
    };
    rec.onerror = (e: SRErrorEvent) => {
      // "no-speech" / "aborted" are benign; surface real errors only.
      if (e.error !== "no-speech" && e.error !== "aborted") {
        setError(e.error || "error");
      }
    };
    rec.onend = () => { setListening(false); setInterim(""); };
    recRef.current = rec;
    try { rec.start(); }
    catch { /* already started */ }
  }, [lang]);

  // cleanup on unmount
  useEffect(() => {
    return () => {
      const rec = recRef.current;
      if (rec) { try { rec.abort(); } catch { /* ignore */ } }
    };
  }, []);

  return { supported, listening, interim, error, start, stop };
}
