"""文本轮播播放器：状态机、间隔调度、进度持久化。

不直接操作 Page：只向统一 danmaku 队列提交低优先级消息，并等发送结果回调。
同一时间最多一段在途；发送成功才推进进度；失败不重试，顺序往下走。
进度只记条目序号 next_index：改拆分字数后序号会漂移，进度归零重新开始。
"""

from __future__ import annotations

import threading
import time

from huya_ck.features.danmaku.handler import danmaku
from huya_ck.features.novel import library as library_module
from huya_ck.features.novel.library import NovelError
from huya_ck.features.novel.splitter import split_segments
from huya_ck.log import get_logger
from huya_ck.platform import config_store

log = get_logger()

STATES = ("idle", "playing", "paused", "completed", "error")
FEEDBACK_PREVIEW_CHARS = 30


class NovelPlayer:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._in_flight = False
        self._last_result_at: float | None = None
        self._last_error = ""
        self._last_send_ok: bool | None = None
        self._segments: list[str] | None = None
        self._segments_key: tuple | None = None
        self._generation = 0

    # ---------- 状态查询 ----------

    def snapshot(self) -> dict:
        cfg = config_store.novel_config()
        with self._lock:
            snap = {
                "config": cfg,
                "in_flight": self._in_flight,
                "last_error": self._last_error,
                "last_send_ok": self._last_send_ok,
            }
        snap["interaction_enabled"] = config_store.interaction_config()["enabled"]
        snap["novel_meta"] = library_module.library.get(cfg["novel_id"]) if cfg["novel_id"] else None
        segments = self._load_segments(cfg)
        snap["total_segments"] = len(segments) if segments is not None else 0
        index = self._current_index(cfg, segments)
        snap["current_index"] = index
        snap["next_preview"] = segments[index][:80] if segments and 0 <= index < len(segments) else ""
        return snap

    # ---------- 状态机动作 ----------

    def start(self) -> dict:
        """从第一段重新播放。"""
        cfg = self._effective_config()
        segments = self._require_segments(cfg)
        with self._lock:
            if self._in_flight:
                return self._refuse("当前段还在发送中")
        config_store.set_novel_state("playing", next_index=0)
        self._reset_runtime()
        # 丢弃旧回调：上一次播放的“已发送第 N 条”结果不能再推进新进度
        self._generation += 1
        log.info("轮播开始（%s，共 %d 条）", self._novel_name(cfg), len(segments))
        return {"ok": True, "state": "playing"}

    def pause(self, *, reason: str = "") -> dict:
        """保留下一段位置。"""
        cfg = config_store.novel_config()
        if cfg["state"] in ("idle", "completed"):
            return {"ok": True, "state": cfg["state"]}
        config_store.set_novel_state("paused")
        with self._lock:
            if reason:
                self._last_error = reason
        log.info("轮播已暂停%s", f"：{reason}" if reason else "")
        return {"ok": True, "state": "paused"}

    def resume(self) -> dict:
        cfg = self._effective_config()
        segments = self._require_segments(cfg)
        current = config_store.novel_config()
        if current["state"] == "completed":
            return self._refuse("已播完，请用「开始」重新播放")
        config_store.set_novel_state("playing")
        log.info("轮播继续（%s）", self._novel_name(cfg))
        return {"ok": True, "state": "playing"}

    def stop(self) -> dict:
        """停止并把进度归零。"""
        config_store.set_novel_state("idle", next_index=0)
        self._reset_runtime()
        log.info("轮播已停止，进度归零")
        return {"ok": True, "state": "idle"}

    def next_segment(self) -> dict:
        """请求发送当前待播段；成功后推进一段。"""
        cfg = self._effective_config()
        segments = self._require_segments(cfg)
        with self._lock:
            if self._in_flight:
                return self._refuse("当前段还在发送中")
        self._submit_current(cfg, segments)
        return {"ok": True, "state": config_store.novel_config()["state"]}

    # ---------- 工人线程驱动 ----------

    def tick(self) -> None:
        """工人线程每个泵循环调用一次。只管自己的状态；发送被全局关闭时，
        danmaku.submit 关闭时会丢弃并回调失败，播放器照常推进（失败不重试）。"""
        cfg = config_store.novel_config()
        if cfg["state"] != "playing":
            return
        if not config_store.interaction_config()["enabled"]:
            self.pause(reason="趣味互动总开关已关闭")
            return
        if not cfg["enabled"]:
            self.pause(reason="轮播模块开关已关闭")
            return
        segments = self._load_segments(cfg)
        if segments is None:
            self._enter_error("文本文件丢失或内容不一致")
            return
        index = self._current_index(cfg, segments)
        if index >= len(segments):
            self._finish_or_loop(cfg, len(segments))
            return
        with self._lock:
            if self._in_flight:
                return
            interval = cfg["interval_ms"] / 1000.0
            if self._last_result_at is not None and time.monotonic() - self._last_result_at < interval:
                return
        self._submit_current(cfg, segments)

    # ---------- 内部 ----------

    def _effective_config(self) -> dict:
        """校验开关链，返回轮播配置。"""
        if not config_store.interaction_config()["enabled"]:
            raise NovelError("趣味互动总开关未开启")
        cfg = config_store.novel_config()
        if not cfg["enabled"]:
            raise NovelError("轮播模块开关未开启")
        if not cfg["novel_id"]:
            raise NovelError("尚未选择文本")
        return cfg

    def _require_segments(self, cfg: dict) -> list[str]:
        segments = self._load_segments(cfg)
        if not segments:
            raise NovelError("文本没有可发送的条目")
        return segments

    def _load_segments(self, cfg: dict) -> list[str] | None:
        """按（文本 ID + 每条字数）缓存拆分结果。文件失效返回 None。"""
        key = (cfg["novel_id"], cfg["max_chars"])
        with self._lock:
            if self._segments_key == key and self._segments is not None:
                return self._segments
        if not cfg["novel_id"]:
            return None
        try:
            text = library_module.library.read_text(cfg["novel_id"])
        except NovelError:
            return None
        segments = split_segments(text, max_chars=cfg["max_chars"])
        with self._lock:
            self._segments = segments
            self._segments_key = key
        return segments

    def _finish_or_loop(self, cfg: dict, total: int) -> None:
        """播完最后一段：循环模式回卷到第一段继续，否则停在 completed。"""
        if cfg.get("loop"):
            config_store.set_novel_state("playing", next_index=0)
            log.info("轮播已播完一轮（%s，共 %d 条），循环回到第一条", self._novel_name(cfg), total)
            return
        config_store.set_novel_state("completed", next_index=total)
        log.info("轮播播放完成（%s），自动停止", self._novel_name(cfg))

    def _current_index(self, cfg: dict, segments: list[str] | None) -> int:
        if not segments:
            return 0
        return min(cfg["next_index"], len(segments))

    def _submit_current(self, cfg: dict, segments: list[str]) -> None:
        index = self._current_index(cfg, segments)
        if index >= len(segments):
            self._finish_or_loop(cfg, len(segments))
            return
        total = len(segments)
        text = segments[index]
        with self._lock:
            self._in_flight = True
            generation = self._generation
        log.info(
            "轮播提交第 %d/%d 条（%s…，共 %d 字）",
            index + 1,
            total,
            text[:FEEDBACK_PREVIEW_CHARS],
            len(text),
        )
        danmaku.submit(
            text,
            source="novel",
            event_id=f"novel:{cfg['novel_id']}:{index}",
            reason=f"轮播 {index + 1}/{total}",
            priority="low",
            on_result=lambda ok: self._on_send_result(ok, generation),
        )

    def _on_send_result(self, ok: bool, generation: int) -> None:
        """danmaku 队列回调（工人线程）。无论成败都推进到下一段：
        失败不重试也不丢段号，与欢迎/感谢的“失败不重试”语义一致。"""
        with self._lock:
            if generation != self._generation:
                return  # 结果属于上一次播放（已被“开始”重置），丢弃
            self._in_flight = False
            self._last_result_at = time.monotonic()
            self._last_send_ok = ok
        if not ok:
            log.info("轮播本条发送失败，丢弃并推进到下一条")
        cfg = config_store.novel_config()
        segments = self._load_segments(cfg)
        if segments is None:
            self._enter_error("文本文件丢失或内容不一致")
            return
        index = self._current_index(cfg, segments)
        if index + 1 < len(segments):
            config_store.set_novel_state("playing", next_index=index + 1)
        else:
            self._finish_or_loop(cfg, len(segments))

    def _enter_error(self, message: str) -> None:
        config_store.set_novel_state("error")
        with self._lock:
            self._last_error = message
            self._in_flight = False
        log.info("轮播进入异常状态：%s", message)

    def _reset_runtime(self) -> None:
        with self._lock:
            self._in_flight = False
            self._last_error = ""
            self._last_send_ok = None

    def _refuse(self, reason: str) -> dict:
        log.info("拒绝轮播操作：%s", reason)
        return {"ok": False, "state": config_store.novel_config()["state"], "reason": reason}

    def _novel_name(self, cfg: dict) -> str:
        meta = library_module.library.get(cfg["novel_id"])
        return meta["name"] if meta else cfg["novel_id"]


def downgrade_on_restart() -> None:
    """进程重启后 playing 必须恢复为 paused，避免无人值守自动刷屏。"""
    cfg = config_store.novel_config()
    if cfg["state"] == "playing":
        config_store.set_novel_state("paused")
        log.info("检测到上次退出时轮播仍在进行，已降级为暂停（保留进度）")


novel_player = NovelPlayer()
downgrade_on_restart()
