// M-Notes 笔记仓库的前端类型。字段与 backend/app/core/notes.py 的
// vault_summary / note_summary / suggestions 投影一一对应。

export interface NotesFolder {
  id: string;
  name: string;
  parent_id: string;
  created_at: number;
  updated_at: number;
  note_count: number;
}

export interface NoteReviewState {
  enabled: boolean;
  next_review_at: number;
  easiness: number;
  interval: number;
  repetitions: number;
}

export interface NoteSource {
  workspace_id?: string;
  session_ids?: string[];
  textbook_ids?: string[];
  use_error_notebook?: boolean;
}

export interface NoteSummary {
  id: string;
  title: string;
  folder_id: string;
  tags: string[];
  template_id: string;
  status: "draft" | "active" | "archived";
  revision: number;
  source: NoteSource;
  review: NoteReviewState;
  created_at: number;
  updated_at: number;
  created_by: string;
  word_count: number;
  links_rewritten?: number;
}

export interface VaultStats {
  note_count: number;
  folder_count: number;
  link_count: number;
  unresolved_links: string[];
  due_review_count: number;
  due_review_ids: string[];
  pending_suggestions: number;
}

export interface VaultSnapshot {
  folders: NotesFolder[];
  notes: NoteSummary[];
  tags: Record<string, number>;
  custom_templates: CustomTemplate[];
  stats: VaultStats;
}

export interface NoteResourceLink {
  type: "note" | "session" | "notes_thread";
  resource_id: string;
  url: string;
  title: string;
  status: "resolved" | "missing" | "deleted";
  resolved: boolean;
  folder_id?: string;
  folder_name?: string;
  message_count?: number;
  updated_at?: number;
}

export interface ResolvedLink {
  title: string;
  note_id: string;
}

export interface NoteDetail {
  note: NoteSummary;
  content: string;
  backlinks: NoteSummary[];
  links: { resolved: ResolvedLink[]; unresolved: string[]; resources?: NoteResourceLink[] };
  inline_tags: string[];
}

export interface NoteRevision {
  revision: number;
  ts: number;
  author: string;
  word_count: number;
}

export interface NoteTemplate {
  id: string;
  name: string;
  name_en?: string;
  description?: string;
  folder_hint?: string;
  suggested_tags?: string[];
  review_enabled?: boolean;
  sources?: string[];
  skeleton?: string;
  content?: string; // 自定义模板正文
  builtin: boolean;
  created_at?: number;
}

export interface CustomTemplate {
  id: string;
  name: string;
  content: string;
  created_at: number;
}

export interface NoteSuggestion {
  id: string;
  note_id: string;
  kind: "replace" | "append";
  proposed_content: string;
  summary: string;
  status: "pending" | "applied" | "dismissed";
  created_at: number;
}

export interface NotesThread {
  thread_id: string;
  title: string;
  created_at: number;
  updated_at: number;
  message_count: number;
  mode: AgentMode;
  last_message?: NotesThreadMessage | null;
}

export interface NotesThreadMessage {
  role: "user" | "assistant";
  content: string;
  context: { scope?: string; note_id?: string; mode?: string; thread_id?: string; attachments?: { id: string; filename: string }[] };
  ts: number;
}

export interface GraphNode {
  id: string;
  title: string;
  folder_id: string;
  tags: string[];
  ghost: boolean;
  kind: "note" | "session" | "notes_thread" | "textbook" | "ghost";
  status?: "resolved" | "unresolved" | "missing" | "deleted";
  resource_id?: string;
  folder_name?: string;
  message_count?: number;
  updated_at?: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  title: string;
  resolved: boolean;
  kind: "note" | "session" | "notes_thread" | "textbook" | "unresolved";
  status?: string;
}

export interface NotesGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

/** 笔记助手四模式：plan 只讨论出计划；collab 提案待确认；auto 直接写；ask 仅答疑。 */
export type AgentMode = "plan" | "collab" | "auto" | "ask";

/** 笔记智能体 SSE 事件（generate 与 chat/stream 共用词汇表）。 */
export interface NotesSSEEvent {
  type: string;
  run_id?: string;
  stage?: string;
  tool?: string;
  status?: string;
  can_stop?: boolean;
  [key: string]: unknown;
}
