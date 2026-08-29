"""Capture the live page event channel and extract URI envelopes.

This mode does not decode business structs. It records:
- WebSocket frames on the event channel (wsapi / *-ws.va.huya.com)
- URI values from MsgPush (cmd 7) and MsgPushV2 (cmd 22)
- page-side Taf / Kiwi dispatch if the player exposes it

The operator compares those live URIs with Event.png.
"""

from __future__ import annotations

import base64
import json
import time
import uuid
from collections import Counter
from typing import Any

from .browser import check_login_status, get_or_new_page, launch_persistent_browser, open_room
from .config import load_config
from .analyze import analyze_raw_path, print_summary
from .event_logger import CaptureLogger, extract_room_id, fingerprint, new_run_id, now_iso
from .inspect import extract_preview
from .jce import CMD_MSG_PUSH, CMD_MSG_PUSH_V2, JceError, parse_websocket_frames
from .uri_map import CANDIDATES, lookup

PROGRESS_INTERVAL_SECONDS = 10
DISCOVER_INTERVAL_SECONDS = 3
MAX_SAVED_FRAME_BYTES = 65536
UNPARSED_SAMPLE_LIMIT = 8

HOOK_JS = r"""
(() => {
  if (window.__huyaUriProbeActive) return;
  window.__huyaUriProbeActive = true;
  window.__huyaUriQueue = [];
  const report = (obj) => {
    const rec = Object.assign({ t: Date.now() }, obj);
    window.__huyaUriQueue.push(rec);
    if (window.__huyaUriQueue.length > 3000) window.__huyaUriQueue.shift();
    if (typeof window.__huyaUriReport === "function") {
      try { window.__huyaUriReport(JSON.stringify(rec)); } catch (e) {}
    }
  };
  const extractUri = (value) => {
    if (value == null) return null;
    if (typeof value === "number" && Number.isFinite(value)) return value;
    if (typeof value === "string" && /^\d+$/.test(value)) return Number(value);
    if (typeof value === "object") {
      for (const key of ["uri", "iUri", "URI", "nUri", "iUriType"]) {
        if (key in value) {
          const found = extractUri(value[key]);
          if (found != null) return found;
        }
      }
    }
    return null;
  };
  const wrapFn = (obj, key, label) => {
    try {
      const orig = obj[key];
      if (typeof orig !== "function" || orig.__huyaUriWrapped) return;
      const wrapped = function (...args) {
        try {
          let uri = null;
          for (const arg of args) {
            uri = extractUri(arg);
            if (uri != null) break;
          }
          if (uri == null && typeof args[0] === "string" && /^\d+$/.test(args[0])) uri = Number(args[0]);
          if (uri != null) report({ source: label + "." + key, uri });
        } catch (e) {}
        return orig.apply(this, args);
      };
      wrapped.__huyaUriWrapped = true;
      obj[key] = wrapped;
    } catch (e) {}
  };
  const inspect = (name, obj) => {
    if (!obj || typeof obj !== "object" || obj.__huyaUriSeen) return;
    obj.__huyaUriSeen = true;
    const hookNames = ["on","emit","once","dispatch","notify","push","trigger","onMessage","onPush","onPushMsg","pushMsg","recv","receive","onData"];
    for (const key of hookNames) wrapFn(obj, key, name);
    try {
      for (const key of Object.keys(obj)) {
        if (/push|msg|uri|signal|dispatch|notify|emit|recv/i.test(key)) wrapFn(obj, key, name);
      }
    } catch (e) {}
  };
  const scan = () => {
    const names = ["huyabaselibsTafSignal","huyabaselibsPushMsgControl","TafNetwork","Taf","TafMx","HUYA","HuyaKiwi","HuyaMgr","vplayerTaf"];
    for (const name of names) {
      try { inspect(name, window[name]); } catch (e) {}
    }
    try {
      if (typeof window.__kiwisdk_global_getTaf__ === "function") {
        inspect("kiwiTaf", window.__kiwisdk_global_getTaf__());
      }
    } catch (e) {}
  };
  scan();
  setInterval(scan, 1000);
})();
"""

