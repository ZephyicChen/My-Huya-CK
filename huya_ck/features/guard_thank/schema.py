DEFAULT = {
    "enabled": False,
    "template": "感谢{nick}为主播{action}{guard_name}!",
}

FIELDS = [
    {"key": "enabled", "label": "启用守护感谢", "type": "bool"},
    {
        "key": "template",
        "label": "感谢文案",
        "type": "text",
        "hint": "变量 {nick} {action} {guard_name}。action 为开通或升级；guard_name 为初爱守护、超级守护或至尊守护。",
    },
]
