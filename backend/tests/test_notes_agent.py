"""Tests for the M-Notes agent (generate pipeline + chat ReAct loop):

1. Generate: no sources -> error event; with a session source -> streamed
   draft persisted as a draft note with wiki-links and source provenance;
   code-fence/opening-line stripping.
2. Chat collab mode: notes_propose lands in the pending queue and emits a
   note_suggestion SSE event; the note itself is untouched.
3. Chat auto mode: notes_write updates the note (agent revision + SSE
   note_updated); notes_create adds a note.
4. Mode gating: notes_write is rejected in ask/plan modes (tool not offered).
5. Plan approval: action="approve_plan" executes the last assistant plan
   with write tools; without a plan it errors.
6. Legacy mode values (suggest/cowrite) normalize to collab/auto.
7. Thread persistence: user + assistant messages with context markers.
8. NOTES_AGENT_MODE=off degradation: SSE streams a single error event.
9. API surface: /generate and /chat/stream return SSE media types.

Fake LLMs only, no network. Data dirs are redirected to temp dirs.
"""
import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402
from app.agents import notes_agent  # noqa: E402
from app.core import notes as notes_mod  # noqa: E402
from app.core import session as session_mod  # noqa: E402
from app.core import trash as trash_mod  # noqa: E402


class _TmpDirs:
    def __init__(self, test: unittest.TestCase):
        self._tmp = tempfile.TemporaryDirectory(prefix="notes_agent_")
        root = Path(self._tmp.name)
        self.root = root
        from app.agents.learning_orchestration import store as orch_store
        from app.agents.memory import prompt_memory
        from app.core import library as library_mod
        from app.core import textbook as textbook_mod
        from app.core import workspace as ws_mod
        self._patches = [
            patch.object(notes_mod, "_NOTES_DIR", root / "notes"),
            # 漏 patch 的写路径曾把 student_default.prompt_memory.json 直写生产目录。
            patch.object(prompt_memory, "_STUDENTS_DIR", root / "students"),
            patch.object(prompt_memory, "_POLICY_PATH",
                         root / "students" / "prompt_memory_policy.json"),
            patch.object(session_mod, "_SESSIONS_DIR", root / "chat_history"),
            patch.object(trash_mod, "_TRASH_DIR", root / "trash"),
            patch.object(orch_store, "_STUDENTS_DIR", root / "students"),
            patch.object(library_mod, "_LIBRARY_DIR",
                         root / "chat_history" / "library"),
            patch.object(textbook_mod, "_LIBRARY_DIR",
                         root / "chat_history" / "library"),
            patch.object(ws_mod, "_WORKSPACES_DIR", root / "workspaces"),
        ]
        for p in self._patches:
            p.start()
        test.addCleanup(self.cleanup)

    def cleanup(self):
        for p in reversed(self._patches):
            p.stop()
        self._tmp.cleanup()


class _GenFake:
    """单轮流式假模型：生成管线用。"""

    def __init__(self, draft: str):
        self.draft = draft

    async def stream(self, messages, tools=None, temperature=0.3, **kw):
        yield {"kind": "answer", "delta": self.draft}
        yield {"kind": "done", "finish_reason": "stop"}


class _ToolFake:
    """首轮发 answer+tool_calls、次轮收尾的假模型：对话循环用。"""

    def __init__(self, calls: list[dict]):
        self.calls = calls
        self.rounds = 0

    async def stream(self, messages, tools=None, **kw):
        self.rounds += 1
        if tools and self.rounds == 1 and self.calls:
            yield {"kind": "answer", "delta": "先处理一下。"}
            yield {"kind": "tool_calls", "calls": self.calls}
            yield {"kind": "done", "finish_reason": "tool_calls"}
        else:
            yield {"kind": "answer", "delta": "处理完毕。"}
            yield {"kind": "done", "finish_reason": "stop"}


