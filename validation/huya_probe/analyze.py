"""Offline analysis of captured URI JSONL."""

from __future__ import annotations

import base64
import json
from collections import Counter, defaultdict
from pathlib import Path

from .inspect import extract_preview
from .jce import JceError, parse_websocket_frames
from .uri_map import CANDIDATES, lookup


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def latest_raw(log_dir: str | Path) -> Path | None:
    folder = Path(log_dir)
    if not folder.exists():
        return None
    files = sorted(folder.glob("*-raw.jsonl"))
    return files[-1] if files else None


def _payload_bytes(row: dict) -> bytes:
    raw = row.get("raw_payload")
    encoding = row.get("payload_encoding") or "base64"
    if encoding == "json":
        return json.dumps(raw, ensure_ascii=False).encode("utf-8") if raw else b""
    if isinstance(raw, str) and encoding == "base64":
        try:
            return base64.b64decode(raw)
        except Exception:
            return b""
    return b""


def _envelope_bytes(row: dict) -> bytes:
    raw = row.get("raw_envelope")
    if isinstance(raw, str) and row.get("envelope_encoding") == "base64":
        try:
            return base64.b64decode(raw)
        except Exception:
            return b""
    return b""


def iter_events(rows: list[dict]) -> list[dict]:
    """Yield analysis events, re-parsing old MsgPushV2 rows that had uri=null."""
    events: list[dict] = []
    for row in rows:
        uri = row.get("uri")
        cmd = row.get("cmd_name")
        if uri is None and cmd == "MsgPushV2":
            envelope = _envelope_bytes(row)
            if envelope:
                try:
                    frames = parse_websocket_frames(envelope)
                except (JceError, Exception):
                    frames = []
                for frame in frames:
                    preview = extract_preview(frame.payload)
                    events.append(
                        {
                            "received_at": row.get("received_at"),
                            "uri": frame.uri,
                            "group": frame.group,
                            "source": "MsgPushV2",
                            "cmd_name": "MsgPushV2",
                            "payload_bytes": len(frame.payload),
                            "text_preview": preview["text_preview"],
                            "int_preview": preview["int_preview"],
                        }
                    )
                continue
        payload = _payload_bytes(row)
        preview = extract_preview(payload)
        events.append(
            {
                "received_at": row.get("received_at"),
                "uri": uri,
                "group": row.get("group"),
                "source": row.get("source") or cmd,
                "cmd_name": cmd,
                "payload_bytes": row.get("payload_bytes") or len(payload),
                "text_preview": row.get("text_preview") or preview["text_preview"],
                "int_preview": row.get("int_preview") or preview["int_preview"],
            }
        )
    return events


def build_summary(events: list[dict], run_meta: dict | None = None) -> dict:
    counts: Counter[int | None] = Counter()
    groups: Counter[str] = Counter()
    sources: Counter[str] = Counter()
    samples: dict[int, list[dict]] = defaultdict(list)
    for event in events:
        uri = event.get("uri")
        counts[uri] += 1
        if event.get("group"):
            family = str(event["group"]).split(":")[0]
            groups[family] += 1
        sources[str(event.get("source") or "")] += 1
        if isinstance(uri, int) and len(samples[uri]) < 8:
            samples[uri].append(
                {
                    "received_at": event.get("received_at"),
                    "text_preview": event.get("text_preview") or [],
                    "int_preview": (event.get("int_preview") or [])[:6],
                    "group": event.get("group"),
                    "source": event.get("source"),
                }
            )

    candidate_block = []
    for item in CANDIDATES:
        candidate_block.append(
            {
                "uri": item.uri,
                "struct_name": item.struct_name,
                "meaning": item.meaning,
                "count": counts.get(item.uri, 0),
                "samples": samples.get(item.uri, []),
            }
        )
    other = []
    for uri, count in counts.most_common():
        if uri is None or lookup(uri):
            continue
        other.append(
            {
                "uri": uri,
                "count": count,
                "samples": samples.get(uri, [])[:5],
            }
        )
    return {
        "meta": run_meta or {},
        "total_events": len(events),
        "uri_ok": sum(n for uri, n in counts.items() if uri is not None),
        "uri_none": counts.get(None, 0),
        "candidates": candidate_block,
        "other_uris": other[:40],
        "groups": dict(groups.most_common(30)),
        "sources": dict(sources),
    }


def print_summary(summary: dict) -> None:
    print("=" * 56)
    print("URI 采集分析")
    print("=" * 56)
    meta = summary.get("meta") or {}
    if meta:
        print(f"run={meta.get('run_id')} room={meta.get('room_id')} file={meta.get('raw_path')}")
    print(f"事件 {summary.get('total_events')}，解析到 URI {summary.get('uri_ok')}，无 URI {summary.get('uri_none')}")
    print()
    print("候选 URI:")
    for item in summary.get("candidates") or []:
        mark = "出现" if item["count"] else "未出现"
        name = item.get("struct_name") or "(结构名待确认)"
        print(f"  {item['uri']:>7}  {name:<28} {mark:4}  n={item['count']:<5} {item.get('meaning')}")
        for sample in item.get("samples") or []:
            texts = " | ".join(sample.get("text_preview") or [])
            if not texts and sample.get("int_preview"):
                texts = "ints=" + ",".join(str(x) for x in sample["int_preview"][:6])
            if texts:
                print(f"           {sample.get('received_at','')}  {texts[:120]}")
    print()
    print("其他高频 URI:")
    for item in (summary.get("other_uris") or [])[:15]:
        texts = ""
        if item.get("samples") and item["samples"][0].get("text_preview"):
            texts = " | ".join(item["samples"][0]["text_preview"])[:80]
        print(f"  {item['uri']:>7}  n={item['count']:<5}  {texts}")
    print("=" * 56)


def analyze_raw_path(raw_path: Path) -> dict:
    rows = load_jsonl(raw_path)
    meta = {}
    if rows:
        meta = {
            "run_id": rows[0].get("run_id"),
            "room_id": rows[0].get("room_id"),
            "room_url": rows[0].get("room_url"),
            "raw_path": str(raw_path),
        }
    events = iter_events(rows)
    summary = build_summary(events, meta)
    out = raw_path.with_name(raw_path.name.replace("-raw.jsonl", "-summary.json"))
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    summary["meta"]["summary_path"] = str(out)
    return summary


def run_analyze_mode(args) -> None:
    log_dir = getattr(args, "log_dir", "validation/event-captures")
    log_path = getattr(args, "log", None)
    if log_path:
        raw_path = Path(log_path)
    else:
        found = latest_raw(log_dir)
        if not found:
            print(f"[analyze] {log_dir} 下没有 *-raw.jsonl")
            return
        raw_path = found
    if not raw_path.exists():
        print(f"[analyze] 找不到文件: {raw_path}")
        return
    summary = analyze_raw_path(raw_path)
    print_summary(summary)
    print(f"分析已写入: {summary['meta'].get('summary_path')}")
