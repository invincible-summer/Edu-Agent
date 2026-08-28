"use client";
import Link from "next/link";
import { useEffect, useRef, type MouseEvent as ReactMouseEvent, type ReactNode } from "react";
import { ArrowRight } from "lucide-react";
import { InkCanvas } from "./InkCanvas";
import type { LandingTr } from "./LandingNav";

/** 磁吸容器：指针靠近时按钮轻微吸附位移。 */
function Magnetic({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const onMove = (e: ReactMouseEvent) => {
    const el = ref.current;
    if (!el || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const r = el.getBoundingClientRect();
    const dx = e.clientX - (r.left + r.width / 2);
    const dy = e.clientY - (r.top + r.height / 2);
    el.style.transform = `translate3d(${(dx * 0.18).toFixed(1)}px, ${(dy * 0.18).toFixed(1)}px, 0)`;
  };
  const onLeave = () => {
    if (ref.current) ref.current.style.transform = "";
  };
  return (
    <div
      ref={ref}
      onMouseMove={onMove}
      onMouseLeave={onLeave}
      className="transition-transform duration-300 ease-out will-change-transform"
    >
      {children}
    </div>
  );
}

/** 标题逐字上浮；b 段叠加黛青→朱砂渐变流光。 */
function StaggeredTitle({ a, b }: { a: string; b: string }) {
  let i = 0;
  const renderChars = (s: string, gradient: boolean) =>
    Array.from(s).map((ch) => {
      const delay = 120 + i++ * 55;
      return (
        <span
          key={`${gradient ? "b" : "a"}-${i}`}
          aria-hidden
          className={gradient ? "hero-gradient-text" : "hero-title-char"}
          style={{ animationDelay: `${delay}ms` }}
        >
          {ch === " " ? " " : ch}
        </span>
      );
    });
  return (
    <h1
      aria-label={`${a} ${b}`}
      className="mt-8 font-serif text-[clamp(2.75rem,13vw,7.5rem)] font-bold leading-[1.08] tracking-tight text-fg"
    >
      <span className="block">{renderChars(a, false)}</span>
      <span className="block">{renderChars(b, true)}</span>
    </h1>
  );
}

/**
 * Hero：全屏电影感首屏。墨色粒子网络背景 + 鼠标跟随光晕 +
 * 视差浮动光斑 + 逐字标题 + 竖排装饰字 + 滚动提示。
 * 通过 --mx/--my/--px/--py CSS 变量驱动，rAF 缓动。
 */
export function Hero({ tr, loggedIn }: { tr: LandingTr; loggedIn: boolean }) {
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let raf = 0;
    let tx = 0.5;
    let ty = 0.42;
    let cx = tx;
    let cy = ty;
    const onMove = (e: MouseEvent) => {
      const r = el.getBoundingClientRect();
      tx = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
      ty = Math.min(1, Math.max(0, (e.clientY - r.top) / r.height));
    };
    const tick = () => {
      cx += (tx - cx) * 0.07;
      cy += (ty - cy) * 0.07;
      el.style.setProperty("--mx", `${(cx * 100).toFixed(2)}%`);
      el.style.setProperty("--my", `${(cy * 100).toFixed(2)}%`);
      el.style.setProperty("--px", ((cx - 0.5) * 2).toFixed(3));
      el.style.setProperty("--py", ((cy - 0.5) * 2).toFixed(3));
      raf = requestAnimationFrame(tick);
    };
    window.addEventListener("mousemove", onMove, { passive: true });
    raf = requestAnimationFrame(tick);
    return () => {
      window.removeEventListener("mousemove", onMove);
      cancelAnimationFrame(raf);
    };
  }, []);

  return (
    <section ref={ref} className="relative flex min-h-svh flex-col overflow-hidden">
      {/* 粒子网络背景 */}
      <InkCanvas className="pointer-events-none absolute inset-0 h-full w-full opacity-60" />

      {/* 鼠标跟随光晕 */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(560px circle at var(--mx, 50%) var(--my, 42%), rgb(var(--accent) / 0.13), transparent 70%)",
        }}
      />

      {/* 视差浮动光斑（位移在外层，浮动动画在内层，避免 transform 冲突） */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{ transform: "translate3d(calc(var(--px, 0) * 26px), calc(var(--py, 0) * 26px), 0)" }}
      >
        <div className="absolute -top-24 left-[12%] h-80 w-80 rounded-full bg-accent-soft opacity-70 blur-3xl animate-[float-slow_9s_ease-in-out_infinite]" />
      </div>
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{ transform: "translate3d(calc(var(--px, 0) * -18px), calc(var(--py, 0) * -18px), 0)" }}
      >
        <div className="absolute right-[8%] bottom-16 h-72 w-72 rounded-full bg-accent2-soft opacity-50 blur-3xl animate-[float-slow_12s_ease-in-out_infinite_reverse]" />
      </div>

      {/* 竖排装饰字 */}
      <p
        aria-hidden
        className="vertical-rl absolute right-6 top-1/2 hidden -translate-y-1/2 select-none font-serif text-sm tracking-[0.5em] text-muted lg:block"
      >
        {tr("landing.hero.vertical")}
      </p>

      <div className="relative mx-auto flex w-full max-w-6xl flex-1 flex-col items-center justify-center px-4 pb-16 pt-32 text-center">
        <p className="page-in flex items-center gap-3 font-mono text-[11px] uppercase tracking-[0.3em] text-fg-secondary">
          <span className="h-px w-8 bg-border" />
          {tr("landing.hero.kicker")}
          <span className="h-px w-8 bg-border" />
        </p>

        <StaggeredTitle a={tr("landing.hero.title.a")} b={tr("landing.hero.title.b")} />

        <p
          className="page-in mx-auto mt-8 max-w-xl text-base leading-relaxed text-fg-secondary md:text-lg"
          style={{ animationDelay: "500ms" }}
        >
          {tr("landing.hero.subtitle")}
        </p>

        <div
          className="page-in mt-12 flex flex-wrap items-center justify-center gap-6"
          style={{ animationDelay: "620ms" }}
        >
          <Magnetic>
            <Link
              href={loggedIn ? "/chat" : "/register"}
              className="inline-flex h-12 items-center gap-2 rounded-full bg-accent px-8 text-[15px] font-medium text-white shadow-md transition-colors hover:bg-accent-strong"
            >
              {tr(loggedIn ? "landing.hero.workspace" : "landing.hero.primary")}
              <ArrowRight size={16} />
            </Link>
          </Magnetic>
          {!loggedIn && (
            <Link
              href="/login"
              className="group inline-flex items-center gap-1.5 text-[15px] font-medium text-fg-secondary transition-colors hover:text-accent"
            >
              {tr("landing.hero.secondary")}
              <ArrowRight size={15} className="transition-transform group-hover:translate-x-0.5" />
            </Link>
          )}
        </div>
      </div>

      {/* 滚动提示 */}
      <div className="relative flex flex-col items-center gap-2 pb-8">
        <span className="font-mono text-[10px] uppercase tracking-[0.3em] text-muted">
          {tr("landing.hero.scroll")}
        </span>
        <span className="block h-10 w-px overflow-hidden bg-border/60">
          <span className="block h-full w-full bg-accent animate-[scroll-line_1.8s_ease-in-out_infinite]" />
        </span>
      </div>
    </section>
  );
}
