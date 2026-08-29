// M-Notes 页面状态：仓库快照 + 当前笔记 + 脏态自动保存 + AI 线程。
// 约定与 useChatStore 一致：SSR 安全（不在 initializer 读 localStorage）、
// 流式增量在本地累积、AbortController 挂在 store 上。
import { create } from "zustand";
import type {
  AgentMode,
  NoteDetail,
  NoteSummary,
  NotesThread,
  NotesThreadMessage,
  VaultSnapshot,
} from "./types-notes";

export type SaveState = "saved" | "dirty" | "saving" | "error" | "conflict";

/** 笔记页布局：AI 面板宽度钳制范围与默认值（仅作用于笔记模块内部）。 */
export const NOTES_LAYOUT_DEFAULTS = {
  rightWidth: 352,
  rightMin: 280,
  rightMax: 560,
} as const;

const LAYOUT_KEY = "edu-agent-notes-layout";

function clamp(n: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, Math.round(n)));
}

function persistLayout(patch: Partial<{
  aiPanelOpen: boolean; rightWidth: number;
}>) {
  if (typeof window === "undefined") return;
  const prev = JSON.parse(localStorage.getItem(LAYOUT_KEY) || "{}") as Record<string, unknown>;
  localStorage.setItem(LAYOUT_KEY, JSON.stringify({ ...prev, ...patch }));
}

interface NotesState {
  // --- layout（笔记页 AI 面板：折叠 + 拖宽，localStorage 持久化） ---
  rightWidth: number;
  focusMode: boolean;
  setRightWidth: (w: number) => void;
  hydrateLayout: () => void;
  setFocusMode: (v: boolean) => void;


  // --- vault snapshot ---
  vault: VaultSnapshot | null;
  vaultError: string;
  vaultLoading: boolean;
  loadVault: () => Promise<void>;

  // --- current note ---
  currentId: string | null;
  detail: NoteDetail | null;
  content: string; // 编辑器缓冲（可能与 detail.content 不同：用户正在改）
  saveState: SaveState;
  saveError: string;
  conflictDetail: NoteDetail | null; // 409 时的服务器最新版
  openNote: (noteId: string | null) => Promise<void>;
  setContent: (content: string) => void;
  saveNow: (extra?: { title?: string }) => Promise<void>;
  reloadCurrent: () => Promise<void>;
  closeNote: () => void;

  // --- ai panel ---
  agentMode: AgentMode;
  setAgentMode: (m: AgentMode) => void;
  aiPanelOpen: boolean;
  toggleAiPanel: () => void;
  threads: NotesThread[];
  activeThreadId: string;
  thread: NotesThreadMessage[];
  loadThreads: () => Promise<void>;
  loadThread: (threadId?: string) => Promise<void>;
  setActiveThread: (threadId: string) => Promise<void>;
  aiStreaming: boolean;
  pendingAnswer: string;
  aiError: string;
  aborter: AbortController | null;

  // --- live updates from agent (SSE) ---
  applyRemoteUpdate: (noteId: string, content: string, revision: number) => void;

  // --- selectors helpers ---
  noteById: (id: string) => NoteSummary | undefined;
}

const EMPTY_VAULT: VaultSnapshot = {
  folders: [],
  notes: [],
  tags: {},
  custom_templates: [],
  stats: {
    note_count: 0,
    folder_count: 0,
    link_count: 0,
    unresolved_links: [],
    due_review_count: 0,
    due_review_ids: [],
    pending_suggestions: 0,
  },
};

