// M-Notes REST + SSE 客户端。全部走 apiFetch（附 JWT；SSE 用 fetch 流式
// 解析，与 lib/api.ts 的 chatStream 同一套行解析器约定）。
import { apiFetch } from "./api-fetch";
import { API_BASE } from "./api";
import type {
  DueReview,
  NoteDetail,
  NoteRevision,
  NoteSuggestion,
  NoteSummary,
  NotesGraph,
  NotesSSEEvent,
  NotesThread,
  NotesThreadMessage,
  NoteTemplate,
  VaultSnapshot,
} from "./types-notes";

const BASE = API_BASE;

async function jsonOrThrow<T>(res: Response, what: string): Promise<T> {
  if (!res.ok) {
    let detail = `${what} failed: ${res.status}`;
    let body: unknown = null;
    try {
      body = await res.json();
      if (body && typeof (body as { detail?: unknown }).detail === "string") {
        detail = (body as { detail: string }).detail;
      }
    } catch {
      /* keep status message */
    }
    const err = new Error(detail) as Error & { status?: number; body?: unknown };
    err.status = res.status;
    err.body = body;
    throw err;
  }
  return res.json() as Promise<T>;
}

// --- vault -----------------------------------------------------------------

export async function getVault(): Promise<VaultSnapshot> {
  return jsonOrThrow(await apiFetch(`${BASE}/notes/vault`), "Get vault");
}

export async function searchNotes(q: string): Promise<{ results: NoteSummary[] }> {
  return jsonOrThrow(
    await apiFetch(`${BASE}/notes/search?q=${encodeURIComponent(q)}`),
    "Search notes");
}

export async function getNotesGraph(): Promise<NotesGraph> {
  return jsonOrThrow(await apiFetch(`${BASE}/notes/graph`), "Get graph");
}

export async function getDueReviews(): Promise<{ due: DueReview[] }> {
  return jsonOrThrow(await apiFetch(`${BASE}/notes/reviews/due`), "Get due reviews");
}

// --- note crud ----------------------------------------------------------------

export async function createNote(body: {
  title?: string;
  folder_id?: string;
  template_id?: string;
  content?: string;
  tags?: string[];
  review_enabled?: boolean;
  status?: string;
}): Promise<{ note: NoteSummary }> {
  return jsonOrThrow(
    await apiFetch(`${BASE}/notes/notes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
    "Create note");
}

export async function getNote(noteId: string): Promise<NoteDetail> {
  return jsonOrThrow(
    await apiFetch(`${BASE}/notes/notes/${encodeURIComponent(noteId)}`),
    "Get note");
}

export async function saveNote(
  noteId: string,
  body: { title?: string; content: string; base_revision?: number; summary?: string },
): Promise<{ note: NoteSummary }> {
  return jsonOrThrow(
    await apiFetch(`${BASE}/notes/notes/${encodeURIComponent(noteId)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
    "Save note");
}

export async function patchNote(
  noteId: string,
  body: {
    title?: string;
    folder_id?: string | null;
    tags?: string[];
    status?: string;
    review_enabled?: boolean;
  },
): Promise<{ note: NoteSummary }> {
  return jsonOrThrow(
    await apiFetch(`${BASE}/notes/notes/${encodeURIComponent(noteId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
    "Patch note");
}

export async function deleteNote(noteId: string): Promise<{ status: string }> {
  return jsonOrThrow(
    await apiFetch(`${BASE}/notes/notes/${encodeURIComponent(noteId)}`, {
      method: "DELETE",
    }),
    "Delete note");
}

export async function submitNoteReview(
  noteId: string,
  quality: number,
): Promise<{ review: NoteSummary["review"]; note: NoteSummary }> {
  return jsonOrThrow(
    await apiFetch(`${BASE}/notes/notes/${encodeURIComponent(noteId)}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ quality }),
    }),
    "Review note");
}

// --- folders ----------------------------------------------------------------------

export async function createNotesFolder(name: string, parentId = ""): Promise<{ folder: { id: string; name: string; parent_id: string } }> {
  return jsonOrThrow(
    await apiFetch(`${BASE}/notes/folders`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, parent_id: parentId }),
    }),
    "Create folder");
}

