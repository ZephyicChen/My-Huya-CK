DEFAULT = {
    "enabled": False,
    "template": "感谢{nick}为主播开通{superfan_name}!",
}

FIELDS = [
    {"key": "enabled", "label": "启用超粉感谢", "type": "bool"},
    {
        "key": "template",
        "label": "感谢文案",
        "type": "text",
        "hint": "变量 {nick} {superfan_name}。普通超粉和超粉PLUS统一按开通感谢。",
    },
]
