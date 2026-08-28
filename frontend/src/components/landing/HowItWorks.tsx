import { Reveal } from "./Reveal";
import type { LandingTr } from "./LandingNav";

const STEPS = ["s1", "s2", "s3"] as const;

/** 如何使用分节：大号衬线序号 + 三步上手。 */
export function HowItWorks({ tr }: { tr: LandingTr }) {
  return (
    <section id="how" className="scroll-mt-24">
      <div className="mx-auto max-w-6xl px-4 py-24 md:py-36">
        <Reveal>
          <p className="font-mono text-[11px] uppercase tracking-[0.3em] text-accent">
            {tr("landing.how.kicker")}
          </p>
          <h2 className="mt-4 max-w-2xl font-serif text-4xl font-bold leading-tight tracking-tight text-fg md:text-5xl">
            {tr("landing.how.title")}
          </h2>
        </Reveal>

        <div className="mt-16 grid gap-12 md:grid-cols-3">
          {STEPS.map((key, i) => (
            <Reveal key={key} delay={i * 100}>
              <span className="font-serif text-7xl font-bold leading-none text-accent/20 md:text-8xl">
                0{i + 1}
              </span>
              <h3 className="mt-6 font-serif text-xl font-semibold text-fg">
                {tr(`landing.how.${key}.title`)}
              </h3>
              <p className="mt-3 text-sm leading-relaxed text-fg-secondary">
                {tr(`landing.how.${key}.desc`)}
              </p>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
