"""模板变量与 {a|b} 回退语法：取第一个非空项；token 是已知变量取值（无值为空），否则按字面量输出。"""

from __future__ import annotations

import re

_TOKEN = re.compile(r"\{([^{}]*)\}")
_FALLBACK = "|"


def render(template: str, data: dict) -> str:
    text = str(template or "")
    out: list[str] = []
    pos = 0
    for match in _TOKEN.finditer(text):
        out.append(text[pos : match.start()])
        out.append(_eval_expr(match.group(1), data))
        pos = match.end()
    out.append(text[pos:])
    return "".join(out).strip()


def _eval_expr(expr: str, data: dict) -> str:
    for part in expr.split(_FALLBACK):
        value = _eval_value(part.strip(), data)
        if value:
            return value
    return ""


def _eval_value(token: str, data: dict) -> str:
    if not token:
        return ""
    if token in data:
        value = data.get(token)
        return "" if value is None else str(value)
    return token