export async function renameNotesFolder(folderId: string, name?: string, parentId?: string): Promise<void> {
  await jsonOrThrow(
    await apiFetch(`${BASE}/notes/folders/${encodeURIComponent(folderId)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...(name !== undefined ? { name } : {}), ...(parentId !== undefined ? { parent_id: parentId } : {}) }),
    }),
    "Rename folder");
}

export async function deleteNotesFolder(folderId: string): Promise<{ moved_to_unfiled: number }> {
  return jsonOrThrow(
    await apiFetch(`${BASE}/notes/folders/${encodeURIComponent(folderId)}`, {
      method: "DELETE",
    }),
    "Delete folder");
}

export async function bulkMoveNotes(noteIds: string[], folderId: string): Promise<{ moved: string[]; missing: string[] }> {
  return jsonOrThrow(await apiFetch(`${BASE}/notes/bulk/move`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ note_ids: noteIds, folder_id: folderId }) }), "Move notes");
}

export async function bulkDeleteNotes(noteIds: string[]): Promise<{ archived: unknown[]; missing: string[] }> {
  return jsonOrThrow(await apiFetch(`${BASE}/notes/bulk/delete`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ note_ids: noteIds }) }), "Delete notes");
}

// --- revisions -----------------------------------------------------------------------

export async function getNoteRevisions(noteId: string): Promise<{ revisions: NoteRevision[] }> {
  return jsonOrThrow(
    await apiFetch(`${BASE}/notes/notes/${encodeURIComponent(noteId)}/revisions`),
    "Get revisions");
}

export async function readNoteRevision(noteId: string, revision: number): Promise<{ content: string }> {
  return jsonOrThrow(
    await apiFetch(
      `${BASE}/notes/notes/${encodeURIComponent(noteId)}/revisions/${revision}`),
    "Read revision");
}

export async function restoreNoteRevision(
  noteId: string,
  revision: number,
): Promise<{ note: NoteSummary }> {
  return jsonOrThrow(
    await apiFetch(
      `${BASE}/notes/notes/${encodeURIComponent(noteId)}/revisions/${revision}/restore`,
      { method: "POST" }),
    "Restore revision");
}

// --- templates --------------------------------------------------------------------------

export async function getNoteTemplates(): Promise<{ templates: NoteTemplate[] }> {
  return jsonOrThrow(await apiFetch(`${BASE}/notes/templates`), "Get templates");
}

export async function createCustomTemplate(name: string, content: string): Promise<{ template: NoteTemplate }> {
  return jsonOrThrow(
    await apiFetch(`${BASE}/notes/templates`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, content }),
    }),
    "Create template");
}

export async function deleteCustomTemplate(templateId: string): Promise<void> {
  await jsonOrThrow(
    await apiFetch(`${BASE}/notes/templates/${encodeURIComponent(templateId)}`, {
      method: "DELETE",
    }),
    "Delete template");
}

// --- suggestions ---------------------------------------------------------------------------

export async function getSuggestions(status?: string): Promise<{ suggestions: NoteSuggestion[] }> {
  const q = status ? `?status=${encodeURIComponent(status)}` : "";
  return jsonOrThrow(await apiFetch(`${BASE}/notes/suggestions${q}`), "Get suggestions");
}

export async function applySuggestion(id: string): Promise<{ note: NoteSummary; content: string }> {
  return jsonOrThrow(
    await apiFetch(`${BASE}/notes/suggestions/${encodeURIComponent(id)}/apply`, {
      method: "POST",
    }),
    "Apply suggestion");
}

export async function dismissSuggestion(id: string): Promise<void> {
  await jsonOrThrow(
    await apiFetch(`${BASE}/notes/suggestions/${encodeURIComponent(id)}/dismiss`, {
      method: "POST",
    }),
    "Dismiss suggestion");
}

// --- thread ---------------------------------------------------------------------------------

export async function getNotesThreads(): Promise<{ threads: NotesThread[] }> {
  return jsonOrThrow(await apiFetch(`${BASE}/notes/threads`), "Get threads");
}

export async function createNotesThread(title = ""): Promise<{ thread: NotesThread & { messages: NotesThreadMessage[] } }> {
  return jsonOrThrow(await apiFetch(`${BASE}/notes/threads`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title }) }), "Create thread");
}

export async function getNotesThread(threadId = "default"): Promise<{ thread_id: string; title: string; mode: string; messages: NotesThreadMessage[] }> {
  return jsonOrThrow(await apiFetch(`${BASE}/notes/threads/${encodeURIComponent(threadId)}`), "Get thread");
}

export async function patchNotesThread(threadId: string, body: { title?: string; mode?: string }): Promise<void> {
  await jsonOrThrow(await apiFetch(`${BASE}/notes/threads/${encodeURIComponent(threadId)}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }), "Update thread");
}

