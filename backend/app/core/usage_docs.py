"""Usage docs: the admin-editable, all-user-readable /docs page content.

One global markdown document, stored at chat_history/settings/usage_docs.json
(alongside the OCR runtime policy — the established admin-settings root, no
per-owner attribution so the orphan scanner never touches it). Storage
contract mirrors ocr_policy: defensive read (missing/corrupt -> bootstrap
default), file_lock + atomic write. The document is version content, not user
runtime data, so it is safe to rewrite wholesale on save.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .atomic import atomic_write_text, file_lock

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DOCS_FILE = _PROJECT_ROOT / "chat_history" / "settings" / "usage_docs.json"

# size cap: a usage doc well beyond this is almost certainly a paste error
_MAX_MARKDOWN_CHARS = 200_000

_DEFAULT_MARKDOWN = """# 使用文档

欢迎来到 Next Tutor Agent —— 一套**教材驱动的 AI 一对一辅导系统**。它不只是聊天机器人：每一轮对话背后都有教学策略、掌握度追踪与教材依据。系统由 M0–M10 十层智能模块协同编排，记住你学过什么，并知道下一步该怎么教。

> 阅读建议：先看「快速上手」开始第一课，再按需查阅「功能导览」与「技术架构速览」。

## 快速上手

1. **注册登录**：注册即得专属学习空间，所有数据按账号完全隔离；
2. **准备教材**：在「资源」中使用公共教材，或上传你自己的教材 / 讲义 / 试卷（自动解析入库）；
3. **开始提问**：在「对话工作台」直接提问，回答基于教材检索生成、附带概念出处；
4. **追踪进步**：打开「学习总览」查看掌握度变化，让系统自动安排复习与测评。

## 功能导览

### 对话工作台（M1 · 任务智能）

与学习智能体多轮对话：讲解、追问、答疑、布置练习。

- **苏格拉底式讲解**：循循善诱，引导你自己想明白，而不是直接给出答案；
- 回答基于 RAG 检索增强生成：先从你选用的教材中检索相关片段，再组织作答，概念出处可溯源；
- 每轮对话经过「理解 → 规划 → 工具执行 → 状态更新」的任务流水线，并沉淀为跨轮教学记忆。

### 教材与资源（RAG）

「资源」页管理教材与学习文件。

- **公共教材**由管理员维护、全员可读；**私有上传**仅自己可见；
- 上传后自动解析、分块并向量化入库，作为对话、出题与生成笔记的知识来源；
- 每个学习区可关联多本教材，对话时按需自动检索。

### 知识图谱（M5 · 知识智能）

以图谱形式浏览教材中的概念及其关联，点击概念可发起针对性提问。图谱在教材解析时自动构建，是「学到哪了、还差什么」的地图。

### 测评中心（M4 · 测评智能）

真实检验「学会了没有」。

- **约束出题**：题目严格约束在你选定的教材与知识点范围内，不出超纲题；
- **三级评分**：作答按完全正确 / 部分正确 / 错误分级评定，精细回写掌握度；
- **CAT 自适应测试**：根据作答实时调整下一题难度，用更少的题精确定位真实水平；
- 测评结果回写掌握度模型，弱项自动进入后续学习安排。

### 笔记仓库（MN）

边学边记，把知识沉淀成你自己的资料库。

- **双链笔记**：用 `[[笔记链接]]` 互相关联，未解析链接一键创建新笔记；
- **AI 生成**：从辅导对话、教材或错题本一键生成知识点总结、错题修正、学习温故等笔记；
- **SM-2 温故**：笔记可开启间隔复习，到期自动进入复习安排；
- **关系图**：以力导向图总览全部笔记及其与对话、教材的关联；
- 删除的笔记先进入回收站，可从「归档中心」恢复。

### 学习总览与我的画像（M2 · 学生模型）

「学习总览」汇总掌握度、学习节奏与近期任务；「我的画像」展示系统对你的理解。

- **BKT 掌握度追踪**：按贝叶斯知识追踪模型，从你的作答序列持续估计每个概念的掌握概率；
- 概念掌握状态与学段、学习风格画像随学习持续更新，画像内容对你透明可查。

### 学习编排（M9 · 编排智能）

