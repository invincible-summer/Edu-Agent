"""Deterministic structure-aware chunking for persisted material RAG.

The V2 chunker never calls an LLM. It keeps physical page boundaries, marks
rather than deletes front-matter/noise, retains normalized and raw source
coordinates, and emits structural parent/previous/next links.
"""
from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections import Counter
from typing import Any

from .retriever import Chunk, tokenize

CHUNK_SCHEMA_VERSION = "structured-v2.1"
TARGET_TOKEN_MIN = 220
TARGET_TOKEN_MAX = 480
TARGET_TOKEN_COUNT = 360
SOFT_TOKEN_LIMIT = 520
HARD_TOKEN_LIMIT = 650

_HEADING_RE = re.compile(
    r"^(?:第\s*[0-9０-９一二三四五六七八九十百零〇两]+\s*(?:章|单元)|"
    r"第\s*[0-9０-９一二三四五六七八九十百零〇两]+\s*(?:节|课|讲|篇)|"
    r"[0-9０-９]+(?:\.[0-9０-９]+){0,3}\s+|"
    r"chapter\s+[0-9]+|"
    r"[一二三四五六七八九十]+、)\s*\S+",
    re.I,
)
_TOC_RE = re.compile(r"(?:目录|contents|table\s+of\s+contents|索引|目次)", re.I)
_COPYRIGHT_RE = re.compile(r"(?:版权|版权所有|著作权|isbn|cip|中国版本图书馆|定价|出版发行|法律声明)", re.I)
_PREFACE_RE = re.compile(r"^(?:前\s*言|序\s*言|内容提要|编者的话|preface)", re.I)
_PAGE_RE = re.compile(r"^(?:[-—_\s]*\d{1,4}[-—_\s]*|第\s*\d+\s*页)$")
_FORMULA_RE = re.compile(r"(?:[=≤≥≈∑∫√∞→←↔]|\\frac|[a-zA-Z]\s*\^\s*\d)")
# 结构化标记（OCR prompt v2 / 原生收割产生）：印刷页码 / 图 / 表。
_PRINTED_PAGE_RE = re.compile(r"^\s*[\[［【]\s*页码\s*[=＝:：]?\s*([0-9]{1,4})\s*[\]］】]\s*$")
# 去锚点版：OCR/收割产物并不保证标记独占行——实测视觉模型会把 [页码=N] 放在
# 该页最后一行行尾（甚至正文句中）。剥离标记子串本身，行内其余文字保留。
_PRINTED_PAGE_INLINE_RE = re.compile(
    r"\s*[\[［【]\s*页码\s*[=＝:：]?\s*([0-9]{1,4})\s*[\]］】]")
_FIGURE_MARK_RE = re.compile(r"^\s*[\[［【]\s*图")
_TABLE_MARK_RE = re.compile(r"^\s*[\[［【]\s*表")
# figure/table 标记块的"从属行"：图述/图注/题目转录前缀、表格行（|/｜ 分隔）。
# 注意不含裸"图"——"图像/图中…"等正文行不能被并入标记块。
_SPECIAL_CONT_RE = re.compile(r"^\s*(?:图述|图注|题目转录)")
_PROTECTED_BLOCKS = {"figure", "formula", "table", "definition", "theorem",
                     "example", "exercise", "solution"}
_TOKEN_PIECE_RE = re.compile(
    r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]|"
    r"[A-Za-z]+(?:'[A-Za-z]+)?|\d+(?:\.\d+)?|[^\s]"
)


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKC", s).replace("\u00a0", " ").strip()


def _normalize_with_raw_map(text: str) -> tuple[str, list[int]]:
    """Return NFKC text and a best-effort map from normalized chars to raw offsets."""
    normalized: list[str] = []
    raw_offsets: list[int] = []
    for raw_idx, char in enumerate(text):
        piece = unicodedata.normalize("NFKC", char).replace("\u00a0", " ")
        normalized.extend(piece)
        raw_offsets.extend([raw_idx] * len(piece))
    return "".join(normalized), raw_offsets