export const useNotesStore = create<NotesState>((set, get) => ({
  rightWidth: NOTES_LAYOUT_DEFAULTS.rightWidth,
  focusMode: false,
  setRightWidth: (w) => {
    const width = clamp(w, NOTES_LAYOUT_DEFAULTS.rightMin, NOTES_LAYOUT_DEFAULTS.rightMax);
    persistLayout({ rightWidth: width });
    set({ rightWidth: width });
  },
  hydrateLayout: () => {
    if (typeof window === "undefined") return;
    try {
      // 旧版本 localStorage 可能残留 leftOpen/leftWidth 字段，读取时自然忽略
      const raw = JSON.parse(localStorage.getItem(LAYOUT_KEY) || "{}") as {
        aiPanelOpen?: boolean; rightWidth?: number;
      };
      const patch: Partial<NotesState> = {};
      if (typeof raw.aiPanelOpen === "boolean") patch.aiPanelOpen = raw.aiPanelOpen;
      if (typeof raw.rightWidth === "number") {
        patch.rightWidth = clamp(raw.rightWidth,
          NOTES_LAYOUT_DEFAULTS.rightMin, NOTES_LAYOUT_DEFAULTS.rightMax);
      }
      if (Object.keys(patch).length > 0) set(patch);
    } catch { /* 损坏的布局 JSON 直接忽略 */ }
  },
  setFocusMode: (v) => set({ focusMode: v }),

  vault: null,
  vaultError: "",
  vaultLoading: false,
  loadVault: async () => {
    set({ vaultLoading: true });
    try {
      const { getVault } = await import("./api-notes");
      const vault = await getVault();
      set({ vault, vaultError: "", vaultLoading: false });
    } catch (e) {
      set({ vaultError: e instanceof Error ? e.message : "加载失败",
           vaultLoading: false });
    }
  },

  currentId: null,
  detail: null,
  content: "",
  saveState: "saved",
  saveError: "",
  conflictDetail: null,
  openNote: async (noteId) => {
    if (!noteId) {
      set({ currentId: null, detail: null, content: "",
            saveState: "saved", saveError: "", conflictDetail: null });
      return;
    }
    try {
      const { getNote } = await import("./api-notes");
      const detail = await getNote(noteId);
      // 切换前若正在编辑旧笔记，先尽力保存一次
      const prev = get().detail;
      if (prev && get().saveState === "dirty") await get().saveNow();
      set({ currentId: noteId, detail, content: detail.content,
            saveState: "saved", saveError: "", conflictDetail: null });
    } catch (e) {
      set({ saveError: e instanceof Error ? e.message : "打开失败" });
    }
  },
  setContent: (content) => {
    const detail = get().detail;
    set({ content, saveState: "dirty",
          saveError: "",
          conflictDetail: null,
          detail: detail
            ? { ...detail, note: { ...detail.note,
                word_count: content.replace(/\s/g, "").length } }
            : null });
  },
  saveNow: async (extra) => {
    const { currentId, detail, content } = get();
    if (!currentId || !detail) return;
    set({ saveState: "saving" });
    try {
      const { saveNote } = await import("./api-notes");
      await saveNote(currentId, {
        title: extra?.title ?? detail.note.title,
        content,
        base_revision: detail.note.revision,
      });
      const { getNote } = await import("./api-notes");
      const fresh = await getNote(currentId);
      set({ detail: fresh, saveState: "saved", saveError: "",
            conflictDetail: null });
      void get().loadVault();
    } catch (e) {
      const err = e as Error & { status?: number; body?: {
        note?: NoteSummary; content?: string } };
      if (err.status === 409 && err.body?.note) {
        set({ saveState: "conflict", saveError: err.message,
              conflictDetail: {
                note: err.body.note,
                content: err.body.content || "",
                backlinks: [], links: { resolved: [], unresolved: [] },
                inline_tags: [],
              } });
      } else {
        set({ saveState: "error",
              saveError: err.message || "保存失败" });
      }
    }
  },
  reloadCurrent: async () => {
    const id = get().currentId;
    if (id) await get().openNote(id);
  },
  closeNote: () => {
    get().openNote(null);
  },

  agentMode: "collab",
  setAgentMode: (m) => {
    if (typeof window !== "undefined") {
      localStorage.setItem("edu-agent-notes-mode", m);
    }
    set({ agentMode: m });
    void import("./api-notes").then((api) => api.patchNotesThread(get().activeThreadId, { mode: m })).catch(() => undefined);
  },
  aiPanelOpen: true,
  toggleAiPanel: () => set((s) => {
    persistLayout({ aiPanelOpen: !s.aiPanelOpen });
    return { aiPanelOpen: !s.aiPanelOpen };
  }),
  threads: [],
  activeThreadId: typeof window !== "undefined"
    ? localStorage.getItem("edu-agent-notes-thread") || "default"
    : "default",
  thread: [],
  loadThreads: async () => {
    try {
      const { getNotesThreads } = await import("./api-notes");
      const { threads } = await getNotesThreads();
      set({ threads });
      if (!threads.some((t) => t.thread_id === get().activeThreadId)) {
        await get().setActiveThread(threads[0]?.thread_id || "default");
      }
    } catch {
      set({ threads: [] });
    }
  },
  loadThread: async (threadId) => {
    const id = threadId || get().activeThreadId;
    try {
      const { getNotesThread } = await import("./api-notes");
      const result = await getNotesThread(id);
      set({ thread: result.messages, activeThreadId: result.thread_id,
            agentMode: (result.mode || "collab") as AgentMode });
    } catch {
      set({ thread: [] });
    }
  },
  setActiveThread: async (threadId) => {
    if (typeof window !== "undefined") localStorage.setItem("edu-agent-notes-thread", threadId);
    set({ activeThreadId: threadId, thread: [] });
    await get().loadThread(threadId);
  },
  aiStreaming: false,
  pendingAnswer: "",
  aiError: "",
  aborter: null,

  applyRemoteUpdate: (noteId, content, revision) => {
    const state = get();
    // 用户没在改这份笔记时，热更新编辑器缓冲；否则只提示（避免踩掉输入）
    if (state.currentId === noteId && state.saveState !== "dirty") {
      set({ content, saveState: "saved",
            detail: state.detail
              ? { ...state.detail, content,
                  note: { ...state.detail.note, revision } }
              : null });
    }
    void state.loadVault();
  },

  noteById: (id) =>
    (get().vault || EMPTY_VAULT).notes.find((n) => n.id === id),
}));
