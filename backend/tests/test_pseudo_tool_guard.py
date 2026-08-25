"""伪工具标签护栏（pseudo_tool_guard）单元契约。

弱模型把工具调用"叙述"成正文里的假 `<knowledge_search>` 标签时：
标签形成即停止转发、前导正文照常流出、可提取检索词。
"""
from __future__ import annotations

import unittest

from app.agents.pseudo_tool_guard import PseudoToolGuard


def feed_all(guard: PseudoToolGuard, text: str) -> str:
    out = []
    for i in range(len(text)):
        out.append(guard.feed(text[i]))
    return "".join(out)


class TestPseudoToolGuard(unittest.TestCase):
    def test_plain_text_passes_through(self):
        g = PseudoToolGuard()
        self.assertEqual(feed_all(g, "导数是瞬时变化率。"), "导数是瞬时变化率。")
        self.assertFalse(g.detected)
        self.assertEqual(g.flush(), "")

    def test_tag_detected_and_stripped_from_stream(self):
        g = PseudoToolGuard()
        visible = feed_all(
            g, "我先检索一下教材。\n<knowledge_search>\n  检索关键词：导数 定义\n</knowledge_search>")
        self.assertTrue(g.detected)
        self.assertEqual(visible, "我先检索一下教材。\n")
        # 命中后再喂入的文本一律不再转发
        self.assertEqual(g.feed("后续内容"), "")
        self.assertEqual(g.flush(), "")

    def test_partial_prefix_held_then_released(self):
        g = PseudoToolGuard()
        # 半截标签前缀 "<knowled" 持有不转发，之前的正文照常放行
        self.assertEqual(feed_all(g, "正文 <knowled"), "正文 ")
        self.assertFalse(g.detected)
        # 后续字符 "<knowledg！" 无法成为标签前缀，持有段原样释放
        out = g.feed("g！")
        self.assertEqual(out, "<knowledg！")
        self.assertFalse(g.detected)
        self.assertEqual(g.flush(), "")

    def test_extract_query_from_tag_content(self):
        g = PseudoToolGuard()
        feed_all(g, "<knowledge_search>\n  检索关键词：导数 定义\n</knowledge_search>")
        self.assertEqual(g.extract_query("用户的问题"), "导数 定义")

    def test_extract_query_fallback_to_user_message(self):
        g = PseudoToolGuard()
        feed_all(g, "<knowledge_search>随便写的说明文字很长很长超过一百二十个字符" + "x" * 200)
        self.assertEqual(g.extract_query("导数高中要学点什么"), "导数高中要学点什么")

    def test_unicode_angle_brackets_not_triggered(self):
        g = PseudoToolGuard()
        visible = feed_all(g, "全角标签＜knowledge_search＞不是伪标签")
        self.assertFalse(g.detected)
        self.assertEqual(visible, "全角标签＜knowledge_search＞不是伪标签")


if __name__ == "__main__":
    unittest.main()
