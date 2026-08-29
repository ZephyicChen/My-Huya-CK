"""解析 TAF 回调中消费徽章的紧凑字节字段。"""

from __future__ import annotations


def consume_badge_level(data: bytes) -> int | None:
    """读取 11200 徽章结构的 tag 1；未知结构安全返回 ``None``。"""
    pos = 0
    size = len(data)
    widths = {0: 1, 1: 2, 2: 4, 3: 8, 4: 4, 5: 8}
    while pos < size:
        head = data[pos]
        pos += 1
        field_type = head & 0x0F
        tag = head >> 4
        if tag == 15:
            if pos >= size:
                return None
            tag = data[pos]
            pos += 1

        if field_type == 12:
            value = 0
        elif field_type in widths:
            width = widths[field_type]
            if pos + width > size:
                return None
            raw = data[pos : pos + width]
            pos += width
            if field_type in {4, 5}:
                continue
            value = int.from_bytes(raw, "big", signed=True)
        elif field_type == 6:
            if pos >= size:
                return None
            width = data[pos]
            pos += 1
            if pos + width > size:
                return None
            pos += width
            continue
        elif field_type == 7:
            if pos + 4 > size:
                return None
            width = int.from_bytes(data[pos : pos + 4], "big")
            pos += 4
            if pos + width > size:
                return None
            pos += width
            continue
        elif field_type == 11:
            return None
        else:
            return None

        if tag == 1:
            return value
    return None