DISCOVER_JS = """
() => {
  const result = {
    href: location.href,
    globals: [],
    tafmx_uris: null,
    huya_struct_names: [],
  };
  try {
    for (const key of Object.keys(window)) {
      if (/huya|taf|HUYA|Taf|HyPlayer|hyPlayer|TafMx/i.test(key)) {
        result.globals.push(key);
      }
    }
    const huya = window.HUYA || window.Huya;
    if (huya && typeof huya === "object") {
      result.huya_struct_names = Object.keys(huya).slice(0, 300);
    }
    const tafmx = window.TafMx || window.tafMx;
    if (tafmx && tafmx.UriMapping) {
      const mapping = {};
      for (const [uri, ctor] of Object.entries(tafmx.UriMapping)) {
        let name = (ctor && ctor.name) || null;
        if (!name && huya) {
          for (const [key, value] of Object.entries(huya)) {
            if (value === ctor) {
              name = key;
              break;
            }
          }
        }
        mapping[String(uri)] = name;
      }
      result.tafmx_uris = mapping;
    }
  } catch (err) {
    result.error = String(err);
  }
  return result;
}
"""


def safe_print(msg: str) -> None:
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("gbk", errors="replace").decode("gbk"))


def _b64(data: bytes, limit: int = MAX_SAVED_FRAME_BYTES) -> tuple[str, int, bool]:
    truncated = len(data) > limit
    chunk = data[:limit]
    return base64.b64encode(chunk).decode("ascii"), len(data), truncated


def _ws_label(url: str) -> str:
    return url.split("?", 1)[0]


def is_event_ws(url: str) -> bool:
    host = url.split("?", 1)[0].lower()
    if "server.va.huya.com" in host:
        return False
    return (
        "wsapi.huya.com" in host
        or "-ws.va.huya.com" in host
        or "ws.va.huya.com" in host
        or "ws.api.huya.com" in host
    )


class CaptureStats:
    def __init__(self) -> None:
        self.ws_open = 0
        self.ws_close = 0
        self.frames = 0
        self.push = 0
        self.uri_ok = 0
        self.unparsed = 0
        self.by_uri: Counter[int] = Counter()
        self.by_cmd: Counter[str] = Counter()
        self.ws_urls: set[str] = set()
        self.page_mapping: dict[str, str | None] | None = None
        self.page_globals: list[str] = []


