"""弱模型伪工具标签护栏（2026-08-15「导数」对话回归，turn 6/8）。

部分模型不发起 function-calling，而是在正文里"叙述"工具调用——输出
``<knowledge_search>检索关键词：导数</knowledge_search>`` 这样的假标签，
学生看到的是标签文本而不是检索结果。本模块在流式输出时做缓冲检测：

- 标签一旦开始形成（含半截前缀 ``<knowled…``）就停止对外转发该段文本；
- 命中后由调用方（chat_agent / executor 的 ReAct 环路）执行**真实**的
  knowledge_search，把结果注入消息并继续环路，让模型基于真结果续写；
- 标签前的正文（"我先检索一下…"）照常流出，作为该步可见前导。

纯文本状态机，无 LLM 依赖；每步 LLM 调用新建一个实例。
"""
from __future__ import annotations

import re

_TAG_OPEN = "<knowledge_search"
_MAX_TAG_RAW = 2000  # 标签原文累计上限（防异常超长输出吃内存）
_QUERY_LINE_RE = re.compile(r"(?:检索关键词|关键词|查询|query)\s*[:：]\s*([^\n<]{2,120})")


class PseudoToolGuard:
    """单次 LLM 流的伪 ``<knowledge_search>`` 标签检测器。"""

    def __init__(self, tag: str = _TAG_OPEN) -> None:
        self._tag = tag.lower()
        self._pending = ""   # 尾部尚未判定的文本（可能是半截标签前缀）
        self._tag_raw = ""   # 标签出现后累计的原文（用于提取检索词）
        self._emitted = ""   # 已判定安全、允许转发给前端的全部文本
        self._detected = False

    @property
    def detected(self) -> bool:
        return self._detected

    @property
    def emitted(self) -> str:
        """到目前为止已放行的文本（命中时即标签前导正文）。"""
        return self._emitted

    def feed(self, delta: str) -> str:
        """喂入一个 answer delta；返回本次可安全转发的前端文本。"""
        if self._detected:
            if len(self._tag_raw) < _MAX_TAG_RAW:
                self._tag_raw += delta
            return ""
        buf = self._pending + delta
        idx = buf.lower().find(self._tag)
        if idx >= 0:
            self._detected = True
            self._tag_raw = buf[idx:idx + _MAX_TAG_RAW]
            out = buf[:idx]
            self._pending = ""
            self._emitted += out
            return out
        held = self._held_prefix_len(buf)
        if held:
            out, self._pending = buf[:len(buf) - held], buf[len(buf) - held:]
        else:
            out, self._pending = buf, ""
        self._emitted += out
        return out

    def flush(self) -> str:
        """流结束：冲掉未成形的半截前缀缓冲（之后不可能再成为标签）。"""
        if self._detected:
            self._pending = ""
            return ""
        out, self._pending = self._pending, ""
        self._emitted += out
        return out

    def extract_query(self, fallback: str) -> str:
        """从标签原文提取检索词；无显式关键词时回退 fallback（用户消息）。"""
        m = _QUERY_LINE_RE.search(self._tag_raw)
        if m and m.group(1).strip():
            return m.group(1).strip()
        text = re.sub(r"<[^>]*>", "", self._tag_raw).strip()
        if 2 <= len(text) <= 120 and not text.startswith("检索"):
            return text
        return (fallback or "").strip()[:120]

    def _held_prefix_len(self, buf: str) -> int:
        """尾部是否存在标签的半截前缀（如 ``<knowled``），返回持有长度。"""
        lower = buf.lower()
        window = min(len(buf), len(self._tag))
        for i in range(max(0, len(buf) - window), len(buf)):
            if buf[i] == "<" and self._tag.startswith(lower[i:]):
                return len(buf) - i
        return 0