def estimate_model_tokens(text: str) -> int:
    """Deterministic conservative token estimate for CJK/Latin/math text."""
    total = 0
    for piece in _TOKEN_PIECE_RE.findall(text or ""):
        if re.fullmatch(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", piece):
            total += 1
        elif piece[0].isalpha():
            total += max(1, math.ceil(len(piece) / 4))
        elif piece[0].isdigit():
            total += max(1, math.ceil(len(piece) / 3))
        else:
            total += 1
    return total


def _block_type(text: str, heading: bool = False) -> str:
    if heading:
        return "heading"
    clean = text.lstrip()
    if _FIGURE_MARK_RE.match(clean):
        return "figure"
    if _TABLE_MARK_RE.match(clean):
        return "table"
    if _COPYRIGHT_RE.search(clean):
        return "metadata"
    if re.match(r"(?:本章小结|小结|总结|summary)", clean, re.I):
        return "summary"
    if re.match(r"(?:证明|解(?:答|析)?[：:]?|solution|proof)\b", clean, re.I):
        return "solution"
    if re.match(r"(?:定义|definition)\s*\d*", clean, re.I):
        return "definition"
    if re.match(r"(?:定理|引理|推论|性质|公理|theorem|lemma|corollary)", clean, re.I):
        return "theorem"
    if re.match(r"(?:习题|练习|exercise)", clean, re.I):
        return "exercise"
    if re.match(r"(?:例\s*[题]?|example)", clean, re.I):
        return "example"
    if _FORMULA_RE.search(text) and len(text) < 500:
        return "formula"
    if "|" in text or "\t" in text:
        return "table"
    return "paragraph"


def _noise_flags(text: str, *, repeated: bool = False) -> list[str]:
    flags: list[str] = []
    compact = re.sub(r"\s+", "", text)
    if _TOC_RE.search(text) or (re.search(r"\.{2,}|…{2,}", text) and re.search(r"\d{1,4}$", text)):
        flags.append("toc")
    if _COPYRIGHT_RE.search(text):
        flags.append("copyright")
    if _PREFACE_RE.search(text.strip()):
        flags.append("preface")
    if _PAGE_RE.match(text):
        flags.append("page_number")
    if repeated:
        flags.append("header_footer")
    if len(compact) >= 8 and len(set(compact)) <= 3:
        flags.append("ocr_garble")
    if re.search(r"(.)\1{8,}", compact):
        flags.append("ocr_garble")
    return list(dict.fromkeys(flags))


def _is_heading(line: str) -> bool:
    line = line.strip()
    if not line or len(line) > 120:
        return False
    return bool(_HEADING_RE.match(line)) or (
        len(line) <= 55 and not re.search(r"[。！？；.!?]$", line)
        and (line.startswith(("第", "附录", "绪论", "概述", "摘要")) or line.isupper())
    )


def _heading_level(title: str) -> int:
    clean = _norm(title)
    if re.match(r"^(?:第\s*\S+\s*(?:章|单元)|chapter\s+\d+)", clean, re.I):
        return 1
    if re.match(r"^第\s*\S+\s*(?:节|课|讲|篇)", clean):
        return 2
    numeric = re.match(r"^([0-9]+(?:\.[0-9]+){0,3})\s+", clean)
    if numeric:
        return min(3, numeric.group(1).count(".") + 1)
    if re.match(r"^[一二三四五六七八九十]+、", clean):
        return 2
    return 3


def _sentence_units(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？；.!?])\s*|\n+", text)
    return [p.strip() for p in parts if p.strip()]


def _prefix_for_budget(text: str, budget: int) -> int:
    low, high = 1, len(text)
    while low < high:
        mid = (low + high + 1) // 2
        if estimate_model_tokens(text[:mid]) <= budget:
            low = mid
        else:
            high = mid - 1
    cut = max(1, low)
    floor = max(1, int(cut * 0.65))
    boundaries = [m.end() for m in re.finditer(r"[\s，,；;。.!?！？）)】\]]", text[floor:cut])]
    if boundaries:
        cut = floor + boundaries[-1]
    return max(1, cut)


def _hard_split(text: str) -> list[str]:
    out: list[str] = []
    rest = text.strip()
    while rest and estimate_model_tokens(rest) > HARD_TOKEN_LIMIT:
        cut = _prefix_for_budget(rest, HARD_TOKEN_LIMIT)
        out.append(rest[:cut].strip())
        rest = rest[cut:].lstrip()
    if rest:
        out.append(rest)
    return [piece for piece in out if piece]


