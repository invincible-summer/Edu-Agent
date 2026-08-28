"use client";
// 递归文件夹树 + 当前节点分页 + 多选/Shift 连选 + 批量移动/删除 + 拖拽移动。
import { useMemo, useRef, useState } from "react";
import {
  ChevronDown, ChevronRight, Download, FileText, Folder, FolderPlus,
  MoreHorizontal, NotebookPen, Plus, Search, Sparkles, Tag, Trash2, X,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Pager, paged } from "@/components/ui/Pager";
import { Dropdown, useClickOutside, type DropdownItem } from "@/components/sidebar/Dropdown";
import { InlineEdit } from "@/components/sidebar/InlineEdit";
import { bulkDeleteNotes, bulkMoveNotes } from "@/lib/api-notes";
import { cn } from "@/lib/cn";
import { relTime } from "@/lib/format";
import type { NoteSummary, NotesFolder, NoteTemplate, VaultSnapshot } from "@/lib/types-notes";

export function NotesSidebar({
  vault, currentId, activeFolder, activeTag, search, creatingFolder, templates,
  tr, lang, onSelectFolder, onSelectTag, onSearch, onOpenNote, onCreateBlank,
  onCreateFromTemplate, onGenerate, onCreateFolder, onRenameFolder,
  onDeleteFolder, onExportAll, onExportFolder, onVaultChanged, onCancelCreateFolder,
}: {
  vault: VaultSnapshot;
  currentId: string | null;
  activeFolder: string | null;
  activeTag: string | null;
  search: string;
  creatingFolder: boolean;
  templates: NoteTemplate[];
  tr: (k: string, fallback?: string) => string;
  lang: "zh" | "en";
  onSelectFolder: (folderId: string | null) => void;
  onSelectTag: (tag: string | null) => void;
  onSearch: (q: string) => void;
  onOpenNote: (id: string) => void;
  onCreateBlank: () => void;
  onCreateFromTemplate: (templateId: string) => void;
  onGenerate: () => void;
  onCreateFolder: (name: string, parentId?: string) => void;
  onRenameFolder: (folderId: string, name: string) => void;
  onDeleteFolder: (folderId: string) => void;
  onExportAll: () => void;
  onExportFolder: (folderId: string) => void;
  onVaultChanged: () => Promise<void> | void;
  onCancelCreateFolder: () => void;
}) {
  const [page, setPage] = useState(0);
  const [newMenu, setNewMenu] = useState(false);
  const [folderMenu, setFolderMenu] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(
    () => new Set(vault.folders.filter((f) => !f.parent_id).map((f) => f.id)),
  );
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [dragOver, setDragOver] = useState<string | null>(null);
  const lastSelected = useRef<number | null>(null);
  const menuRef = useClickOutside<HTMLDivElement>(() => setNewMenu(false), newMenu);
  // 文件夹菜单（在滚动列表内）的锚点：同一时刻只开一个，条件挂到当前行
  const folderMenuRef = useRef<HTMLDivElement>(null);

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    return vault.notes
      .filter((n) => activeFolder === null || n.folder_id === activeFolder)
      .filter((n) => !activeTag || n.tags.includes(activeTag))
      .filter((n) => !q || n.title.toLowerCase().includes(q) || n.tags.some((t) => t.toLowerCase().includes(q)))
      .sort((a, b) => b.updated_at - a.updated_at);
  }, [vault.notes, activeFolder, activeTag, search]);
  const pageItems = paged(visible, page, 8);
  const folderCounts = useMemo(() => Object.fromEntries(vault.folders.map((f) => [f.id, vault.notes.filter((n) => n.folder_id === f.id).length])), [vault]);
  const children = useMemo(() => {
    const map: Record<string, NotesFolder[]> = {};
    for (const folder of vault.folders) (map[folder.parent_id || ""] ||= []).push(folder);
    Object.values(map).forEach((items) => items.sort((a, b) => a.name.localeCompare(b.name)));
    return map;
  }, [vault.folders]);

  const toggleSelected = (id: string, index: number, shift: boolean) => {
    setSelected((current) => {
      const next = new Set(current);
      if (shift && lastSelected.current !== null) {
        const [a, b] = [lastSelected.current, index].sort((x, y) => x - y);
        visible.slice(a, b + 1).forEach((note) => next.add(note.id));
      } else if (next.has(id)) next.delete(id); else next.add(id);
      lastSelected.current = index;
      return next;
    });
  };

  const moveSelection = async (folderId: string, fallbackId?: string) => {
    const ids = fallbackId && !selected.has(fallbackId)
      ? [fallbackId]
      : (selected.size > 0 ? [...selected] : (fallbackId ? [fallbackId] : []));
    if (ids.length === 0) return;
    await bulkMoveNotes(ids, folderId);
    setSelected(new Set());
    setDragOver(null);
    await onVaultChanged();
  };
  const deleteSelection = async () => {
    if (selected.size === 0 || !window.confirm(`将 ${selected.size} 篇笔记移入回收站？`)) return;
    await bulkDeleteNotes([...selected]);
    setSelected(new Set());
    await onVaultChanged();
  };
  const pickMoveTarget = async () => {
    const lines = ["root = 未分类", ...vault.folders.map((f) => `${f.id} = ${f.name}`)];
    const value = window.prompt(`输入目标文件夹 id：\n${lines.join("\n")}`, activeFolder || "root");
    if (value === null) return;
    const target = value === "root" ? "" : value.trim();
    if (target && !vault.folders.some((f) => f.id === target)) return;
    await moveSelection(target);
  };

  const renderFolders = (parentId = "", depth = 0): React.ReactNode => (children[parentId] || []).map((folder) => {
    const hasChildren = Boolean(children[folder.id]?.length);
    const open = expanded.has(folder.id);
    const menuItems: DropdownItem[] = [
      { label: "创建子文件夹", icon: FolderPlus, onClick: () => { const name = window.prompt("子文件夹名称"); if (name?.trim()) onCreateFolder(name, folder.id); } },
      { label: tr("notes.rename"), icon: NotebookPen, onClick: () => { const name = window.prompt(tr("notes.rename"), folder.name); if (name?.trim()) onRenameFolder(folder.id, name); } },
      { label: tr("notes.export"), icon: Download, onClick: () => onExportFolder(folder.id) },
      { label: tr("notes.delete"), icon: Trash2, danger: true, onClick: () => { if (window.confirm(`删除文件夹“${folder.name}”？内容会安全上移。`)) onDeleteFolder(folder.id); } },
    ];
    return (
      <div key={folder.id}>
        <div
          onDragOver={(e) => { e.preventDefault(); setDragOver(folder.id); }}
          onDragLeave={() => setDragOver((id) => id === folder.id ? null : id)}
          onDrop={(e) => { e.preventDefault(); void moveSelection(folder.id, e.dataTransfer.getData("text/note-id")); }}
          className={cn("group flex items-center rounded-md", dragOver === folder.id && "bg-accent-soft ring-1 ring-accent")}
          style={{ paddingLeft: depth * 12 }}
        >
          <button onClick={() => setExpanded((set) => { const next = new Set(set); if (next.has(folder.id)) next.delete(folder.id); else next.add(folder.id); return next; })} className="p-1 text-muted">
            {hasChildren ? (open ? <ChevronDown size={12} /> : <ChevronRight size={12} />) : <span className="block size-3" />}
          </button>
          <button onClick={() => { onSelectFolder(folder.id); setPage(0); }} className={cn("flex min-w-0 flex-1 items-center gap-1.5 px-1 py-1.5 text-left text-xs", activeFolder === folder.id ? "font-medium text-accent-strong" : "text-fg-secondary")}>
            <Folder size={13} className="shrink-0" /><span className="truncate">{folder.name}</span><span className="ml-auto tnum text-[10px] text-muted">{folderCounts[folder.id] || 0}</span>
          </button>
          <div className="relative" ref={folderMenu === folder.id ? folderMenuRef : undefined}>
            <button onClick={() => setFolderMenu(folderMenu === folder.id ? null : folder.id)} className="p-1 text-muted opacity-0 group-hover:opacity-100"><MoreHorizontal size={13} /></button>
            {folderMenu === folder.id && <Dropdown items={menuItems} onClose={() => setFolderMenu(null)} anchorRef={folderMenuRef} />}
          </div>
        </div>
        {open && renderFolders(folder.id, depth + 1)}
      </div>
    );
  });

  return (
    <div className="flex h-full min-h-0 flex-col border-r border-border bg-surface">
      <div className="space-y-2 border-b border-border p-2.5">
        <div className="flex items-center gap-1.5">
          <div className="relative" ref={menuRef}>
            <Button variant="primary" size="sm" icon={<Plus size={14} />} onClick={() => setNewMenu((v) => !v)}>{tr("notes.new")}</Button>
            {newMenu && <div className="absolute left-0 top-9 z-30 w-52 rounded-[10px] border border-border bg-surface p-1 shadow-lg">
              <button className="w-full rounded-md px-2 py-1.5 text-left text-xs hover:bg-surface-hover" onClick={() => { setNewMenu(false); onCreateBlank(); }}>{tr("notes.blank")}</button>
              {templates.slice(0, 8).map((t) => <button key={t.id} className="w-full truncate rounded-md px-2 py-1.5 text-left text-xs hover:bg-surface-hover" onClick={() => { setNewMenu(false); onCreateFromTemplate(t.id); }}>{lang === "en" && t.name_en ? t.name_en : t.name}</button>)}
            </div>}
          </div>
          <Button variant="accent2" size="sm" icon={<Sparkles size={14} />} onClick={onGenerate}>AI</Button>
        </div>
        <div className="relative"><Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted" /><input value={search} onChange={(e) => { onSearch(e.target.value); setPage(0); }} placeholder={tr("notes.search")} className="h-8 w-full rounded-[8px] border border-border bg-bg pl-7 pr-2 text-xs outline-none focus:border-accent" /></div>
      </div>

      {selected.size > 0 && <div className="flex flex-wrap items-center gap-1 border-b border-border bg-accent-soft px-2 py-1.5 text-[11px] text-accent-strong">
        <span className="mr-auto">已选 {selected.size} 篇</span>
        <button className="rounded px-1.5 py-1 hover:bg-surface" onClick={() => void pickMoveTarget()}>移动</button>
        <button className="rounded px-1.5 py-1 text-danger hover:bg-danger/10" onClick={() => void deleteSelection()}>删除</button>
        <button className="p-1" onClick={() => setSelected(new Set())}><X size={12} /></button>
      </div>}

      <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
        <FolderRow label={tr("notes.all")} count={vault.stats.note_count} active={activeFolder === null} onClick={() => { onSelectFolder(null); setPage(0); }} />
        {renderFolders()}
        <div onDragOver={(e) => { e.preventDefault(); setDragOver("root"); }} onDrop={(e) => { e.preventDefault(); void moveSelection("", e.dataTransfer.getData("text/note-id")); }} className={cn("rounded-md", dragOver === "root" && "bg-accent-soft ring-1 ring-accent")}>
          <FolderRow label={tr("notes.unfiled")} count={vault.notes.filter((n) => !n.folder_id).length} active={activeFolder === ""} onClick={() => { onSelectFolder(""); setPage(0); }} />
        </div>
        {creatingFolder ? <InlineEdit initialValue="" placeholder={tr("notes.newFolder")} onCommit={(v) => onCreateFolder(v, activeFolder || "")} onCancel={onCancelCreateFolder} /> : <button onClick={() => onCreateFolder("", activeFolder || "")} className="flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-xs text-muted hover:bg-surface-hover hover:text-accent"><FolderPlus size={13} /> {tr("notes.newFolder")}</button>}

        {Object.keys(vault.tags).length > 0 && <div className="mt-3 border-t border-border pt-2"><div className="flex flex-wrap gap-1 px-1.5">{Object.entries(vault.tags).slice(0, 14).map(([tag, count]) => <button key={tag} onClick={() => { onSelectTag(activeTag === tag ? null : tag); setPage(0); }} className={cn("flex items-center gap-0.5 rounded-md px-1.5 py-0.5 text-[11px]", activeTag === tag ? "bg-accent-soft text-accent-strong" : "text-muted hover:bg-surface-hover")}><Tag size={10} />{tag}<span className="opacity-60">{count}</span></button>)}</div></div>}

        <div className="mt-3 border-t border-border pt-2">
          <div className="flex items-center justify-between px-2 pb-1"><button className="text-[10px] uppercase tracking-wide text-muted" onClick={() => setSelected(new Set(visible.map((n) => n.id)))}>{tr("notes.count", "{n} 篇").replace("{n}", String(visible.length))} · 全选</button><button onClick={onExportAll} className="text-[11px] text-muted hover:text-accent">zip</button></div>
          {pageItems.length === 0 ? <div className="px-2 py-4 text-center text-[11px] text-muted">{tr("notes.empty.title")}</div> : pageItems.map((note) => {
            const index = visible.findIndex((item) => item.id === note.id);
            return <NoteRow key={note.id} note={note} current={note.id === currentId} selected={selected.has(note.id)} lang={lang} onSelect={(event) => toggleSelected(note.id, index, event.shiftKey)} onClick={() => onOpenNote(note.id)} onDragStart={(event) => { event.dataTransfer.setData("text/note-id", note.id); event.dataTransfer.effectAllowed = "move"; }} />;
          })}
          <Pager page={page} total={visible.length} per={8} onPage={setPage} />
        </div>
      </div>
    </div>
  );
}