def run_capture_mode(args, room_url: str) -> None:
    config = load_config()
    run_id = new_run_id(args.log_dir)
    session_id = uuid.uuid4().hex[:12]
    room_id = extract_room_id(room_url)
    logger = CaptureLogger(args.log_dir, room_id, room_url, run_id, session_id)
    stats = CaptureStats()
    verbose = bool(getattr(args, "verbose", False))

    pw, context = launch_persistent_browser(args.profile_dir)
    seen_ws: set[int] = set()
    hooked_pages: set[int] = set()
    unparsed_samples = 0
    last_progress = time.monotonic()
    last_discover = 0.0
    mapping_reported = False

    def record_push(
        *,
        source: str,
        ws_url: str,
        cmd_type: int | None,
        cmd_name: str | None,
        uri: int | None,
        payload: bytes,
        raw: bytes,
        push_type: int | None = None,
        protocol_type: int | None = None,
        group: str | None = None,
        extra: dict | None = None,
    ) -> None:
        stats.push += 1
        candidate = lookup(uri)
        if uri is not None:
            stats.by_uri[uri] += 1
            stats.uri_ok += 1
        preview = extract_preview(payload)
        payload_b64, payload_size, payload_truncated = _b64(payload)
        envelope_b64, envelope_size, envelope_truncated = _b64(raw)
        event = {
            "kind": "push",
            "source": source,
            "received_at": now_iso(),
            "ws_url": ws_url,
            "cmd_type": cmd_type,
            "cmd_name": cmd_name,
            "uri": uri,
            "group": group,
            "struct_name": candidate.struct_name if candidate else None,
            "candidate_event_type": candidate.event_type if candidate else "unknown",
            "meaning": candidate.meaning if candidate else None,
            "text_preview": preview["text_preview"],
            "int_preview": preview["int_preview"],
            "push_type": push_type,
            "protocol_type": protocol_type,
            "payload_encoding": "base64",
            "raw_payload": payload_b64,
            "payload_bytes": payload_size,
            "payload_truncated": payload_truncated,
            "envelope_encoding": "base64",
            "raw_envelope": envelope_b64,
            "envelope_bytes": envelope_size,
            "envelope_truncated": envelope_truncated,
            "raw_fingerprint": fingerprint(raw or payload),
            "parse_status": "uri_ok" if uri is not None else "envelope_ok",
        }
        if extra:
            event.update(extra)
        logger.write_raw(event)
        shown = uri is not None and stats.by_uri[uri] <= 8
        if verbose or shown:
            label = (candidate.struct_name or candidate.meaning) if candidate else "unknown"
            text = " | ".join(preview["text_preview"][:3])
            extra_text = f"  {text[:80]}" if text else ""
            grp = f" group={group}" if group else ""
            safe_print(
                f"[uri] {uri} {label}  src={source}{grp} payload={payload_size}B{extra_text}"
            )

    def on_js_report(raw: str) -> None:
        try:
            info = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return
        uri = info.get("uri")
        try:
            uri = int(uri) if uri is not None else None
        except (TypeError, ValueError):
            uri = None
        if uri is None:
            return
        record_push(
            source=str(info.get("source") or "page_js"),
            ws_url="",
            cmd_type=None,
            cmd_name="page_dispatch",
            uri=uri,
            payload=b"",
            raw=b"",
            extra={"js_source": info.get("source")},
        )

    def on_websocket(ws) -> None:
        ident = id(ws)
        if ident in seen_ws:
            return
        seen_ws.add(ident)
        stats.ws_open += 1
        stats.ws_urls.add(ws.url)
        logger.write_channel(
            {
                "kind": "ws_open",
                "received_at": now_iso(),
                "ws_url": ws.url,
                "event_channel": is_event_ws(ws.url),
            }
        )
        kind = "event" if is_event_ws(ws.url) else "other"
        safe_print(f"[channel] ws open ({kind})  {_ws_label(ws.url)}")

        def on_frame(payload: Any) -> None:
            handle_frame(payload, ws.url)

        def on_close() -> None:
            stats.ws_close += 1
            logger.write_channel(
                {
                    "kind": "ws_close",
                    "received_at": now_iso(),
                    "ws_url": ws.url,
                }
            )
            safe_print(f"[channel] ws close {_ws_label(ws.url)}")

        ws.on("framereceived", on_frame)
        ws.on("close", on_close)

    def handle_frame(payload: Any, ws_url: str) -> None:
        nonlocal unparsed_samples
        if not is_event_ws(ws_url):
            return
        stats.frames += 1
        if isinstance(payload, str):
            _handle_text_frame(payload, ws_url)
            return
        if not isinstance(payload, (bytes, bytearray)):
            stats.unparsed += 1
            return
        data = bytes(payload)
        try:
            parsed_list = parse_websocket_frames(data)
        except (JceError, Exception):
            stats.unparsed += 1
            if unparsed_samples < UNPARSED_SAMPLE_LIMIT:
                unparsed_samples += 1
                raw_b64, size, truncated = _b64(data, 256)
                logger.write_channel(
                    {
                        "kind": "unparsed_frame",
                        "received_at": now_iso(),
                        "ws_url": ws_url,
                        "byte_size": size,
                        "raw_preview_b64": raw_b64,
                        "truncated": truncated,
                    }
                )
            return

        if not parsed_list:
            return
        stats.by_cmd[parsed_list[0].cmd_name] += 1
        wrote_any = False
        for parsed in parsed_list:
            if parsed.uri is None and parsed.cmd_type not in (CMD_MSG_PUSH, CMD_MSG_PUSH_V2):
                continue
            wrote_any = True
            record_push(
                source=parsed.cmd_name,
                ws_url=ws_url,
                cmd_type=parsed.cmd_type,
                cmd_name=parsed.cmd_name,
                uri=parsed.uri,
                payload=parsed.payload,
                raw=parsed.raw,
                push_type=parsed.push_type,
                protocol_type=parsed.protocol_type,
                group=parsed.group,
            )
        if parsed_list[0].cmd_type == CMD_MSG_PUSH_V2 and not wrote_any and unparsed_samples < UNPARSED_SAMPLE_LIMIT:
            unparsed_samples += 1
            raw_b64, size, truncated = _b64(data, 256)
            logger.write_channel(
                {
                    "kind": "v2_unparsed",
                    "received_at": now_iso(),
                    "ws_url": ws_url,
                    "byte_size": size,
                    "raw_preview_b64": raw_b64,
                    "truncated": truncated,
                }
            )

    def _handle_text_frame(text: str, ws_url: str) -> None:
        uri = None
        try:
            obj = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            stats.unparsed += 1
            return
        for key in ("uri", "iUri", "URI", "nUri"):
            if isinstance(obj, dict) and key in obj:
                try:
                    uri = int(obj[key])
                except (TypeError, ValueError):
                    uri = None
                break
        if uri is None:
            stats.unparsed += 1
            return
        record_push(
            source="json",
            ws_url=ws_url,
            cmd_type=None,
            cmd_name="json",
            uri=uri,
            payload=text.encode("utf-8", errors="replace"),
            raw=text.encode("utf-8", errors="replace"),
            extra={"payload_encoding": "json", "raw_payload": obj},
        )

    def discover(page) -> None:
        nonlocal mapping_reported, last_discover
        last_discover = time.monotonic()
        try:
            info = page.evaluate(DISCOVER_JS)
        except Exception:
            return
        if not isinstance(info, dict):
            return
        globals_found = info.get("globals") or []
        if globals_found and globals_found != stats.page_globals:
            stats.page_globals = list(globals_found)
            logger.write_channel(
                {
                    "kind": "page_globals",
                    "received_at": now_iso(),
                    "globals": stats.page_globals,
                    "href": info.get("href"),
                }
            )
            if verbose:
                safe_print(f"[page] globals: {', '.join(stats.page_globals[:20])}")
        mapping = info.get("tafmx_uris")
        if mapping and not mapping_reported:
            mapping_reported = True
            stats.page_mapping = {str(k): v for k, v in mapping.items()}
            logger.write_channel(
                {
                    "kind": "page_uri_mapping",
                    "received_at": now_iso(),
                    "tafmx_uris": stats.page_mapping,
                    "huya_struct_names": info.get("huya_struct_names") or [],
                    "href": info.get("href"),
                }
            )
            safe_print(f"[page] TafMx.UriMapping 出现，共 {len(stats.page_mapping)} 项")
            _print_mapping_vs_candidates(stats.page_mapping)

    def print_progress() -> None:
        cand = " ".join(f"{item.uri}={stats.by_uri.get(item.uri, 0)}" for item in CANDIDATES)
        extras = [
            f"{uri}={count}"
            for uri, count in stats.by_uri.most_common(8)
            if lookup(uri) is None
        ]
        extra_text = (" | 其他 " + " ".join(extras)) if extras else ""
        missing = [str(item.uri) for item in CANDIDATES if stats.by_uri.get(item.uri, 0) == 0]
        safe_print(
            f"[capture] frames={stats.frames} push={stats.push} "
            f"uri={stats.uri_ok} | {cand}{extra_text}"
        )
        if missing:
            safe_print(f"[capture] 候选尚未出现: {', '.join(missing)}")

    try:
        try:
            context.expose_function("__huyaUriReport", on_js_report)
        except Exception as exc:
            safe_print(f"[capture] 页面回调挂接失败: {exc}")
        context.add_init_script(HOOK_JS)

        def attach_page(page) -> None:
            ident = id(page)
            if ident in hooked_pages:
                return
            hooked_pages.add(ident)
            page.on("websocket", on_websocket)

        context.on("page", attach_page)
        page = get_or_new_page(context)
        attach_page(page)

        status, detail = check_login_status(context, page)
        if status is False:
            safe_print(f"[capture] 登录状态无效（{detail}），请先运行 login 模式")
            return
        if status is None:
            safe_print(f"[capture] {detail}，继续执行，请人工留意浏览器窗口")

        logger.write_channel(
            {
                "kind": "session_start",
                "received_at": now_iso(),
                "login_status": status,
                "login_detail": detail,
            }
        )
        page = open_room(context, room_url, config)
        attach_page(page)
        try:
            page.evaluate(HOOK_JS)
        except Exception:
            pass
        safe_print(f"[capture] 已挂接页面事件通道，原始日志: {logger.raw_path}")
        safe_print("[capture] 同时解析 MsgPush / MsgPushV2，并挂接页面 Taf 分发。")
        safe_print("[capture] 按 Ctrl+C 结束并打印汇总")
        discover(page)

        while True:
            try:
                page.wait_for_timeout(1000)
            except Exception as exc:
                safe_print(f"[capture] 页面不可用: {exc}")
                break
            now = time.monotonic()
            if now - last_discover >= DISCOVER_INTERVAL_SECONDS and not mapping_reported:
                discover(page)
            if now - last_progress >= PROGRESS_INTERVAL_SECONDS:
                last_progress = now
                print_progress()
    except KeyboardInterrupt:
        safe_print("\n[capture] 收到中断，正在退出...")
    except Exception as exc:
        safe_print(f"[capture] 发生异常: {exc}")
        logger.write_channel({"kind": "error", "received_at": now_iso(), "error": str(exc)})
    finally:
        try:
            logger.write_channel(
                {
                    "kind": "session_end",
                    "received_at": now_iso(),
                    "frames": stats.frames,
                    "push": stats.push,
                    "uri_ok": stats.uri_ok,
                    "unparsed": stats.unparsed,
                    "by_uri": {str(k): v for k, v in stats.by_uri.items()},
                    "by_cmd": dict(stats.by_cmd),
                }
            )
            logger.close()
        except Exception:
            pass
        safe_print(f"[capture] WebSocket 打开 {stats.ws_open} / 关闭 {stats.ws_close}，原始日志 {logger.raw_path}")
        try:
            summary = analyze_raw_path(logger.raw_path)
            print_summary(summary)
            safe_print(f"分析已写入: {summary['meta'].get('summary_path')}")
        except Exception as exc:
            safe_print(f"[capture] 写分析失败: {exc}")
        try:
            context.close()
            pw.stop()
        except Exception:
            pass


def _print_mapping_vs_candidates(mapping: dict[str, str | None]) -> None:
    safe_print("[page] 与 Event.png 候选对照:")
    for item in CANDIDATES:
        live_name = mapping.get(str(item.uri))
        expected = item.struct_name or "(图中未给结构名)"
        if str(item.uri) not in mapping:
            safe_print(f"    {item.uri}: 页面映射中没有该项  候选={expected}")
        elif live_name == item.struct_name or (item.struct_name is None and live_name):
            shown = live_name or "(无函数名)"
            safe_print(f"    {item.uri}: 页面={shown}  候选={expected}")
        else:
            safe_print(
                f"    {item.uri}: 页面={live_name or '(无函数名)'}  候选={expected}  ← 不一致，以页面为准"
            )



