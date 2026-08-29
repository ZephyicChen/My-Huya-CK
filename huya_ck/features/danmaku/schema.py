DEFAULT = {
    "enabled": False,
    "interval_ms": 3000,
    "queue_max": 20,
}

FIELDS = [
    {
        "key": "enabled",
        "label": "允许发送",
        "type": "bool",
        "hint": "关闭后所有欢迎/感谢都不会发出。",
    },
    {
        "key": "interval_ms",
        "label": "两条弹幕至少隔几秒",
        "type": "seconds",
        "hint": "从上一条成功点击发送后开始计时，避免连着刷屏。",
        "min": 0,
        "step": 0.5,
    },
    {
        "key": "queue_max",
        "label": "最多排队几条",
        "type": "int",
        "min": 1,
    },
]
