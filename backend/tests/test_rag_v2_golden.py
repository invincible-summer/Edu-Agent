"""Optional real-public-textbook golden. Skips on clean CI without gitignored data."""
from __future__ import annotations
import asyncio
import hashlib
import unittest
from pathlib import Path

from app.core.knowledge_store import KnowledgeStore
from app.core.structured_chunker import chunk_text_v2
from app.tools.knowledge_search import KnowledgeSearchTool

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "chat_history" / "library" / "data" / "public"
LINEAR = DATA / "dad15da7b48b.txt"
PHYSICS = [DATA / "6e0f311d8b9a.txt", DATA / "5cec4f16eb41.txt"]


@unittest.skipUnless(LINEAR.exists() and all(p.exists() for p in PHYSICS),
                     "public textbook golden data not installed")
class TestRealTextbookGolden(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.linear_hash = hashlib.sha256(LINEAR.read_bytes()).hexdigest()
        linear = KnowledgeStore(upload_dir=Path("/tmp/rag_v2_linear"))
        linear.chunks = chunk_text_v2(LINEAR.read_text(encoding="utf-8"), "线性代数", "dad15da7b48b")
        linear.files = [{"id": "dad15da7b48b", "filename": "线性代数",
                         "source_scope": "public", "source_visibility": "public"}]
        cls.linear_tool = KnowledgeSearchTool(linear)
        from app.core.retriever import chunk_text
        legacy = KnowledgeStore(upload_dir=Path("/tmp/rag_legacy_linear"))
        legacy.chunks = chunk_text(LINEAR.read_text(encoding="utf-8"), "线性代数", "dad15da7b48b")
        legacy.files = list(linear.files)
        cls.legacy_linear_tool = KnowledgeSearchTool(legacy)
        physics = KnowledgeStore(upload_dir=Path("/tmp/rag_v2_physics"))
        names = ["大学物理·电磁光学量子", "大学物理·力学热学"]
        for path, name in zip(PHYSICS, names):
            fid = path.stem
            physics.chunks.extend(chunk_text_v2(path.read_text(encoding="utf-8"), name, fid))
            physics.files.append({"id": fid, "filename": name,
                                  "source_scope": "public", "source_visibility": "public"})
        cls.physics_tool = KnowledgeSearchTool(physics)

    def test_linear_body_and_rejection(self):
        space = asyncio.run(self.linear_tool.run(query="线性空间与线性变换", top_k=4))
        self.assertEqual(space.status, "success")
        self.assertGreaterEqual(space.data["results"][0]["page"], 153)
        positive = asyncio.run(self.linear_tool.run(query="正定矩阵的判定条件", top_k=4))
        self.assertEqual(positive.status, "success")
        self.assertIn(positive.data["results"][0]["page"], {143, 144, 145})
        author = asyncio.run(self.linear_tool.run(query="这本教材的作者是谁", top_k=4))
        self.assertEqual(author.status, "success")
        self.assertTrue(any(set(row.get("noise_flags") or []) & {"metadata", "copyright", "preface"}
                            for row in author.data["results"]))
        unrelated = asyncio.run(self.linear_tool.run(query="量子色动力学胶子禁闭", top_k=4))
        self.assertTrue(unrelated.is_error)
        self.assertTrue(unrelated.data.get("no_hit"))
        self.assertEqual(hashlib.sha256(LINEAR.read_bytes()).hexdigest(), self.linear_hash)

    def test_v2_precision_improves_without_recall_loss(self):
        from unittest.mock import patch
        from app.core.config import settings
        relevant = ["线性空间与线性变换", "正定矩阵的判定条件",
                    "特征值与特征向量", "矩阵的秩", "克莱默法则"]
        legacy_hits = []
        v2_hits = []
        for query in relevant:
            with patch.object(settings, "rag_evidence_gate", "off"):
                legacy_hits.append(asyncio.run(
                    self.legacy_linear_tool.run(query=query, top_k=4)))
            with patch.object(settings, "rag_evidence_gate", "on"):
                v2_hits.append(asyncio.run(self.linear_tool.run(query=query, top_k=4)))
        self.assertGreaterEqual(sum(not r.is_error for r in v2_hits),
                                sum(not r.is_error for r in legacy_hits))
        with patch.object(settings, "rag_evidence_gate", "off"):
            legacy_space = asyncio.run(self.legacy_linear_tool.run(
                query="线性空间与线性变换", top_k=4))
            legacy_qcd = asyncio.run(self.legacy_linear_tool.run(
                query="量子色动力学胶子禁闭", top_k=4))
        with patch.object(settings, "rag_evidence_gate", "on"):
            v2_space = asyncio.run(self.linear_tool.run(
                query="线性空间与线性变换", top_k=4))
            v2_qcd = asyncio.run(self.linear_tool.run(
                query="量子色动力学胶子禁闭", top_k=4))
        self.assertLess(legacy_space.data["results"][0]["page"], 153)
        self.assertGreaterEqual(v2_space.data["results"][0]["page"], 153)
        self.assertFalse(legacy_qcd.is_error)
        self.assertTrue(v2_qcd.is_error)

    def test_quality_thresholds_on_linear_algebra_suite(self):
        relevant = [
            "矩阵乘法", "矩阵的初等变换", "逆矩阵的判定", "线性方程组的解",
            "行列式按行展开", "克莱默法则", "向量组的线性相关性", "矩阵的秩",
            "齐次线性方程组基础解系", "特征值与特征向量", "相似对角化",
            "实对称矩阵正交对角化", "二次型的标准形", "正定矩阵的判定条件",
            "线性空间与子空间", "线性空间的基维数坐标", "基变换与坐标变换",
            "线性变换的矩阵表示", "线性变换的核与像", "向量空间的维数",
        ]
        unrelated = [
            "量子色动力学胶子禁闭", "蛋白质折叠的分子伴侣", "光合作用暗反应卡尔文循环",
            "唐诗格律平仄", "罗马帝国晚期税制", "TCP拥塞控制算法", "Java垃圾回收器",
            "卷积神经网络反向传播", "数据库两阶段提交", "火山喷发岩浆黏度",
            "法语虚拟式语法", "莎士比亚十四行诗", "明朝海禁政策", "有机化学傅克反应",
            "细胞有丝分裂纺锤体", "足球越位规则", "货币政策量化宽松",
            "黑洞霍金辐射", "区块链权益证明", "操作系统虚拟内存缺页中断",
        ]
        hits = [asyncio.run(self.linear_tool.run(query=q, top_k=4)) for q in relevant]
        misses = [asyncio.run(self.linear_tool.run(query=q, top_k=4)) for q in unrelated]
        recall = sum(not r.is_error for r in hits) / len(hits)
        clean_top1 = sum(not r.is_error and not (set(r.data["results"][0].get("noise_flags") or [])
                         & {"toc", "copyright", "preface", "header_footer"}) for r in hits) / len(hits)
        rejection = sum(r.is_error for r in misses) / len(misses)
        per_query_duplicate_rates = []
        for result in hits:
            if result.is_error:
                continue
            locations = [(row.get("file_id"), row.get("page"))
                         for row in result.data["results"]]
            per_query_duplicate_rates.append(
                1 - len(set(locations)) / max(1, len(locations)))
        duplicate_rate = max(per_query_duplicate_rates, default=0.0)
        self.assertGreaterEqual(recall, 0.95)
        self.assertGreaterEqual(clean_top1, 0.95)
        self.assertGreaterEqual(rejection, 0.95)
        self.assertLessEqual(duplicate_rate, 0.10)

    def test_physics_cross_volume(self):
        cases = [
            ("刚体转动惯量和平行轴定理", "5cec4f16eb41"),
            ("麦克斯韦方程组的积分形式", "6e0f311d8b9a"),
            ("夫琅禾费单缝衍射强度分布", "6e0f311d8b9a"),
        ]
        for query, expected in cases:
            result = asyncio.run(self.physics_tool.run(query=query, top_k=4))
            self.assertEqual(result.status, "success", query)
            self.assertEqual(result.data["results"][0]["file_id"], expected, query)
            locations = [(x["file_id"], x.get("page")) for x in result.data["results"]]
            self.assertEqual(len(locations), len(set(locations)), query)


if __name__ == "__main__": unittest.main()