def _split_piece(text: str, block_type: str) -> list[str]:
    text = _norm(text)
    token_count = estimate_model_tokens(text)
    if not text:
        return []
    if token_count <= SOFT_TOKEN_LIMIT:
        return [text]
    if block_type in _PROTECTED_BLOCKS and token_count <= HARD_TOKEN_LIMIT:
        return [text]

    units: list[str] = []
    for unit in _sentence_units(text) or [text]:
        units.extend(_hard_split(unit))
    out: list[str] = []
    out_tokens: list[int] = []
    current = ""
    current_tokens = 0
    for unit in units:
        unit_tokens = estimate_model_tokens(unit)
        candidate_tokens = current_tokens + unit_tokens
        if (current and candidate_tokens > TARGET_TOKEN_COUNT
                and current_tokens >= TARGET_TOKEN_MIN):
            out.append(current)
            out_tokens.append(current_tokens)
            current, current_tokens = unit, unit_tokens
        elif candidate_tokens <= HARD_TOKEN_LIMIT:
            current = f"{current}\n{unit}".strip() if current else unit
            current_tokens = candidate_tokens
        else:
            if current:
                out.append(current)
                out_tokens.append(current_tokens)
            split_units = _hard_split(unit)
            for completed in split_units[:-1]:
                out.append(completed)
                out_tokens.append(estimate_model_tokens(completed))
            current = split_units[-1]
            current_tokens = estimate_model_tokens(current)
    if current:
        out.append(current)
        out_tokens.append(current_tokens)
    if len(out) >= 2 and out_tokens[-1] < TARGET_TOKEN_MIN:
        candidate_tokens = out_tokens[-2] + out_tokens[-1]
        if candidate_tokens <= SOFT_TOKEN_LIMIT:
            out[-2:] = [f"{out[-2]}\n{out[-1]}"]
            out_tokens[-2:] = [candidate_tokens]
    final: list[str] = []
    for piece in out:
        final.extend(_hard_split(piece))
    return final


def _raw_offsets(normalized_start: int, normalized_end: int,
                 raw_map: list[int], raw_length: int) -> tuple[int, int]:
    if not raw_map:
        return 0, 0
    start_idx = min(max(0, normalized_start), len(raw_map) - 1)
    end_idx = min(max(start_idx, normalized_end - 1), len(raw_map) - 1)
    return raw_map[start_idx], min(raw_length, raw_map[end_idx] + 1)


