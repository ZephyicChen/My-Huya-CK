"""UI 表单模式与默认配置。"""

DEFAULT = {
    "enabled": False,
    "min_noble_level": 2,
    "min_consume_level": 0,
    "template": "欢迎{guard_prefix|noble_prefix}{nick}哥进入直播间~",
}

FIELDS = [
    {"key": "enabled", "label": "启用欢迎", "type": "bool"},
    {
        "key": "min_noble_level",
        "label": "欢迎谁",
        "type": "select",
        "options": [
            {"value": 0, "label": "所有贵族"},
            {"value": 1, "label": "剑士及以上"},
            {"value": 2, "label": "骑士及以上"},
            {"value": 3, "label": "领主及以上"},
            {"value": 4, "label": "公爵及以上"},
        ],
    },
    {
        "key": "min_consume_level",
        "label": "最低消费等级",
        "type": "int",
        "hint": "0 表示不限制。",
        "min": 0,
        "placeholder": "不限制",
    },
    {
        "key": "template",
        "label": "欢迎文案",
        "type": "text",
        "hint": "变量 {nick} 昵称 / {guard_prefix} 守护档名（至尊/超级/初爱守护，无守护为空）/ {noble_prefix} 公爵及以上爵位 / {noble_name} / {consume_level}。{A|B|字} 从左到右取第一个非空，如默认文案；字面量也可当兜底",
    },
]
