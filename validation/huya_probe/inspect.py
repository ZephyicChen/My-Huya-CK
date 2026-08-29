"""Lightweight JCE field preview for analysis. Not a business decoder."""

from __future__ import annotations

from .jce import (
    EN_INT8,
    EN_INT16,
    EN_INT32,
    EN_INT64,
    EN_LIST,
    EN_SIMPLELIST,
    EN_STRING1,
    EN_STRING4,
    EN_STRUCTBEGIN,
    EN_STRUCTEND,
    EN_ZERO,
    JceError,
    JceReader,
)

_SKIP_TEXT = ("http://", "https://", "<ua>", ".png", ".jpg", ".jpeg", ".mp4", ".webp")


def extract_preview(payload: bytes, max_text: int = 8, max_ints: int = 12) -> dict:
    texts: list[str] = []
    ints: list[int] = []
    _walk(payload, texts, ints, depth=0)
    texts = [t for t in texts if _keep_text(t)][:max_text]
    return {"text_preview": texts, "int_preview": ints[:max_ints]}


def _keep_text(value: str) -> bool:
    value = value.strip()
    if len(value) < 1 or len(value) > 160:
        return False
    lower = value.lower()
    return not any(token in lower for token in _SKIP_TEXT)


def _walk(data: bytes, texts: list[str], ints: list[int], depth: int) -> None:
    if depth > 3 or not data:
        return
    reader = JceReader(data)
    while reader.pos < len(reader.data):
        try:
            _tag, typ, size = reader.peek_head()
        except JceError:
            break
        reader.pos += size
        try:
            if typ == EN_ZERO:
                ints.append(0)
            elif typ == EN_INT8:
                ints.append(int.from_bytes(reader.data[reader.pos : reader.pos + 1], "big", signed=True))
                reader.pos += 1
            elif typ == EN_INT16:
                ints.append(int.from_bytes(reader.data[reader.pos : reader.pos + 2], "big", signed=True))
                reader.pos += 2
            elif typ == EN_INT32:
                ints.append(int.from_bytes(reader.data[reader.pos : reader.pos + 4], "big", signed=True))
                reader.pos += 4
            elif typ == EN_INT64:
                high = int.from_bytes(reader.data[reader.pos : reader.pos + 4], "big", signed=False)
                low = int.from_bytes(reader.data[reader.pos + 4 : reader.pos + 8], "big", signed=False)
                reader.pos += 8
                ints.append((high << 32) + low)
            elif typ == EN_STRING1:
                n = reader.data[reader.pos]
                reader.pos += 1
                texts.append(reader.data[reader.pos : reader.pos + n].decode("utf-8", errors="replace"))
                reader.pos += n
            elif typ == EN_STRING4:
                n = int.from_bytes(reader.data[reader.pos : reader.pos + 4], "big", signed=False)
                reader.pos += 4
                texts.append(reader.data[reader.pos : reader.pos + n].decode("utf-8", errors="replace"))
                reader.pos += n
            elif typ == EN_SIMPLELIST:
                _, _elem = reader.read_head()
                n = reader.read_int32(0, required=True, default=0) or 0
                blob = bytes(reader.data[reader.pos : reader.pos + n])
                reader.pos += n
                _walk(blob, texts, ints, depth + 1)
            elif typ == EN_STRUCTBEGIN:
                start = reader.pos
                while True:
                    _pt, pty, psz = reader.peek_head()
                    if pty == EN_STRUCTEND:
                        body = reader.data[start : reader.pos]
                        reader.pos += psz
                        _walk(body, texts, ints, depth + 1)
                        break
                    reader.pos += psz
                    reader.skip_field(pty)
            elif typ == EN_LIST:
                n = reader.read_int32(0, required=True, default=0) or 0
                for index in range(n):
                    _, item_type = reader.read_head()
                    if item_type == EN_STRUCTBEGIN:
                        start = reader.pos
                        while True:
                            _pt, pty, psz = reader.peek_head()
                            if pty == EN_STRUCTEND:
                                body = reader.data[start : reader.pos]
                                reader.pos += psz
                                if index < 3:
                                    _walk(body, texts, ints, depth + 1)
                                break
                            reader.pos += psz
                            reader.skip_field(pty)
                    else:
                        reader.skip_field(item_type)
            else:
                reader.skip_field(typ)
        except (JceError, IndexError, ValueError):
            break