function FolderRow({ label, count, active, onClick }: { label: string; count: number; active: boolean; onClick: () => void }) {
  return <button onClick={onClick} className={cn("flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-xs", active ? "bg-accent-soft font-medium text-accent-strong" : "text-fg-secondary hover:bg-surface-hover")}><ChevronRight size={12} className="opacity-50" /><span className="truncate">{label}</span><span className="ml-auto tnum text-[10px] text-muted">{count}</span></button>;
}

function NoteRow({ note, current, selected, lang, onSelect, onClick, onDragStart }: { note: NoteSummary; current: boolean; selected: boolean; lang: "zh" | "en"; onSelect: (event: React.MouseEvent<HTMLInputElement>) => void; onClick: () => void; onDragStart: (event: React.DragEvent<HTMLDivElement>) => void }) {
  return <div draggable onDragStart={onDragStart} className={cn("group flex items-start gap-1 rounded-md px-1 py-1.5", current ? "bg-accent-soft" : "hover:bg-surface-hover")}>
    <input type="checkbox" checked={selected} onClick={onSelect} onChange={() => undefined} className="mt-1 size-3.5 accent-[var(--color-accent)]" />
    <button onClick={onClick} className="min-w-0 flex-1 text-left"><div className="flex items-center gap-1"><FileText size={12} className={current ? "text-accent" : "text-muted"} /><span className={cn("truncate text-xs", current ? "font-medium text-accent-strong" : "text-fg-secondary")}>{note.title}</span></div><div className="mt-0.5 pl-4 text-[10px] text-muted">{relTime(note.updated_at, lang)} · {note.word_count}</div></button>
  </div>;
}
