"use client";
import { useEffect } from "react";
import { AppShell } from "@/components/shell/AppShell";
import { useAuthStore, hydrateAuth } from "@/lib/auth-store";

export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  const { loaded, statusLoaded, authRequired, user } = useAuthStore();

  useEffect(() => {
    hydrateAuth();
  }, []);

  // M0: when AUTH_MODE=1 and not authenticated, redirect to login.
  // `statusLoaded` 并入门控：水合并行化后 authRequired 与 token 校验可能
  // 乱序完成，两者都落定才渲染，未登录用户绝不闪现工作区。
  const needsRedirect = loaded && statusLoaded && authRequired && !user;
  useEffect(() => {
    if (needsRedirect) {
      const redirect = encodeURIComponent(window.location.pathname);
      window.location.href = `/login?redirect=${redirect}`;
    }
  }, [needsRedirect]);

  // Show nothing while hydrating or redirecting (prevents flash of content)
  if (!loaded || !statusLoaded || needsRedirect) {
    return <div className="min-h-screen bg-bg" />;
  }

  return <AppShell>{children}</AppShell>;
}
