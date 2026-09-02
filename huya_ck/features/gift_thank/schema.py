DEFAULT = {
    "enabled": False,
    "min_value_fen": 600,
    "min_unit_value_fen": 0,
    "template": "感谢{nick}送的{count}个{item_name}",
    "merge_quiet_ms": 3000,
    "merge_max_ms": 8000,
}

FIELDS = [
    {"key": "enabled", "label": "启用礼物感谢", "type": "bool"},
    {
        "key": "min_value_fen",
        "label": "低于多少元不感谢",
        "type": "yuan",
        "hint": "按本包合计。虎粮等 0 元礼物不会感谢。",
        "min": 0,
        "step": 0.1,
    },
    {
        "key": "min_unit_value_fen",
        "label": "单件礼物低于多少元不感谢",
        "type": "yuan",
        "hint": "按本包合计金额 ÷ 数量计算，可过滤一次赠送多个的低单价礼物。",
        "min": 0,
        "step": 0.1,
    },
    {
        "key": "merge_quiet_ms",
        "label": "连击静默几秒后合并感谢",
        "type": "seconds",
        "hint": "同一人连送同一种礼物，静默这么久后合并成一条感谢，数量和金额按合计。0 秒表示不合并，每包立刻判断。",
        "min": 0,
        "step": 0.5,
        "placeholder": "3 秒",
    },
    {
        "key": "merge_max_ms",
        "label": "连击最长等几秒",
        "type": "seconds",
        "hint": "窗口从第一包起最长等待，到点强制结算，之后的包开新窗口。",
        "min": 0,
        "step": 0.5,
        "placeholder": "8 秒",
    },
    {
        "key": "template",
        "label": "感谢文案",
        "type": "text",
        "hint": "变量 {nick} {item_name} {count} {value_yuan}。{A|B} 从左到右取第一个非空，字面量可当兜底",
    },
]
