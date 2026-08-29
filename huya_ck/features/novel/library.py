"""本地小说库：上传、索引、删除、预览。文件名只用程序生成的 ID，禁止拼接用户输入的路径。"""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from pathlib import Path

from huya_ck.features.novel.splitter import clean_text
from huya_ck.log import get_logger

log = get_logger()

MAX_SIZE_BYTES = 5 * 1024 * 1024
PREVIEW_CHARS = 200


class NovelError(Exception):
    """面向用户的上传/删除错误。"""


class NovelLibrary:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._lock = threading.Lock()

    def _resolve(self, novel_id: str) -> Path:
        """校验解析后的绝对路径仍位于小说目录内。"""
        target = (self._root / f"{novel_id}.txt").resolve()
        root = self._root.resolve()
        if root != target and root not in target.parents:
            raise NovelError("非法的小说路径")
        return target

    def index_path(self) -> Path:
        return self._root / "index.json"

    def _read_index(self) -> dict:
        path = self.index_path()
        if not path.exists():
            return {"novels": []}
        try:
            with path.open(encoding="utf-8") as handle:
                raw = json.load(handle)
        except Exception:
            return {"novels": []}
        if not isinstance(raw, dict) or not isinstance(raw.get("novels"), list):
            return {"novels": []}
        return raw

    def _write_index(self, data: dict) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        tmp = self.index_path().with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        tmp.replace(self.index_path())

    def list(self) -> list[dict]:
        with self._lock:
            index = self._read_index()
        out = []
        for item in index["novels"]:
            entry = dict(item)
            entry["exists"] = self._resolve(entry["id"]).exists()
            out.append(entry)
        return out

    def get(self, novel_id: str) -> dict | None:
        for item in self.list():
            if item["id"] == novel_id:
                return item
        return None

    def upload(self, display_name: str, data: bytes) -> dict:
        """保存一部小说。display_name 只作为显示名称，实际文件用随机 ID 命名。"""
        if not data:
            raise NovelError("文件内容为空")
        if len(data) > MAX_SIZE_BYTES:
            raise NovelError("文件超过 5 MiB 上限")
        try:
            raw_text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise NovelError("文件不是有效的 UTF-8 文本") from exc
        text = clean_text(raw_text)
        if not text:
            raise NovelError("清理后没有可发送的正文")
        # 摘要针对落盘的清理后正文计算
        sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
        with self._lock:
            for item in self._read_index()["novels"]:
                if item.get("sha256") == sha256:
                    raise NovelError(f"内容与《{item['name']}》完全相同，未重复保存")
            novel_id = secrets.token_hex(8)
            self._root.mkdir(parents=True, exist_ok=True)
            target = self._resolve(novel_id)
            target.write_text(text, encoding="utf-8", newline="\n")
            meta = {
                "id": novel_id,
                "name": (display_name or "未命名").strip()[:80] or "未命名",
                "file_name": f"{novel_id}.txt",
                "size": len(data),
                "sha256": sha256,
                "created_at": int(time.time()),
            }
            index = self._read_index()
            index["novels"].append(meta)
            self._write_index(index)
        log.info("已导入小说《%s》（%d 字节，id=%s）", meta["name"], meta["size"], novel_id)
        return meta

    def read_text(self, novel_id: str) -> str:
        """读取正文并校验摘要；不一致抛 NovelError。"""
        meta = self.get(novel_id)
        if meta is None:
            raise NovelError("小说不存在")
        target = self._resolve(novel_id)
        if not target.exists():
            raise NovelError("小说文件已丢失")
        text = target.read_text(encoding="utf-8")
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != meta["sha256"]:
            raise NovelError("小说文件内容与导入时不一致")
        return text

    def preview(self, novel_id: str, *, head_chars: int = PREVIEW_CHARS, max_chars_segment: int | None = None) -> dict:
        text = self.read_text(novel_id)
        from huya_ck.features.novel.splitter import split_segments

        segments = split_segments(text, max_chars=max_chars_segment) if max_chars_segment else None
        return {
            "head": text[:head_chars],
            "total_chars": len(text),
            "segments": len(segments) if segments is not None else None,
        }

    def delete(self, novel_id: str) -> None:
        with self._lock:
            index = self._read_index()
            kept = [item for item in index["novels"] if item["id"] != novel_id]
            if len(kept) == len(index["novels"]):
                raise NovelError("小说不存在")
            target = self._resolve(novel_id)
            if target.exists():
                target.unlink()
            index["novels"] = kept
            self._write_index(index)
        log.info("已删除小说 id=%s（正文与元数据一并删除，不可恢复）", novel_id)


def default_library() -> NovelLibrary:
    from huya_ck.paths import NOVEL_DATA_DIR

    return NovelLibrary(NOVEL_DATA_DIR)


library = default_library()
