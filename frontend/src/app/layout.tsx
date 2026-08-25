import type { Metadata } from "next";
import Script from "next/script";
import "katex/dist/katex.min.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Tutor OS",
  description: "智能学习 Agent — 你的私人 AI 教师",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh" suppressHydrationWarning>
      <body className="min-h-screen bg-bg text-fg antialiased">
        {/* No-flash theme init: runs before hydration so dark users never see
            a light flash. next/script (beforeInteractive) is the sanctioned way
            to inline a pre-hydration script without React's <script> warning. */}
        <Script id="edu-theme-init" strategy="beforeInteractive" dangerouslySetInnerHTML={{
          __html: `(function(){try{var p=new URLSearchParams(location.search);var t=p.get('theme');if(!t){t=localStorage.getItem('edu-agent-theme');}if(!t){t='light';}if(t==='dark'){document.documentElement.classList.add('dark');}}catch(e){}var fs=1.25;try{var v=parseFloat(localStorage.getItem('edu-agent-fs')||'1.25');if(v){fs=v;}}catch(e){}try{document.documentElement.style.setProperty('--fs-scale',String(fs));}catch(e){}})()`
        }} />
        {children}
      </body>
    </html>
  );
}
