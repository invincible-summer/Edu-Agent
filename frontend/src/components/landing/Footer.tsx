import Link from "next/link";
import { GraduationCap } from "lucide-react";
import type { LandingTr } from "./LandingNav";

/** 落地页页脚：品牌 + 入口链接 + 巨型字标。 */
export function Footer({ tr }: { tr: LandingTr }) {
  return (
    <footer className="overflow-hidden border-t border-border/60">
      <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 px-4 py-10 sm:flex-row">
        <div className="flex items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-[6px] bg-accent text-white">
            <GraduationCap size={13} />
          </span>
          <span className="text-sm text-fg-secondary">
            © {new Date().getFullYear()} {tr("app.name")}
          </span>
        </div>
        <nav className="flex items-center gap-5">
          <Link href="/docs" className="text-sm text-muted transition-colors hover:text-fg">
            {tr("landing.footer.docs")}
          </Link>
          <Link href="/login" className="text-sm text-muted transition-colors hover:text-fg">
            {tr("landing.footer.login")}
          </Link>
          <Link href="/register" className="text-sm text-muted transition-colors hover:text-fg">
            {tr("landing.footer.register")}
          </Link>
        </nav>
      </div>
      <div
        aria-hidden
        className="select-none whitespace-nowrap text-center font-serif text-[13vw] font-bold leading-[0.85] text-fg/5"
      >
        AI TUTOR OS
      </div>
    </footer>
  );
}
