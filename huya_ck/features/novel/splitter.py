"""文本导入清理与拆分。只产出弹幕段文本；进度由播放器记段序号。"""

from __future__ import annotations

import re

PRIMARY_BREAK = "。！？；"
SECONDARY_BREAK = "，、："
_MULTISPACE = re.compile(r"[ \t　]+")
_BLANK_LINES = re.compile(r"\n{3,}")


def clean_text(raw: str) -> str:
    """去 BOM、统一换行、合并连续空格和多余空行。保留自然段边界和中文标点。"""
    text = raw.lstrip("﻿")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = _MULTISPACE.sub(" ", text)
    text = _BLANK_LINES.sub("\n\n", text)
    return text.strip()


def split_segments(text: str, *, max_chars: int) -> list[str]:
    """把清洗后的文本拆成不超过 max_chars 的弹幕段列表。

    拆分顺序：自然段 → 句末标点 → 次级标点 → 硬切。标点跟随前一句，不产生空段。
    """
    segments: list[str] = []
    for paragraph in text.split("\n"):
        if paragraph:
            segments.extend(_split_piece(paragraph, max_chars))
    return segments


def _split_piece(text: str, limit: int) -> list[str]:
    """把一段文本拆成不超过 limit 的若干片。"""
    if limit <= 0:
        limit = 1
    if len(text) <= limit:
        return [text]
    pieces: list[str] = []
    # 第一遍：按句末标点切出句子（标点跟随前一句）
    chunks: list[str] = []
    start = 0
    for pos, char in enumerate(text):
        if char in PRIMARY_BREAK:
            chunks.append(text[start : pos + 1])
            start = pos + 1
    if start < len(text):
        chunks.append(text[start:])
    # 第二遍：贪心合并成不超限的片；超长句子递归用次级标点/硬切
    buf = ""
    for chunk in chunks:
        if len(chunk) > limit:
            if buf:
                pieces.append(buf)
                buf = ""
            pieces.extend(_split_long_chunk(chunk, limit))
            continue
        if buf and len(buf) + len(chunk) > limit:
            pieces.append(buf)
            buf = ""
        buf += chunk
    if buf:
        pieces.append(buf)
    return pieces


def _split_long_chunk(chunk: str, limit: int) -> list[str]:
    """超长句子：先按次级标点贪心切，仍超长再硬切。标点跟随前一句。"""
    parts: list[str] = []
    start = 0
    for pos, char in enumerate(chunk):
        if char in SECONDARY_BREAK:
            parts.append(chunk[start : pos + 1])
            start = pos + 1
    if start < len(chunk):
        parts.append(chunk[start:])
    result: list[str] = []
    buf = ""
    for part in parts:
        while len(part) > limit:
            if buf:
                result.append(buf)
                buf = ""
            result.append(part[:limit])
            part = part[limit:]
        if buf and len(buf) + len(part) > limit:
            result.append(buf)
            buf = ""
        buf += part
    if buf:
        result.append(buf)
    return result