def chunk_text_v2(text: str, source: str, file_id: str = "") -> list[Chunk]:
    """Create deterministic V2 chunks, never crossing a physical page."""
    if not text or not text.strip():
        return []
    pages = text.split("\f")
    multi = len(pages) > 1
    edge_lines: list[str] = []
    for page in pages:
        lines = [_norm(x) for x in page.splitlines() if _norm(x)]
        edge_lines.extend(lines[:1] + lines[-1:])
    repeated = {line for line, count in Counter(edge_lines).items() if line and count >= 3}
    raw: list[dict[str, Any]] = []
    section_stack: list[str] = []
    toc_region = False
    preface_region = False
    structural_noise = {"toc", "copyright", "preface", "header_footer", "page_number"}
    printed_by_page: dict[int, int] = {}  # 页号 → 教材印刷页码（[页码=N] 标记）

    for page_no, page in enumerate(pages, 1):
        lines = [_norm(x) for x in page.splitlines() if _norm(x)]
        marker_count = page.count("􀆺") + page.count("……") + page.count("…")
        numeric_lines = sum(1 for line in lines if re.fullmatch(r"[0-9０-９]+", line))
        early_front_matter = page_no <= max(20, int(len(pages) * 0.15))
        compact_head = re.sub(r"\s+", "", "".join(lines[:8]))
        if early_front_matter and (any(_PREFACE_RE.search(line) for line in lines[:8])
                                   or compact_head.startswith(("前言", "序言", "内容提要", "编者的话"))):
            preface_region = True
        if not early_front_matter and toc_region:
            toc_region = False
        if early_front_matter and (_TOC_RE.search(page) or marker_count >= 8
                                   or (len(lines) >= 20 and numeric_lines >= 6)):
            toc_region = True
            preface_region = False
        elif toc_region and marker_count == 0 and numeric_lines <= 1 and any(len(x) > 30 for x in lines):
            toc_region = False

        blocks: list[tuple[str, str, list[str]]] = []
        normalized_page, raw_map = _normalize_with_raw_map(page)
        source_cursor = 0
        # 印刷页码标记（OCR prompt v2 / 原生收割产出）：位置容错——标记可在页首
        # 独立行、行尾甚至句中；剥离标记子串（行内其余正文保留），取该页最后
        # 一个标记数字进 metadata（printed_page），不参与切块正文。剥离后为空的
        # 行整行丢弃。
        stripped_lines: list[str] = []
        printed_marker: list[int] = []

        def _take_marker(m: "re.Match[str]") -> str:
            printed_marker.append(int(m.group(1)))
            return ""

        for line in lines:
            if _PRINTED_PAGE_RE.match(line):
                _PRINTED_PAGE_INLINE_RE.sub(_take_marker, line)
                continue
            if _PRINTED_PAGE_INLINE_RE.search(line):
                line = _PRINTED_PAGE_INLINE_RE.sub(_take_marker, line).strip()
                if not line:
                    continue
            stripped_lines.append(line)
        if printed_marker:
            printed_by_page[page_no] = printed_marker[-1]
        lines = stripped_lines
        current: list[str] = []
        in_special = False  # 处于 [图...]/[表...] 标记块内（图述/表格行从属）
        for line in lines:
            heading = _is_heading(line)
            special_start = bool(_FIGURE_MARK_RE.match(line) or _TABLE_MARK_RE.match(line))
            continues_special = in_special and (
                _SPECIAL_CONT_RE.match(line) or "|" in line or "｜" in line)
            if (heading or special_start or (in_special and not continues_special)) and current:
                piece = "\n".join(current).strip()
                flags = _noise_flags(piece, repeated=piece in repeated)
                if toc_region:
                    flags = list(dict.fromkeys(flags + ["toc"]))
                elif preface_region:
                    flags = list(dict.fromkeys(flags + ["preface"]))
                blocks.append((piece, "paragraph", flags))
                current = []
                in_special = False
            if heading:
                flags = _noise_flags(line, repeated=line in repeated)
                if toc_region:
                    flags = list(dict.fromkeys(flags + ["toc"]))
                elif preface_region:
                    flags = list(dict.fromkeys(flags + ["preface"]))
                blocks.append((line, "heading", flags))
            else:
                if special_start:
                    in_special = True
                current.append(line)
        if current:
            piece = "\n".join(current).strip()
            flags = _noise_flags(piece, repeated=piece in repeated)
            if toc_region:
                flags = list(dict.fromkeys(flags + ["toc"]))
            elif preface_region:
                flags = list(dict.fromkeys(flags + ["preface"]))
            blocks.append((piece, "paragraph", flags))

        for block_text, kind, flags in blocks:
            if kind == "heading":
                title = block_text
                heading_level = _heading_level(title)
                noisy_heading = bool(set(flags) & structural_noise)
                if noisy_heading:
                    item_path = (section_stack + [title])[-3:]
                else:
                    effective_level = min(heading_level, len(section_stack) + 1)
                    section_stack = section_stack[:effective_level - 1] + [title]
                    item_path = section_stack[-3:]
                pieces = [(title, "heading", heading_level, not noisy_heading, item_path)]
            else:
                block_type = _block_type(block_text)
                pieces = [(piece, block_type, None, False, section_stack[-3:])
                          for piece in _split_piece(block_text, block_type)]

            for piece, block_type, heading_level, structural_heading, item_path in pieces:
                pos = normalized_page.find(piece, source_cursor)
                if pos < 0:
                    pos = normalized_page.find(piece)
                mapping_exact = pos >= 0
                if pos < 0:
                    pos = source_cursor
                normalized_end = min(len(normalized_page), pos + len(piece))
                raw_start, raw_end = _raw_offsets(pos, normalized_end, raw_map, len(page))
                source_cursor = max(source_cursor, normalized_end)
                raw.append({
                    "text": piece, "page": page_no if multi else None,
                    "block_type": block_type, "noise_flags": flags,
                    "section_path": list(item_path), "heading_level": heading_level,
                    "structural_heading": structural_heading,
                    "source_start": raw_start, "source_end": raw_end,
                    "normalized_start": pos, "normalized_end": normalized_end,
                    "mapping_exact": mapping_exact,
                    "normalization_changed": normalized_page != page,
                })

    chunks: list[Chunk] = []
    starts_new_semantic_block = {"heading", "figure", "definition", "theorem",
                                 "example", "exercise", "solution", "summary",
                                 "metadata"}
    for item in raw:
        piece = item["text"]
        if not piece:
            continue
        # 图/表块保持原子性：既不并入前块，也不接收后续段落打包。
        prev_types = set((chunks[-1].metadata.get("block_types") or [])
                         if chunks else [])
        can_pack = (chunks and chunks[-1].page == item["page"]
                    and item["block_type"] not in starts_new_semantic_block
                    and not item["noise_flags"]
                    and not prev_types & {"figure", "table"}
                    and not chunks[-1].metadata.get("hard_boundary"))
        if can_pack:
            candidate = f"{chunks[-1].text}\n{piece}"
            if estimate_model_tokens(candidate) <= SOFT_TOKEN_LIMIT:
                chunks[-1].text = candidate
                chunks[-1].tokens = tokenize(candidate)
                chunks[-1].metadata.setdefault("block_types", []).append(item["block_type"])
                chunks[-1].metadata["source_end"] = item.get("source_end")
                chunks[-1].metadata["normalized_end"] = item.get("normalized_end")
                chunks[-1].metadata["mapping_exact"] = bool(
                    chunks[-1].metadata.get("mapping_exact") and item.get("mapping_exact"))
                chunks[-1].metadata["token_estimate"] = estimate_model_tokens(candidate)
                continue
        idx = len(chunks)
        chunk_id = f"{file_id or source}#{idx}"
        chunk = Chunk(chunk_id=chunk_id, source=source, text=piece, index=idx,
                      tokens=tokenize(piece), file_id=file_id, page=item["page"])
        chunk.metadata.update({
            "chunk_schema": CHUNK_SCHEMA_VERSION,
            "block_types": [item["block_type"]],
            "noise_flags": list(item["noise_flags"]),
            "section_path": item["section_path"],
            "heading_level": item.get("heading_level"),
            "structural_heading": bool(item.get("structural_heading")),
            "page_range": ([item["page"], item["page"]] if item["page"] else None),
            "source_page": item["page"],
            "printed_page": (printed_by_page.get(int(item["page"]))
                             if item.get("page") else None),
            "source_start": item.get("source_start"),
            "source_end": item.get("source_end"),
            "normalized_start": item.get("normalized_start"),
            "normalized_end": item.get("normalized_end"),
            "mapping_basis": "nfkc_with_raw_offset_map",
            "mapping_exact": bool(item.get("mapping_exact")),
            "normalization_changed": bool(item.get("normalization_changed")),
            "normalized_nfkc": True,
            "token_estimate": estimate_model_tokens(piece),
            "hard_boundary": (item["block_type"] == "heading"
                              or item["block_type"] in {"figure", "table"}
                              or bool(item["noise_flags"])),
        })
        chunks.append(chunk)

    heading_stack: dict[int, str] = {}
    for idx, chunk in enumerate(chunks):
        metadata = chunk.metadata
        if metadata.get("structural_heading"):
            level = int(metadata.get("heading_level") or 3)
            parent_levels = [depth for depth in heading_stack if depth < level]
            metadata["parent_id"] = heading_stack[max(parent_levels)] if parent_levels else None
            heading_stack = {depth: cid for depth, cid in heading_stack.items() if depth < level}
            heading_stack[level] = chunk.chunk_id
        else:
            metadata["parent_id"] = heading_stack[max(heading_stack)] if heading_stack else None
        metadata["prev_id"] = chunks[idx - 1].chunk_id if idx else None
        metadata["next_id"] = chunks[idx + 1].chunk_id if idx + 1 < len(chunks) else None
        metadata["content_sha256"] = hashlib.sha256(chunk.text.encode()).hexdigest()
    return chunks


def active_chunk_schema() -> str:
    from .config import settings
    return CHUNK_SCHEMA_VERSION if settings.rag_chunker_mode == "v2" else "legacy-v1"


def chunk_text_for_rag(text: str, source: str, file_id: str = "") -> list[Chunk]:
    from .config import settings
    if settings.rag_chunker_mode == "v2":
        return chunk_text_v2(text, source, file_id)
    from .retriever import chunk_text
    return chunk_text(text, source=source, file_id=file_id)


def chunks_from_meta(text: str, source: str, file_id: str,
                     meta: dict | None) -> list[Chunk]:
    """按文件元数据的 ``chunk_schema`` 选分块器（重载/恢复路径的统一入口）。

    标记为 structured-v* 的文件用 V2 结构化分块（页边界/标题硬边界/保护块），
    未打标的旧文件保持 V1 定长行为——禁止把已结构化的文件静默退回暴力分块。
    """
    schema = str((meta or {}).get("chunk_schema") or "")
    if schema.startswith("structured-v") and text.strip():
        return chunk_text_v2(text, source=source, file_id=file_id)
    from .retriever import chunk_text
    return chunk_text(text, source=source, file_id=file_id)
