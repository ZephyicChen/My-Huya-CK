DEFAULT = {
    "enabled": False,
    "template": "感谢{nick}为主播{action}{noble_name}{months}个月!",
}

FIELDS = [
    {"key": "enabled", "label": "启用贵族感谢", "type": "bool"},
    {
        "key": "template",
        "label": "感谢文案",
        "type": "text",
        "hint": "变量 {nick} {action} {noble_name} {months}。action 为开通/升级或续费。",
    },
]
