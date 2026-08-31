"use client";
import Link from "next/link";
import { useEffect, useRef } from "react";
import { ArrowRight } from "lucide-react";
import { InkCanvas } from "./InkCanvas";
import { Magnetic } from "./Magnetic";
import type { LandingTr } from "./LandingNav";

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

  // 轻滚翻页：Hero 仍有可见部分留在视口内（底部 ≥20%）时，一次向下的
  // 轻滚意图（滚轮累计约 40px 或触摸上滑约 48px）即平滑滑到功能区，
  // 呈现"轻轻一滚即翻页"的动态手感。
  // 不 preventDefault、不劫持向上滚动与其余页面；翻页中的新滚动意图会
  // 立即中断动画交还原生滚动（忽略触控板惯性衰减的小增量）；
  // prefers-reduced-motion 下退化为原生滚动。
  useEffect(() => {
    const el = ref.current;
    if (!el || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const st = { locked: false, lockTimer: 0, wheelTimer: 0, accum: 0, glideAt: 0, touchY: 0 };
    const heroVisible = () => el.getBoundingClientRect().bottom > window.innerHeight * 0.2;
    const glide = () => {
      st.locked = true;
      st.glideAt = Date.now();
      document.getElementById("features")?.scrollIntoView({ behavior: "smooth", block: "start" });
      st.lockTimer = window.setTimeout(() => {
        st.locked = false;
      }, 800);
    };
    const cancelGlide = () => {
      window.clearTimeout(st.lockTimer);
      // 以瞬时定位打断进行中的平滑滚动，立刻交还原生滚动。
      window.scrollTo({ top: window.scrollY, behavior: "auto" });
      st.locked = false;
    };
    const onWheel = (e: WheelEvent) => {
      if (st.locked) {
        if (Date.now() - st.glideAt > 400 || Math.abs(e.deltaY) > 80) cancelGlide();
        return;
      }
      window.clearTimeout(st.wheelTimer);
      st.wheelTimer = window.setTimeout(() => {
        st.accum = 0;
      }, 180);
      if (e.deltaY <= 0 || !heroVisible()) {
        st.accum = 0;
        return;
      }
      st.accum += e.deltaY;
      if (st.accum >= 40) {
        st.accum = 0;
        glide();
      }
    };
    const onTouchStart = (e: TouchEvent) => {
      st.touchY = e.touches[0]?.clientY ?? 0;
      if (st.locked) cancelGlide();
    };
    const onTouchMove = (e: TouchEvent) => {
      if (st.locked) return;
      const y = e.touches[0]?.clientY ?? 0;
      if (st.touchY - y >= 48 && heroVisible()) {
        st.touchY = y;
        glide();
      }
    };
    window.addEventListener("wheel", onWheel, { passive: true });
    window.addEventListener("touchstart", onTouchStart, { passive: true });
    window.addEventListener("touchmove", onTouchMove, { passive: true });
    return () => {
      window.removeEventListener("wheel", onWheel);
      window.removeEventListener("touchstart", onTouchStart);
      window.removeEventListener("touchmove", onTouchMove);
      window.clearTimeout(st.lockTimer);
      window.clearTimeout(st.wheelTimer);
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

      {/* 滚动提示：宋体文案 + 黛青动线；点击或轻滚即翻页到功能区 */}
      <a
        href="#features"
        aria-label={tr("landing.hero.scroll")}
        onClick={(e) => {
          e.preventDefault();
          document.getElementById("features")?.scrollIntoView({ behavior: "smooth", block: "start" });
        }}
        className="group relative flex flex-col items-center gap-2 pb-8 outline-none"
      >
        <span className="font-serif text-xs tracking-[0.4em] text-fg-secondary transition-colors group-hover:text-accent">
          {tr("landing.hero.scroll")}
        </span>
        <span className="block h-12 w-px overflow-hidden bg-border">
          <span className="block h-full w-full bg-accent animate-[scroll-line_1.8s_ease-in-out_infinite]" />
        </span>
      </a>
    </section>
  );
}
