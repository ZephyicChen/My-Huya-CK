DEFAULT = {
    "enabled": False,
    "min_value_fen": 600,
    "min_unit_value_fen": 0,
    "template": "感谢{nick}送的{count}个{item_name}",
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
        "key": "template",
        "label": "感谢文案",
        "type": "text",
        "hint": "变量 {nick} {item_name} {count} {value_yuan}。{A|B} 从左到右取第一个非空，字面量可当兜底",
    },
]
