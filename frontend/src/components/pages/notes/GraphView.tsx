"use client";
// 统一资源关系图：笔记/普通对话/笔记助手线程/失效节点；支持平移、滚轮缩放、适应视图与点击跳转。
import { useMemo, useRef, useState } from "react";
import { Maximize2, Minus, Plus, RotateCcw } from "lucide-react";
import type { GraphNode, NotesGraph } from "@/lib/types-notes";

const COLORS: Record<GraphNode["kind"], string> = {
  note: "var(--color-accent)",
  session: "var(--color-info)",
  notes_thread: "var(--color-accent2)",
  ghost: "var(--color-muted)",
};

export function GraphView({ graph, folderNames, tr, onOpenNote, onCreateNote, onOpenSession, onOpenThread }: {
  graph: NotesGraph;
  folderNames: Record<string, string>;
  tr: (k: string, fallback?: string) => string;
  onOpenNote: (id: string) => void;
  onCreateNote: (title: string) => void;
  onOpenSession?: (id: string) => void;
  onOpenThread?: (id: string) => void;
}) {
  const [hover, setHover] = useState<string | null>(null);
  const [view, setView] = useState({ x: 0, y: 0, scale: 1 });
  const drag = useRef<{ x: number; y: number; vx: number; vy: number } | null>(null);
  const layout = useMemo(() => {
    const W = 900, H = 620, cx = W / 2, cy = H / 2;
    const degree: Record<string, number> = {};
    graph.edges.forEach((edge) => { degree[edge.source] = (degree[edge.source] || 0) + 1; degree[edge.target] = (degree[edge.target] || 0) + 1; });
    const pos: Record<string, { x: number; y: number }> = {};
    const groups = [
      graph.nodes.filter((node) => node.kind === "note"),
      graph.nodes.filter((node) => node.kind === "session"),
      graph.nodes.filter((node) => node.kind === "notes_thread"),
      graph.nodes.filter((node) => node.kind === "ghost" || node.status !== "resolved"),
    ];
    const radii = [150, 245, 320, 385];
    groups.forEach((nodes, group) => [...nodes].sort((a, b) => (degree[b.id] || 0) - (degree[a.id] || 0)).forEach((node, index) => {
      const angle = (index / Math.max(nodes.length, 1)) * Math.PI * 2 - Math.PI / 2 + group * 0.35;
      const radius = nodes.length === 1 && group === 0 ? 0 : radii[group];
      pos[node.id] = { x: cx + Math.cos(angle) * radius, y: cy + Math.sin(angle) * radius };
    }));
    return { W, H, pos, degree };
  }, [graph]);
  const nodeById = useMemo(() => Object.fromEntries(graph.nodes.map((node) => [node.id, node])), [graph.nodes]);
  const hovered = hover ? nodeById[hover] : undefined;
  const zoom = (delta: number) => setView((v) => ({ ...v, scale: Math.max(.35, Math.min(2.6, v.scale + delta)) }));
  const reset = () => setView({ x: 0, y: 0, scale: 1 });
  const activate = (node: GraphNode) => {
    if (node.status && node.status !== "resolved") {
      window.alert(node.status === "deleted" ? "该资源已被删除" : "该资源不存在或无法访问");
      if (node.kind === "ghost" && node.status === "unresolved") onCreateNote(node.title);
      return;
    }
    if (node.kind === "note") onOpenNote(node.resource_id || node.id);
    else if (node.kind === "session") onOpenSession?.(node.resource_id || node.id.replace(/^session:/, ""));
    else if (node.kind === "notes_thread") onOpenThread?.(node.resource_id || node.id.replace(/^notes_thread:/, ""));
    else onCreateNote(node.title);
  };

  if (!graph.nodes.length) return <div className="flex h-full items-center justify-center text-xs text-muted">{tr("graph.empty")}</div>;
  return <div className="relative flex h-full min-h-0 flex-col overflow-hidden bg-bg">
    <div className="flex items-center gap-1 border-b border-border bg-surface px-3 py-2 text-[11px] text-muted">
      <span>{tr("graph.desc")}</span>
      <div className="ml-auto flex gap-1">
        <button title="缩小" className="rounded p-1 hover:bg-surface-hover" onClick={() => zoom(-.15)}><Minus size={13} /></button>
        <button title="放大" className="rounded p-1 hover:bg-surface-hover" onClick={() => zoom(.15)}><Plus size={13} /></button>
        <button title="适应画布" className="rounded p-1 hover:bg-surface-hover" onClick={() => setView({ x: 0, y: 0, scale: .82 })}><Maximize2 size={13} /></button>
        <button title="重置" className="rounded p-1 hover:bg-surface-hover" onClick={reset}><RotateCcw size={13} /></button>
      </div>
    </div>
    <svg
      viewBox={`0 0 ${layout.W} ${layout.H}`} className="min-h-0 flex-1 touch-none select-none"
      onWheel={(e) => { e.preventDefault(); zoom(e.deltaY > 0 ? -.1 : .1); }}
      onPointerDown={(e) => { (e.currentTarget as SVGSVGElement).setPointerCapture(e.pointerId); drag.current = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y }; }}
      onPointerMove={(e) => { if (!drag.current) return; setView((v) => ({ ...v, x: drag.current!.vx + (e.clientX - drag.current!.x) / v.scale, y: drag.current!.vy + (e.clientY - drag.current!.y) / v.scale })); }}
      onPointerUp={() => { drag.current = null; }}
    >
      <g transform={`translate(${layout.W / 2 + view.x} ${layout.H / 2 + view.y}) scale(${view.scale}) translate(${-layout.W / 2} ${-layout.H / 2})`}>
        {graph.edges.map((edge, index) => { const a = layout.pos[edge.source], b = layout.pos[edge.target]; if (!a || !b) return null; return <line key={`${edge.source}-${edge.target}-${index}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={edge.resolved ? "var(--color-border)" : "var(--color-danger)"} strokeWidth={edge.kind === "notes_thread" ? 2 : 1.2} strokeDasharray={edge.resolved ? undefined : "5 4"} opacity={hover && hover !== edge.source && hover !== edge.target ? .25 : .8} />; })}
        {graph.nodes.map((node) => { const p = layout.pos[node.id]; if (!p) return null; const active = hover === node.id; const invalid = node.status && node.status !== "resolved"; return <g key={node.id} transform={`translate(${p.x} ${p.y})`} className="cursor-pointer" onPointerDown={(e) => e.stopPropagation()} onMouseEnter={() => setHover(node.id)} onMouseLeave={() => setHover(null)} onClick={() => activate(node)}>
          <circle r={active ? 15 : 11} fill={invalid ? "var(--color-surface)" : COLORS[node.kind]} stroke={invalid ? "var(--color-danger)" : "var(--color-surface)"} strokeWidth={active ? 4 : 2} strokeDasharray={invalid ? "4 3" : undefined} />
          <text y={26} textAnchor="middle" fontSize="10" fill="var(--color-fg-secondary)">{node.title.length > 16 ? `${node.title.slice(0, 16)}…` : node.title}</text>
        </g>; })}
      </g>
    </svg>
    {hovered && <div className="pointer-events-none absolute bottom-4 left-4 max-w-xs rounded-lg border border-border bg-surface/95 px-3 py-2 text-xs shadow-lg">
      <div className="font-medium text-fg">{hovered.title}</div>
      <div className="mt-1 text-[11px] text-muted">类型：{hovered.kind} · 关联：{layout.degree[hovered.id] || 0}</div>
      {hovered.folder_id && <div className="text-[11px] text-muted">文件夹：{folderNames[hovered.folder_id] || hovered.folder_name || "未分类"}</div>}
      {hovered.message_count !== undefined && <div className="text-[11px] text-muted">消息：{hovered.message_count}</div>}
      {hovered.status && hovered.status !== "resolved" && <div className="text-[11px] text-danger">状态：{hovered.status === "deleted" ? "已删除" : "无法解析"}</div>}
    </div>}
  </div>;
}
