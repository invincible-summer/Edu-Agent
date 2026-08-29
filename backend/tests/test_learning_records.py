"""学习账本（L1 档案层）回归：record_id 唯一性 + 知识点概念名解析。

历史缺陷：record_id 直接沿用题目 id，而题目 id 是套内序号（聊天出题每套
从 1 重编号、CAT 每题固定 "1"），且去重只认 (record_id, session_id)：
- 跨会话同序号各自追加 → 同一 record_id 多条，前端 React duplicate key；
- CAT 同会话第二题被去重吞掉不落行，record_verdict 匹配不到只能走 uuid
  兜底，产生 type=short_answer、无 bloom_level 的退化记录。

这些测试 pin 修复后的行为：幂等重放保留、任何 id 碰撞换唯一新 id、存量
重复在读取与下次写入时被治愈、/student/learning-records 把图谱节点 id
解析为人读概念名（fail-open）。No LLM, no network.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from tests.storage_sandbox import StorageSandboxTestCase  # noqa: E402
from app.core import learning_records as lr  # noqa: E402


class TestRecordIdUniqueness(StorageSandboxTestCase):

    SID = "sandbox_lr_student"

    def test_in_set_ids_unique_across_sessions(self):
        """两套题各含 id="1"：两条记录、record_id 互不相同且非空。"""
        lr.record_question(self.SID, "chat_a", {"id": "1", "stem": "题干A"})
        lr.record_question(self.SID, "chat_b", {"id": "1", "stem": "题干B"})
        records = lr.list_records(self.SID)
        ids = [r.get("record_id") for r in records]
        self.assertEqual(len(records), 2)
        self.assertEqual(len(set(ids)), 2)
        self.assertTrue(all(ids))

    def test_cat_same_id_new_stem_files_new_record(self):
        """CAT：同 session 两道 id="1" 不同题干 → 各自落行，判分精确写回，
        元数据（type/bloom_level）不退化为兜底 short_answer。"""
        sess = f"assessment:{self.SID}"
        for stem, level in (("第一题", "apply"), ("第二题", "analyze")):
            lr.record_question(self.SID, sess, {
                "id": "1", "stem": stem, "type": "multiple_choice",
                "bloom_level": level, "knowledge_point": "导数"})
        records = lr.list_records(self.SID)
        self.assertEqual(len(records), 2)
        self.assertEqual(len({r["record_id"] for r in records}), 2)

        ok = lr.record_verdict(self.SID, sess, stem="第二题", verdict="correct",
                               student_answer="ans", score=1.0, concept="导数")
        self.assertTrue(ok)
        by_stem = {r["stem"]: r for r in lr.list_records(self.SID)}
        self.assertEqual(by_stem["第二题"]["verdict"], "correct")
        self.assertEqual(by_stem["第二题"]["type"], "multiple_choice")
        self.assertEqual(by_stem["第二题"]["bloom_level"], "analyze")
        self.assertEqual(by_stem["第一题"]["verdict"], "")  # 未误写另一行

    def test_exact_replay_is_idempotent(self):
        """同 session 同 id 同题干重放：复用原记录，不重复落行。"""
        q = {"id": "9", "stem": "同一道题", "knowledge_point": "函数"}
        rid1 = lr.record_question(self.SID, "s1", q)
        rid2 = lr.record_question(self.SID, "s1", q)
        self.assertEqual(rid1, rid2)
        records = lr.list_records(self.SID)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["record_id"], rid1)

    def test_legacy_duplicates_sanitized(self):
        """存量重复 id：list_records 读侧去重；下次写入时持久治愈文件。"""
        lr._save(self.SID, {"records": [
            {"record_id": "1", "session_id": "a", "stem": "旧题一", "created_at": 1},
            {"record_id": "1", "session_id": "b", "stem": "旧题二", "created_at": 2},
            {"record_id": "", "session_id": "c", "stem": "旧题三", "created_at": 3},
        ]})
        seen = [r["record_id"] for r in lr.list_records(self.SID)]
        self.assertEqual(len(seen), 3)
        self.assertEqual(len(set(seen)), 3)   # 内存级：展示侧已唯一
        self.assertTrue(all(seen))

        lr.record_question(self.SID, "s_new", {"id": "1", "stem": "新题"})
        on_disk = [r["record_id"] for r in lr._load(self.SID)["records"]]
        self.assertEqual(len(on_disk), 4)
        self.assertEqual(len(set(on_disk)), 4)  # 写入路径已把文件治愈


def _mock_student_model() -> MagicMock:
    """graph 命中 + memory 命中两个解析源（name 须逐一赋值，绕开
    MagicMock(name=...) 的命名陷阱）。"""
    node = MagicMock()
    node.name = "细胞"
    rec = MagicMock()
    rec.skill_id = "physics.dynamics.newton_second"
    rec.concept = "牛顿第二定律"
    sm = MagicMock()
    sm.graph.nodes = {"custom.tb-tb_137.c.abc123": node}
    sm.memory = {"m1": rec}
    return sm


class TestLearningRecordsEndpoint(StorageSandboxTestCase):
    """/student/learning-records 的 knowledge_point 概念名解析（fail-open）。"""

    def _setup_client(self):
        from fastapi.testclient import TestClient
        from app.main import create_app
        from app.identity import store as id_store
        from app.identity.models import UserProfile
        from app.identity.security import create_token, hash_password
        self.client = TestClient(create_app())
        self.user = id_store.create_user(
            email="lr@example.com", username="",
            password_hash=hash_password("secret123"),
            profile=UserProfile(name="lr"))
        self.headers = {"Authorization": f"Bearer {create_token(self.user.id)}"}
        return self.user.id

    def test_resolves_concept_ids_to_names(self):
        from app.api.v1 import student as student_api
        sid = self._setup_client()
        lr.record_question(sid, "chat_a", {
            "id": "1", "stem": "q1", "knowledge_point": "custom.tb-tb_137.c.abc123"})
        lr.record_question(sid, "chat_b", {
            "id": "1", "stem": "q2", "knowledge_point": "physics.dynamics.newton_second"})
        lr.record_question(sid, "chat_c", {
            "id": "1", "stem": "q3", "knowledge_point": "导数"})
        with patch.object(student_api, "_sm") as mock_sm:
            mock_sm.is_enabled.return_value = True
            mock_sm.get_student_model.return_value = _mock_student_model()
            resp = self.client.get("/api/v1/student/learning-records",
                                   headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "ok")
        by_stem = {i["stem"]: i["knowledge_point"] for i in body["items"]}
        self.assertEqual(by_stem["q1"], "细胞")            # graph 节点命中
        self.assertEqual(by_stem["q2"], "牛顿第二定律")     # memory skill_id 命中
        self.assertEqual(by_stem["q3"], "导数")             # 人读名原样保留
        ids = [i["record_id"] for i in body["items"]]
        self.assertEqual(len(ids), 3)
        self.assertEqual(len(set(ids)), 3)                 # 跨会话 id 唯一

    def test_disabled_student_model_passes_through(self):
        from app.api.v1 import student as student_api
        sid = self._setup_client()
        lr.record_question(sid, "chat_a", {
            "id": "1", "stem": "q1", "knowledge_point": "custom.tb-tb_137.c.abc123"})
        with patch.object(student_api, "_sm") as mock_sm:
            mock_sm.is_enabled.return_value = False
            resp = self.client.get("/api/v1/student/learning-records",
                                   headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ok")
        self.assertEqual(resp.json()["items"][0]["knowledge_point"],
                         "custom.tb-tb_137.c.abc123")


if __name__ == "__main__":
    unittest.main()
