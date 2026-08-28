import { ArrowUpRight } from "lucide-react";
import { Reveal } from "./Reveal";
import type { LandingTr } from "./LandingNav";

const FEATURES = ["f1", "f2", "f3", "f4", "f5", "f6"] as const;

/** 功能分节：编辑式编号列表（无卡片），行悬停染黛青。 */
export function Features({ tr }: { tr: LandingTr }) {
  return (
    <section id="features" className="scroll-mt-24">
      <div className="mx-auto max-w-6xl px-4 py-24 md:py-36">
        <Reveal>
          <p className="font-mono text-[11px] uppercase tracking-[0.3em] text-accent">
            {tr("landing.features.kicker")}
          </p>
          <h2 className="mt-4 max-w-2xl font-serif text-4xl font-bold leading-tight tracking-tight text-fg md:text-5xl">
            {tr("landing.features.title")}
          </h2>
          <p className="mt-5 max-w-xl leading-relaxed text-fg-secondary">
            {tr("landing.features.subtitle")}
          </p>
        </Reveal>

        <div className="mt-16 border-t border-border">
          {FEATURES.map((key, i) => (
            <Reveal key={key} delay={i * 60}>
              <div className="group relative grid items-baseline gap-2 border-b border-border py-7 transition-colors duration-300 hover:bg-surface md:grid-cols-[72px_1fr_1.1fr_32px] md:gap-6 md:px-4">
                {/* 底部黛青发线：hover 时从左扫入 */}
                <span
                  aria-hidden
                  className="pointer-events-none absolute inset-x-0 bottom-0 h-px origin-left scale-x-0 bg-accent transition-transform duration-500 ease-out group-hover:scale-x-100"
                />
                <span className="font-mono text-sm text-muted transition-colors duration-300 group-hover:text-accent2">
                  0{i + 1}
                </span>
                <h3 className="font-serif text-xl font-semibold text-fg transition-all duration-300 group-hover:translate-x-1 group-hover:text-accent md:text-2xl">
                  {tr(`landing.features.${key}.title`)}
                </h3>
                <p className="text-sm leading-relaxed text-fg-secondary">
                  {tr(`landing.features.${key}.desc`)}
                </p>
                <ArrowUpRight
                  size={18}
                  className="hidden -translate-x-1 text-accent opacity-0 transition-all duration-300 group-hover:translate-x-0 group-hover:opacity-100 md:block"
                />
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
