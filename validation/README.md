# 验证期材料（正式版删除）

URI 通道可行性验证，不是场控产品。产品在仓库根 `huya_ck/`，用根目录 `run.bat`。

| 路径 | 说明 |
| --- | --- |
| `huya_probe/` | 旧采集探针 |
| `run.bat` | 旧采集菜单 |
| `docs/` | 旧需求、`Event.png`、看见层历史设计稿 |
| `event-captures/` | 含用户数据，勿提交 |
| `tests/` | 信封解析单测 |

```bat
validation\run.bat
```

```bat
set PYTHONPATH=validation
.venv\Scripts\python -m huya_probe capture --room 房间号
```