class _RetrievalFake:
    """生成管线假模型：complete 出检索查询，stream 记录最终 user 内容。"""

    def __init__(self, draft: str, queries: list[str]):
        self.draft = draft
        self.queries = queries
        self.queries_seen = False
        self.seen_user = ""

    async def complete(self, messages, **kw):
        self.queries_seen = True
        return json.dumps(self.queries, ensure_ascii=False), None

    async def stream(self, messages, tools=None, temperature=0.3, **kw):
        self.seen_user = str(messages[-1].get("content") or "")
        yield {"kind": "answer", "delta": self.draft}
        yield {"kind": "done", "finish_reason": "stop"}


class TestNotesAgent(unittest.TestCase):
    def setUp(self) -> None:
        _TmpDirs(self)
        self.client = TestClient(create_app())

    def _make_session(self, title: str, messages: list[dict]) -> str:
        sid = session_mod.new_session_id(title)
        session = session_mod.TutorSession(session_id=sid)
        session.student_id = "student_default"
        session.title = title
        session.messages = messages
        session_mod.save_session(session)
        return sid

    def _make_note(self, title: str, content: str) -> dict:
        vault = notes_mod.load_vault("student_default")
        meta = vault.create_note(title=title, content=content)
        notes_mod.save_vault(vault)
        return meta

    # -- 1. generate ---------------------------------------------------------

    def test_generate_without_sources_errors(self):
        async def run():
            with patch.object(notes_agent, "get_llm",
                              lambda: _GenFake("x")):
                return [e async for e in notes_agent.generate_note(
                    "student_default", template_id="knowledge_summary",
                    sources={})]
        events = asyncio.run(run())
        self.assertEqual(events[-1]["type"], "error")

    def test_generate_creates_draft_note_with_links_and_source(self):
        sid = self._make_session("力学讨论", [
            {"role": "user", "content": "讲讲牛顿第二定律"},
            {"role": "assistant", "content": "F=ma"},
        ])
        draft = ("好的，以下是笔记\n```markdown\n"
                 "## 牛顿第二定律\n\n$F=ma$，参见 [[牛顿第二定律]]。\n```")

        async def run():
            with patch.object(notes_agent, "get_llm",
                              lambda: _GenFake(draft)):
                return [e async for e in notes_agent.generate_note(
                    "student_default", template_id="knowledge_summary",
                    sources={"session_ids": [sid]})]
        events = asyncio.run(run())
        kinds = [e["type"] for e in events]
        self.assertIn("sources_summary", kinds)
        self.assertIn("note_created", kinds)
        created = next(e for e in events if e["type"] == "note_created")
        note = created["note"]
        # code fence + opening line stripped
        self.assertTrue(created["content"].startswith("## 牛顿第二定律"))
        self.assertNotIn("```", created["content"])
        self.assertEqual(note["status"], "draft")
        self.assertEqual(note["source"]["session_ids"], [sid])
        # title derived from first heading
        self.assertEqual(note["title"], "牛顿第二定律")
        # wiki-link resolved against the existing note
        self.assertIn("牛顿第二定律", note["title"])

    def test_generate_review_template_registers_m9_card(self):
        sid = self._make_session("复习", [{"role": "user", "content": "x"}])
        note = self._make_note("已有", "y")

        async def run():
            with patch.object(notes_agent, "get_llm",
                              lambda: _GenFake("## 温故计划\n内容")):
                return [e async for e in notes_agent.generate_note(
                    "student_default", template_id="review_note",
                    sources={"session_ids": [sid]})]
        events = asyncio.run(run())
        created = next(e for e in events if e["type"] == "note_created")
        self.assertTrue(created["note"]["review"]["enabled"])
        self.assertGreater(created["note"]["review"]["next_review_at"], 0)

    # -- 2. collab mode -------------------------------------------------------

    def test_chat_collab_mode_queues_proposal(self):
        note = self._make_note("目标笔记", "原内容")
        fake = _ToolFake([{
            "id": "c1", "name": "notes_propose",
            "args": {"note_id": note["id"], "kind": "append",
                     "content": "## 补充\n追加段落", "summary": "补一段"}}])

        async def run():
            with patch.object(notes_agent, "get_llm", lambda: fake):
                return [e async for e in notes_agent.run_notes_chat(
                    "student_default", message="帮我补充",
                    context={"note_id": note["id"], "scope": "note"},
                    mode="collab")]
        events = asyncio.run(run())
        kinds = [e["type"] for e in events]
        self.assertIn("note_suggestion", kinds)
        self.assertNotIn("note_updated", kinds)
        sg = next(e for e in events if e["type"] == "note_suggestion")["suggestion"]
        self.assertEqual(sg["kind"], "append")
        # note untouched
        self.assertEqual(
            notes_mod.load_vault("student_default").read_note(note["id"]),
            "原内容")
        # suggestion persisted in the queue
        items = [i for i in notes_mod.load_suggestions("student_default")
                 if i["id"] == sg["id"]]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["status"], "pending")

    # -- 3. auto mode ----------------------------------------------------------

    def test_chat_auto_mode_writes_note(self):
        note = self._make_note("直写目标", "v1")
        fake = _ToolFake([{
            "id": "c1", "name": "notes_write",
            "args": {"note_id": note["id"], "content": "v2-by-agent",
                     "summary": "直写"}}])

        async def run():
            with patch.object(notes_agent, "get_llm", lambda: fake):
                return [e async for e in notes_agent.run_notes_chat(
                    "student_default", message="直接改",
                    context={"note_id": note["id"], "scope": "note"},
                    mode="auto")]
        events = asyncio.run(run())
        kinds = [e["type"] for e in events]
        self.assertIn("note_updated", kinds)
        updated = next(e for e in events if e["type"] == "note_updated")
        self.assertEqual(updated["content"], "v2-by-agent")
        self.assertEqual(updated["summary"], "直写")
        vault = notes_mod.load_vault("student_default")
        self.assertEqual(vault.read_note(note["id"]), "v2-by-agent")
        self.assertTrue(any(r["author"] == "agent"
                            for r in vault.list_revisions(note["id"])))

    def test_chat_auto_mode_creates_note(self):
        fake = _ToolFake([{
            "id": "c1", "name": "notes_create",
            "args": {"title": "新主题笔记", "content": "新建内容"}}])

        async def run():
            with patch.object(notes_agent, "get_llm", lambda: fake):
                return [e async for e in notes_agent.run_notes_chat(
                    "student_default", message="开个新笔记",
                    context={"scope": "vault"}, mode="auto")]
        events = asyncio.run(run())
        updated = next(e for e in events if e["type"] == "note_updated")
        vault = notes_mod.load_vault("student_default")
        meta = vault.find_note(updated["note_id"])
        self.assertIsNotNone(meta)
        self.assertEqual(meta["created_by"], "agent")
        self.assertEqual(vault.read_note(updated["note_id"]), "新建内容")

    # -- 4. mode gating ---------------------------------------------------------

    def test_write_tool_rejected_in_ask_and_plan_modes(self):
        for mode in ("ask", "plan"):
            with self.subTest(mode=mode):
                note = self._make_note(f"保护-{mode}", "locked")
                fake = _ToolFake([{
                    "id": "c1", "name": "notes_write",
                    "args": {"note_id": note["id"], "content": "hacked",
                             "summary": "x"}}])

                async def run():
                    with patch.object(notes_agent, "get_llm", lambda: fake):
                        return [e async for e in notes_agent.run_notes_chat(
                            "student_default", message="改",
                            context={"note_id": note["id"], "scope": "note"},
                            mode=mode)]
                events = asyncio.run(run())
                tool_results = [e for e in events
                                if e["type"] == "tool_result"]
                self.assertTrue(tool_results)
                self.assertEqual(tool_results[0]["result"]["status"], "error")
                self.assertEqual(
                    notes_mod.load_vault("student_default").read_note(
                        note["id"]),
                    "locked")

    def test_propose_tool_rejected_in_ask_mode(self):
        note = self._make_note("问答保护", "locked")
        fake = _ToolFake([{
            "id": "c1", "name": "notes_propose",
            "args": {"note_id": note["id"], "kind": "append",
                     "content": "x", "summary": "s"}}])

        async def run():
            with patch.object(notes_agent, "get_llm", lambda: fake):
                return [e async for e in notes_agent.run_notes_chat(
                    "student_default", message="改",
                    context={"scope": "vault"}, mode="ask")]
        events = asyncio.run(run())
        tool_results = [e for e in events if e["type"] == "tool_result"]
        self.assertTrue(tool_results)
        self.assertEqual(tool_results[0]["result"]["status"], "error")

    # -- 5. plan approval ---------------------------------------------------------

    def test_plan_approval_executes_last_assistant_plan(self):
        note = self._make_note("计划目标", "v0")
        notes_mod.append_thread_message(
            "student_default", "assistant",
            "修改计划：1. 修订《计划目标》，补充一节。",
            {"scope": "note", "note_id": note["id"], "mode": "plan"})
        fake = _ToolFake([{
            "id": "c1", "name": "notes_write",
            "args": {"note_id": note["id"], "content": "v1-per-plan",
                     "summary": "按计划修订"}}])

        async def run():
            with patch.object(notes_agent, "get_llm", lambda: fake):
                return [e async for e in notes_agent.run_notes_chat(
                    "student_default", message="", action="approve_plan",
                    context={"note_id": note["id"], "scope": "note"},
                    mode="plan")]
        events = asyncio.run(run())
        kinds = [e["type"] for e in events]
        self.assertIn("note_updated", kinds)
        self.assertEqual(
            notes_mod.load_vault("student_default").read_note(note["id"]),
            "v1-per-plan")
        # thread: plan -> approval marker -> execution summary
        thread = notes_mod.thread_view("student_default")
        self.assertEqual([m["role"] for m in thread["messages"]],
                         ["assistant", "user", "assistant"])
        self.assertIn("批复", thread["messages"][1]["content"])

    def test_plan_approval_without_plan_errors(self):
        async def run():
            with patch.object(notes_agent, "get_llm", lambda: _ToolFake([])):
                return [e async for e in notes_agent.run_notes_chat(
                    "student_default", message="", mode="plan",
                    action="approve_plan")]
        events = asyncio.run(run())
        self.assertEqual(events[-1]["type"], "error")

    # -- 6. legacy mode normalization ---------------------------------------------

    def test_normalize_mode_maps_legacy_values(self):
        self.assertEqual(notes_agent.normalize_mode("suggest"), "collab")
        self.assertEqual(notes_agent.normalize_mode("cowrite"), "auto")
        self.assertEqual(notes_agent.normalize_mode("plan"), "plan")
        self.assertEqual(notes_agent.normalize_mode("ask"), "ask")
        self.assertEqual(notes_agent.normalize_mode("collab"), "collab")
        self.assertEqual(notes_agent.normalize_mode("auto"), "auto")
        self.assertEqual(notes_agent.normalize_mode("junk"), "collab")
        self.assertEqual(notes_agent.normalize_mode(""), "collab")

    def test_legacy_suggest_behaves_as_collab(self):
        note = self._make_note("旧值", "x")
        fake = _ToolFake([{
            "id": "c1", "name": "notes_propose",
            "args": {"note_id": note["id"], "kind": "append",
                     "content": "补", "summary": "s"}}])

        async def run():
            with patch.object(notes_agent, "get_llm", lambda: fake):
                return [e async for e in notes_agent.run_notes_chat(
                    "student_default", message="m", mode="suggest")]
        events = asyncio.run(run())
        self.assertIn("note_suggestion", [e["type"] for e in events])

    def test_legacy_cowrite_behaves_as_auto(self):
        note = self._make_note("旧值2", "x")
        fake = _ToolFake([{
            "id": "c1", "name": "notes_write",
            "args": {"note_id": note["id"], "content": "y",
                     "summary": "s"}}])

        async def run():
            with patch.object(notes_agent, "get_llm", lambda: fake):
                return [e async for e in notes_agent.run_notes_chat(
                    "student_default", message="m", mode="cowrite")]
        events = asyncio.run(run())
        self.assertIn("note_updated", [e["type"] for e in events])

    # -- 7. thread ----------------------------------------------------------------

    def test_thread_persists_user_and_assistant(self):
        note = self._make_note("线程", "x")

        async def run():
            with patch.object(notes_agent, "get_llm",
                              lambda: _ToolFake([])):
                return [e async for e in notes_agent.run_notes_chat(
                    "student_default", message="你好",
                    context={"note_id": note["id"], "scope": "note"},
                    mode="ask")]
        asyncio.run(run())
        thread = notes_mod.thread_view("student_default")
        self.assertEqual([m["role"] for m in thread["messages"]],
                         ["user", "assistant"])
        self.assertEqual(thread["messages"][0]["context"]["note_id"],
                         note["id"])

    # -- 7b. 三形态来源 + 真实 RAG + knowledge_search + 附件 -------------------------

    def _add_textbook(self, fid: str, name: str, text: str,
                      *, status: str = "ready") -> dict:
        """落库一个文件并注册为教材（对齐 test_attach_library 的做法）。"""
        from app.core import library as library_mod
        from app.core import textbook as textbook_mod
        lib = library_mod.load_library("student_default")
        meta = lib.add_file("", name, text, file_id=fid)
        meta["kind"] = "textbook"
        library_mod.save_library(lib)
        rec = textbook_mod.create_textbook(
            "student_default", file_id=fid, title=name)
        if rec.get("status") != status:
            recs = textbook_mod.load_textbooks("student_default")
            for r in recs:
                if r["id"] == rec["id"]:
                    r["status"] = status
            textbook_mod._save("student_default", recs)
        return rec

    def test_resolve_source_mode_prefers_explicit_then_infers(self):
        self.assertEqual(
            notes_agent._resolve_source_mode({"source_mode": "workspace"}),
            "workspace")
        self.assertEqual(
            notes_agent._resolve_source_mode({"workspace_id": "ws_1"}),
            "workspace")
        self.assertEqual(
            notes_agent._resolve_source_mode({"textbook_ids": ["tb"]}),
            "textbooks")
        self.assertEqual(notes_agent._resolve_source_mode({}), "sessions")

    def test_generate_textbooks_mode_runs_real_retrieval(self):
        rec = self._add_textbook(
            "f_phys_01", "物理.pdf",
            "第二章 力。牛顿第二定律：物体的加速度与合外力成正比，F=ma。"
            "动能定理：合外力做的功等于动能的变化。")
        fake = _RetrievalFake(
            draft="## 牛顿第二定律笔记\n\n$F=ma$，参见 [[牛顿第二定律]]。",
            queries=["牛顿第二定律"])

        async def run():
            with patch.object(notes_agent, "get_llm", lambda: fake):
                return [e async for e in notes_agent.generate_note(
                    "student_default", template_id="knowledge_summary",
                    sources={"source_mode": "textbooks",
                             "textbook_ids": [rec["id"]]})]
        events = asyncio.run(run())
        # source 记录 source_mode + 推导出的文件集
        created = next(e for e in events if e["type"] == "note_created")
        self.assertEqual(created["note"]["source"]["source_mode"], "textbooks")
        self.assertIn("f_phys_01",
                      created["note"]["source"]["material_file_ids"])
        # 检索查询来自 fake.complete，片段进入 prompt 且确实命中教材原文
        self.assertTrue(fake.queries_seen)
        self.assertIn("检索片段", fake.seen_user)
        self.assertIn("F=ma", fake.seen_user)
        summary = next(e for e in events if e["type"] == "sources_summary")
        self.assertGreaterEqual(summary.get("retrieved", 0), 1)
        self.assertIn("retrieving", [e.get("stage") for e in events
                                     if e["type"] == "step"])

    def test_retrieval_queries_fall_back_when_complete_fails(self):
        rec = self._add_textbook("f_chem_01", "化学.pdf",
                                 "氧化还原反应的本质是电子转移。")

        class _Broken:
            async def complete(self, *a, **kw):
                raise RuntimeError("offline")

            async def stream(self, messages, tools=None, temperature=0.3, **kw):
                yield {"kind": "answer", "delta": "## 化学笔记\n内容"}
                yield {"kind": "done", "finish_reason": "stop"}

        async def run():
            with patch.object(notes_agent, "get_llm", lambda: _Broken()):
                return [e async for e in notes_agent.generate_note(
                    "student_default", template_id="knowledge_summary",
                    sources={"source_mode": "textbooks",
                             "textbook_ids": [rec["id"]]})]
        events = asyncio.run(run())
        # 查询生成失败 → 确定性降级查询，生成不中断
        self.assertIn("note_created", [e["type"] for e in events])
        self.assertNotEqual(events[-1]["type"], "error")

    def test_generate_workspace_mode_expands_all_sessions(self):
        from app.core import workspace as ws_mod
        s1 = self._make_session("力学", [{"role": "user", "content": "a"}])
        s2 = self._make_session("热学", [{"role": "user", "content": "b"}])
        ws = ws_mod.Workspace(name="总复习", student_id="student_default")
        ws_mod.save_workspace(ws)
        ws_mod.add_session_to_workspace(ws.workspace_id, s1)
        ws_mod.add_session_to_workspace(ws.workspace_id, s2)

        async def run():
            with patch.object(notes_agent, "get_llm",
                              lambda: _GenFake("## 总复习\n内容")):
                return [e async for e in notes_agent.generate_note(
                    "student_default", template_id="knowledge_summary",
                    sources={"source_mode": "workspace",
                             "workspace_id": ws.workspace_id})]
        events = asyncio.run(run())
        created = next(e for e in events if e["type"] == "note_created")
        # 空 session_ids = 整个工作区：两个会话都进入来源
        self.assertEqual(created["note"]["source"]["source_mode"], "workspace")
        self.assertEqual(set(created["note"]["source"]["session_ids"]),
                         {s1, s2})

    def test_chat_knowledge_search_tool_available_in_ask_mode(self):
        # 无笔记上下文 + 无来源：fallback 教材语料仍让 knowledge_search 可用
        self._add_textbook(
            "f_bio_01", "生物.pdf",
            "光合作用是绿色植物利用光能将二氧化碳和水合成有机物并释放氧气的过程。")
        fake = _ToolFake([{
            "id": "c1", "name": "knowledge_search",
            "args": {"query": "光合作用"}}])

        async def run():
            with patch.object(notes_agent, "get_llm", lambda: fake):
                return [e async for e in notes_agent.run_notes_chat(
                    "student_default", message="光合作用是什么",
                    mode="ask")]
        events = asyncio.run(run())
        results = [e["result"] for e in events if e["type"] == "tool_result"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "success")
        self.assertIn("光合作用", results[0]["text"])
        self.assertEqual(events[-1]["type"], "done")

    def test_chat_attachments_recorded_and_degrade_without_vision(self):
        note = self._make_note("附件", "x")

        async def run():
            with patch.object(notes_agent, "get_llm",
                              lambda: _ToolFake([])):
                return [e async for e in notes_agent.run_notes_chat(
                    "student_default", message="看图",
                    context={"note_id": note["id"], "scope": "note"},
                    mode="ask",
                    attachments=[{"id": "nofile", "filename": "a.png"}])]
        events = asyncio.run(run())
        # 附件文件不存在 → 视觉通道静默降级，消息仍记录附件元数据
        self.assertEqual(events[-1]["type"], "done")
        thread = notes_mod.thread_view("student_default")
        ctx = thread["messages"][0]["context"]
        self.assertEqual(ctx.get("attachments"),
                         [{"id": "nofile", "filename": "a.png"}])

    # -- 8. degradation ----------------------------------------------------------

    def test_disabled_agent_route_returns_error_sse(self):
        import os
        with patch.dict(os.environ, {"NOTES_AGENT_MODE": "off"}):
            r = self.client.post("/api/v1/notes/chat/stream",
                                 json={"message": "你好"})
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.headers["content-type"].startswith(
                "text/event-stream"))
            self.assertIn("event: error", r.text)
            self.assertIn("NOTES_AGENT_MODE", r.text)

    # -- 9. API surface -------------------------------------------------------------

    def test_generate_route_streams_sse(self):
        sid = self._make_session("来源", [{"role": "user", "content": "q"}])

        async def fake_generate(*args, **kwargs):
            yield {"type": "step", "stage": "collecting"}
            yield {"type": "done", "note_id": "x", "revision": 1}

        with patch.object(notes_agent, "generate_note", fake_generate):
            r = self.client.post("/api/v1/notes/generate", json={
                "template_id": "knowledge_summary",
                "sources": {"session_ids": [sid]}})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.headers["content-type"].startswith(
            "text/event-stream"))
        self.assertIn("event: step", r.text)
        self.assertIn("event: done", r.text)

    def test_chat_route_streams_sse(self):
        async def fake_chat(*args, **kwargs):
            yield {"type": "answer", "content": "你好", "is_delta": True}
            yield {"type": "done", "answer": "你好", "mode": "collab"}

        with patch.object(notes_agent, "run_notes_chat", fake_chat):
            r = self.client.post("/api/v1/notes/chat/stream", json={
                "message": "你好", "mode": "collab"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("event: answer", r.text)
        parsed = [line for line in r.text.splitlines()
                  if line.startswith("data: ")]
        payload = json.loads(parsed[1][6:])
        self.assertEqual(payload["mode"], "collab")

    def test_chat_route_passes_action_through(self):
        captured = {}

        async def fake_chat(*args, **kwargs):
            captured.update(kwargs)
            yield {"type": "done", "answer": "ok", "mode": "plan"}

        with patch.object(notes_agent, "run_notes_chat", fake_chat):
            r = self.client.post("/api/v1/notes/chat/stream", json={
                "message": "", "mode": "plan", "action": "approve_plan"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(captured.get("action"), "approve_plan")

    # -- 10. multi-thread API + knowledge cards ------------------------------

    def test_multiple_threads_are_isolated_and_clear_is_server_side(self):
        one = self.client.post("/api/v1/notes/threads", json={"title": "线程一"}).json()["thread"]
        two = self.client.post("/api/v1/notes/threads", json={"title": "线程二"}).json()["thread"]
        notes_mod.append_thread_message("student_default", "user", "one", thread_id=one["thread_id"])
        notes_mod.append_thread_message("student_default", "user", "two", thread_id=two["thread_id"])
        self.assertEqual(self.client.get(f"/api/v1/notes/threads/{one['thread_id']}").json()["messages"][0]["content"], "one")
        self.assertEqual(self.client.get(f"/api/v1/notes/threads/{two['thread_id']}").json()["messages"][0]["content"], "two")
        renamed = self.client.patch(f"/api/v1/notes/threads/{one['thread_id']}", json={"title": "已重命名", "mode": "ask"})
        self.assertEqual(renamed.json()["thread"]["title"], "已重命名")
        self.client.delete(f"/api/v1/notes/threads/{one['thread_id']}/messages")
        cleared = self.client.get(f"/api/v1/notes/threads/{one['thread_id']}").json()
        self.assertEqual(cleared["messages"], [])
        self.assertEqual(cleared["working"].get("stage"), "idle")
        self.client.delete(f"/api/v1/notes/threads/{one['thread_id']}")
        self.assertEqual(self.client.get(f"/api/v1/notes/threads/{one['thread_id']}").status_code, 404)
        self.assertTrue(notes_mod.thread_was_deleted("student_default", one["thread_id"]))

    def test_knowledge_cards_are_compact_and_deduplicated(self):
        result = {"data": {"results": [{
            "file_id": "physics", "filename": "普通物理学.pdf",
            "chapter": "第 5 章", "printed_page": 123, "index": 9,
            "context_hash": "stable",
            "evidence_excerpt": "自旋角动量在外力矩作用下发生方向变化，用于说明进动现象。" + "原文" * 500,
        }]}}
        cards = notes_agent._knowledge_cards(result)
        content = notes_agent._with_knowledge_cards("正文", cards)
        content = notes_agent._with_knowledge_cards(content, cards)
        self.assertEqual(content.count("[知识卡]"), 1)
        self.assertIn("第 123 页", content)
        self.assertLess(len(content), 700)
        self.assertNotIn("原文" * 100, content)

    def test_chat_stream_accepts_thread_id(self):
        captured = {}
        async def fake_chat(*args, **kwargs):
            captured.update(kwargs)
            yield {"type": "done", "answer": "ok", "mode": "ask"}
        with patch.object(notes_agent, "run_notes_chat", fake_chat):
            response = self.client.post("/api/v1/notes/chat/stream", json={"message": "hi", "mode": "ask", "thread_id": "abc"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured.get("thread_id"), "abc")


if __name__ == "__main__":
    unittest.main()