export async function deleteNotesThread(threadId: string): Promise<void> {
  await jsonOrThrow(await apiFetch(`${BASE}/notes/threads/${encodeURIComponent(threadId)}`, { method: "DELETE" }), "Delete thread");
}

export async function clearNotesThread(threadId = "default"): Promise<void> {
  await jsonOrThrow(await apiFetch(`${BASE}/notes/threads/${encodeURIComponent(threadId)}/messages`, { method: "DELETE" }), "Clear thread");
}

// --- export -----------------------------------------------------------------------------------

export async function exportNoteFile(noteId: string, title: string): Promise<void> {
  const res = await apiFetch(`${BASE}/notes/notes/${encodeURIComponent(noteId)}/export`);
  if (!res.ok) throw new Error(`Export failed: ${res.status}`);
  downloadBlob(await res.blob(), `${sanitizeFilename(title)}.md`, "text/markdown");
}

export async function exportVaultZip(folderId?: string, folderName?: string): Promise<void> {
  const q = folderId ? `?folder_id=${encodeURIComponent(folderId)}` : "";
  const res = await apiFetch(`${BASE}/notes/export${q}`);
  if (!res.ok) throw new Error(`Export failed: ${res.status}`);
  const name = folderName
    ? `${sanitizeFilename(folderName)}.zip`
    : "notes_export.zip";
  downloadBlob(await res.blob(), name, "application/zip");
}

function sanitizeFilename(name: string): string {
  return (name || "note").replace(/[\\/:*?"<>|\s]+/g, "_").slice(0, 60) || "note";
}

function downloadBlob(blob: Blob, filename: string, mime: string): void {
  const url = URL.createObjectURL(new Blob([blob], { type: mime }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// --- SSE 流（与 chatStream 相同的行解析器）---------------------------------------------------

async function* sseStream(
  url: string,
  body: unknown,
  signal?: AbortSignal,
): AsyncGenerator<NotesSSEEvent> {
  const res = await apiFetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) throw new Error(`Notes stream failed: ${res.status}`);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let currentEvent = "message";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.startsWith("event:")) currentEvent = trimmed.slice(6).trim();
      else if (trimmed.startsWith("data:")) {
        try {
          const payload = JSON.parse(trimmed.slice(5).trim());
          payload.type = currentEvent;
          yield payload as NotesSSEEvent;
        } catch {
          /* skip malformed frame */
        }
      }
    }
  }
}

export function notesGenerateStream(
  body: {
    template_id: string;
    sources?: {
      /** 来源三形态：sessions（教材/文件按对话引用推导）/ workspace / textbooks */
      source_mode?: "sessions" | "workspace" | "textbooks";
      workspace_id?: string;
      session_ids?: string[];
      textbook_ids?: string[];
      use_error_notebook?: boolean;
    };
    target?: { folder_id?: string; title?: string };
    instructions?: string;
  },
  signal?: AbortSignal,
): AsyncGenerator<NotesSSEEvent> {
  return sseStream(`${BASE}/notes/generate`, body, signal);
}

export function notesChatStream(
  body: {
    message: string;
    context?: { note_id?: string; scope?: string };
    mode?: string;
    /** approve_plan = 批复线程中最后一条助手消息为计划并自动执行 */
    action?: string;
    /** /notes/upload 返回的图片附件 {id, filename}（多模态通道） */
    attachments?: { id: string; filename: string }[];
    thread_id?: string;
  },
  signal?: AbortSignal,
): AsyncGenerator<NotesSSEEvent> {
  return sseStream(`${BASE}/notes/chat/stream`, body, signal);
}

export interface NotesUploadResult {
  id?: string;
  filename: string;
  error?: string;
  warning?: string | null;
  char_count?: number;
  chunk_count?: number;
  ocr_used?: boolean;
  /** 图片的 OCR 预览文本（发送时包成 <ocr_material> 前缀） */
  preview_text?: string | null;
}

export async function notesUpload(
  files: File[],
): Promise<{ results: NotesUploadResult[] }> {
  const form = new FormData();
  for (const f of files) form.append("files", f, f.name);
  const res = await apiFetch(`${BASE}/notes/upload`, { method: "POST", body: form });
  if (!res.ok) throw new Error(`Notes upload failed: ${res.status}`);
  return res.json();
}