从学期目标到今日任务的自动编排：设定一个或多个目标后，系统分解为周任务 → 今日任务，并结合 SM-2 间隔重复安排到期复习，对抗遗忘。

### 记忆（M6 · 记忆智能）

系统维护**有界画像**与策略聚合记录：哪些讲法对你有效、哪种节奏更适合你——越用越懂你。

### 洞察（M7 · 评估改进）

错题记录与教学自诊断：系统复盘教学效果，让学习智能体越教越好；你可以在这里回顾错题与改进建议。

### 归档中心

删除的内容（如笔记）先进回收站，可随时恢复，避免误删损失。

### 管理端（M0 · 仅管理员）

公共教材与版本管理、账号管理、孤儿数据清理；本文档也由管理员在本页直接编辑。

## 技术架构速览

| 模块 | 名称 | 职责 |
| --- | --- | --- |
| M0 | 身份基础设施 | 用户是谁、数据属于谁、如何安全访问 |
| M1 | 任务智能 | 理解 → 规划 → 工具执行 → 状态更新 |
| M2 | 学生模型 | 学习画像 + BKT 掌握度 + 概念状态 |
| M3 | 教学引擎 | 六模式状态机 + 跨轮教学记忆 |
| M4 | 测评智能 | 三级评分 + 约束出题 + CAT 自适应测试 |
| M5 | 知识智能 | 教材知识图谱 + 概念检索 |
| M6 | 记忆智能 | 有界画像 + 策略聚合，越用越懂你 |
| M7 | 评估改进 | 教学自诊断，让学习智能体越教越好 |
| M8 | 交互体验 | 表达方式适配每个学生的偏好 |
| M9 | 学习编排 | 多目标 → 周任务 → 今日任务 |
| M10 | 能力运行时 | 技能调用契约与学习证据门 |

## 学习建议

- **让系统知道你在用哪本教材**：关联教材后，讲解、出题与测评都会以它为依据；
- **答错不要跳过**：错题会进入错题本与掌握度模型，是后续编排的输入；
- **重要内容沉淀为笔记**：对话会过去，笔记与双链留下来；
- **跟着今日任务走**：编排已综合考虑你的目标与遗忘曲线，比临时突击有效。

## 常见问题

- **回答有依据吗？** 有。回答基于所选教材的 RAG 检索结果，概念出处可溯源；
- **我上传的教材别人能看到吗？** 不能。私有教材与文件仅自己可见；公共教材由管理员维护；
- **忘记复习怎么办？** 学习编排会把到期复习自动排进任务，学习总览也会提醒；
- **误删的内容能找回吗？** 能。删除先进入回收站，可在「归档中心」恢复。

> 本文档由管理员维护：管理员登录后可在本页直接编辑（支持 Markdown）。
"""


def _bootstrap() -> dict[str, Any]:
    return {"markdown": _DEFAULT_MARKDOWN, "updated_at": 0.0, "updated_by": ""}


def read_docs() -> dict[str, Any]:
    """Read the usage doc; missing/corrupt file -> bootstrap default.

    Never raises (the page must render for everyone even with a bad file).
    """
    try:
        data = json.loads(_DOCS_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return _bootstrap()
        md = str(data.get("markdown") or "")
        return {
            "markdown": md if md else _bootstrap()["markdown"],
            "updated_at": float(data.get("updated_at") or 0.0),
            "updated_by": str(data.get("updated_by") or ""),
        }
    except Exception:
        return _bootstrap()


def write_docs(markdown: str, *, updated_by: str = "") -> dict[str, Any]:
    """Persist a new doc version (atomic + lock). Returns the stored payload.

    Raises ValueError when the markdown exceeds the size cap; other failures
    raise OSError so the API can surface a 500 rather than silently dropping
    an admin edit.
    """
    md = str(markdown or "")
    if len(md) > _MAX_MARKDOWN_CHARS:
        raise ValueError("document too large")
    payload = {"markdown": md, "updated_at": time.time(),
               "updated_by": str(updated_by or "")}
    _DOCS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(_DOCS_FILE):
        atomic_write_text(_DOCS_FILE, json.dumps(payload, ensure_ascii=False))
    return payload
