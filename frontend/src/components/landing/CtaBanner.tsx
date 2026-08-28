import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Reveal } from "./Reveal";
import type { LandingTr } from "./LandingNav";

/**
 * 结尾 CTA：全幅深黛青横幅（沿用 AuthShell 品牌栏 #1d5650），
 * 不随主题变浅，保证白字对比度。
 */
export function CtaBanner({ tr, loggedIn }: { tr: LandingTr; loggedIn: boolean }) {
  return (
    <section className="relative overflow-hidden bg-[#1d5650]">
      <div
        aria-hidden
        className="pointer-events-none absolute -top-40 left-1/2 h-96 w-[42rem] -translate-x-1/2 rounded-full bg-white/10 blur-3xl"
      />
      <Reveal className="relative mx-auto max-w-4xl px-4 py-28 text-center md:py-40">
        <h2 className="font-serif text-4xl font-bold tracking-tight text-white md:text-6xl">
          {tr("landing.cta.title")}
        </h2>
        <p className="mx-auto mt-6 max-w-xl leading-relaxed text-white/75">
          {tr("landing.cta.subtitle")}
        </p>
        <div className="mt-12">
          <Link
            href={loggedIn ? "/chat" : "/register"}
            className="inline-flex h-13 items-center gap-2 rounded-full bg-white px-9 text-base font-medium text-[#1d5650] transition-transform duration-300 hover:scale-[1.04]"
          >
            {tr(loggedIn ? "landing.cta.workspace" : "landing.cta.button")}
            <ArrowRight size={17} />
          </Link>
        </div>
      </Reveal>
    </section>
  );
}
