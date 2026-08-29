"""接入虎牙网页自身的 TAF 业务订阅，包括 1400 弹幕消息。

部分直播间的消息连接由网页 SDK/Worker 持有，Playwright 的 page websocket
事件看不到这些帧。网页组件本身通过 TTP.addTafListener 收消息；这里在同一
官方通道旁挂只读监听，再把贵族、进场、礼物、守护和超粉事件转成场控领域事件。
"""

from __future__ import annotations

import time
from typing import Any, Callable

from huya_ck.log import get_logger
from huya_ck.platform.bus import emit
from huya_ck.platform.channel import channel_state
from huya_ck.platform.chat_state import chat_state
from huya_ck.platform.taf_decoration import consume_badge_level

log = get_logger()

_BRIDGE_IDENT = -1
_CONSUME_BADGE_APP_ID = 11200
_NOBLE_NAMES = {1: "剑士", 2: "骑士", 3: "领主", 4: "公爵", 5: "君王", 6: "帝皇"}
_NOBLE_LEVELS = {name: level for level, name in _NOBLE_NAMES.items()}


OFFICIAL_TAF_BRIDGE_SCRIPT = r"""
(() => {
  const status = (value) => {
    try { window.__huya_ck_taf_status(value); } catch (_) {}
  };
  const integerText = (value) => {
    if (value === undefined || value === null) return null;
    try { return String(value); } catch (_) { return null; }
  };
  const vectorItems = (value) => {
    if (!value) return [];
    if (Array.isArray(value)) return value;
    if (Array.isArray(value.value)) return value.value;
    return [];
  };
  const byteList = (value) => {
    if (!value) return [];
    try {
      const source = value.buffer !== undefined ? value.buffer : value;
      if (source instanceof ArrayBuffer) return Array.from(new Uint8Array(source));
      if (ArrayBuffer.isView(source)) {
        return Array.from(new Uint8Array(source.buffer, source.byteOffset, source.byteLength));
      }
      if (Array.isArray(source)) return source;
    } catch (_) {}
    return [];
  };
  const text = (value) => value === undefined || value === null ? "" : String(value);
  const fieldKeys = (event) => {
    const result = [];
    const visit = (value, prefix, depth) => {
      if (!value || typeof value !== "object" || depth > 2) return;
      let keys = [];
      try { keys = Object.keys(value).slice(0, 80); } catch (_) { return; }
      for (const key of keys) {
        const path = prefix ? `${prefix}.${key}` : key;
        result.push(path);
        try { visit(value[key], path, depth + 1); } catch (_) {}
        if (result.length >= 160) return;
      }
    };
    visit(event, "", 0);
    return result;
  };
  const deepFirst = (root, names) => {
    let found = null;
    const seen = new WeakSet();
    const visit = (value, depth) => {
      if (found !== null || !value || typeof value !== "object" || depth > 5) return;
      if (seen.has(value)) return;
      seen.add(value);
      let keys = [];
      try { keys = Object.keys(value).slice(0, 120); } catch (_) { return; }
      for (const name of names) {
        if (!keys.includes(name)) continue;
        try {
          const candidate = value[name];
          if (candidate !== undefined && candidate !== null && candidate !== "") {
            found = candidate;
            return;
          }
        } catch (_) {}
      }
      for (const key of keys) {
        try { visit(value[key], depth + 1); } catch (_) {}
        if (found !== null) return;
      }
    };
    visit(root, 0);
    return found;
  };
  const textValues = (root) => {
    const result = [];
    const seen = new WeakSet();
    const visit = (value, depth) => {
      if (result.length >= 120 || value === undefined || value === null || depth > 6) return;
      if (typeof value === "string") {
        const clean = value.trim();
        if (clean) result.push(clean);
        return;
      }
      if (typeof value !== "object" || seen.has(value)) return;
      seen.add(value);
      let keys = [];
      try { keys = Object.keys(value).slice(0, 120); } catch (_) { return; }
      for (const key of keys) {
        try { visit(value[key], depth + 1); } catch (_) {}
        if (result.length >= 120) return;
      }
    };
    visit(root, 0);
    return result;
  };
  const forwardEnter = (event) => {
    try {
      const noble = event && event.tNobleInfo ? event.tNobleInfo : {};
      const guard = event && event.tGuardInfo ? event.tGuardInfo : {};
      const decoration = event && event.tDecorationInfo ? event.tDecorationInfo : {};
      const prefixes = vectorItems(decoration.vDecorationPrefix).map((item) => ({
        app_id: item ? item.iAppId : null,
        data: byteList(item ? item.vData : null),
      }));
      window.__huya_ck_on_6110({
        uid: integerText(event ? event.lUid : null),
        nick: event && event.sNickName ? String(event.sNickName) : "",
        room_uid: integerText(event ? event.lPid : null),
        noble_name: noble.sNobleName ? String(noble.sNobleName) : "",
        noble_level: integerText(noble.iNobleLevel),
        guard_uid: integerText(guard.lUid),
        guard_level: integerText(guard.iGuardLevel),
        guard_text: String(guard.sEnterText || guard.sNewAttr || guard.sAttr || ""),
        decoration_prefix: prefixes,
      });
    } catch (error) {
      status(`event-error:${error && error.message ? error.message : String(error)}`);
    }
  };
  const forwardGift = (event) => {
    try {
      window.__huya_ck_on_6501({
        item_id: integerText(event ? event.iItemType : null),
        order_id: event && event.strPayId ? String(event.strPayId) : "",
        count: integerText(event ? event.iItemCount : null),
        value_fen: integerText(event ? event.lPayTotal : null),
        sender_uid: integerText(event ? event.lSenderUid : null),
        sender_nick: event && event.sSenderNick ? String(event.sSenderNick) : "",
        anchor_nick: event && event.sPresenterNick ? String(event.sPresenterNick) : "",
        item_name: event && event.sPropsName ? String(event.sPropsName) : "",
        room_id: integerText(event ? event.lRoomId : null),
      });
    } catch (error) {
      status(`gift-event-error:${error && error.message ? error.message : String(error)}`);
    }
  };
  const forwardGuard = (event) => {
    try {
      const values = textValues(event);
      const knownBanner = text(deepFirst(event, [
        "sBannerText", "sContent", "sNotice", "sDisplayInfo", "bannerText", "content"
      ])).trim();
      const isGuardBanner = (value) =>
        /(初爱守护|超级守护|至尊守护)/.test(value) &&
        /(开通|升级|荣升)/.test(value);
      const bannerText = (isGuardBanner(knownBanner) ? knownBanner : "") ||
        values.find((value) => isGuardBanner(value)) || "";
      const bannerIndex = values.indexOf(bannerText);
      const precedingNick = bannerIndex > 0 ? values[bannerIndex - 1] : "";
      const knownNick = text(deepFirst(event, [
        "sNickName", "sUserNick", "sSenderNick", "userNick", "nick"
      ])).trim();
      const nick = knownNick || (
        precedingNick &&
        !/^https?:\/\//i.test(precedingNick) &&
        !isGuardBanner(precedingNick) &&
        precedingNick.length <= 80
          ? precedingNick
          : ""
      );
      window.__huya_ck_on_6540({
        uid: integerText(deepFirst(event, ["lUid", "lUserId", "lSenderUid", "uid", "userId"])),
        union_id: text(deepFirst(event, ["unionId", "sUnionId"])),
        nick,
        room_id: integerText(deepFirst(event, ["lPid", "lRoomId", "roomId"])),
        anchor_nick: text(deepFirst(event, ["sPresenterNick", "presenterNick"])),
        banner_text: bannerText,
        text_values: values,
        field_keys: fieldKeys(event),
      });
    } catch (error) {
      status(`guard-event-error:${error && error.message ? error.message : String(error)}`);
    }
  };
  const forwardNoble = (event) => {
    try {
      const values = textValues(event);
      const nobleNames = ["\u5251\u58eb", "\u9a91\u58eb", "\u9886\u4e3b", "\u516c\u7235", "\u541b\u738b", "\u5e1d\u7687"];
      const knownNobleName = text(deepFirst(event, ["sNobleName", "nobleName"])).trim();
      const nobleName = knownNobleName || values.find((value) => nobleNames.includes(value)) || "";
      const knownNick = text(deepFirst(event, [
        "sNickName", "sUserNick", "userNick", "nick"
      ])).trim();
      const nick = knownNick || values.find((value) =>
        value !== nobleName &&
        !nobleNames.includes(value) &&
        !/^https?:\/\//i.test(value) &&
        value.length <= 80
      ) || "";
      window.__huya_ck_on_1001({
        uid: integerText(deepFirst(event, ["lUid", "lUserId", "uid", "userId"])),
        nick,
        noble_name: nobleName,
        noble_level: integerText(deepFirst(event, ["iNobleLevel", "nobleLevel", "iLevel"])),
        room_id: integerText(deepFirst(event, ["lPid", "lRoomId", "roomId"])),
        anchor_nick: text(deepFirst(event, ["sPresenterNick", "presenterNick"])),
        open_flag: integerText(deepFirst(event, ["iOpenFlag", "openFlag", "iOpenType", "openType"])),
        pay_month: integerText(deepFirst(event, ["iPayMonth", "payMonth", "iMonths", "months"])),
        open_days: integerText(deepFirst(event, ["iOpenDays", "openDays"])),
        event_time_ms: String(Date.now()),
        event_seq: String(window.__huya_ck_noble_seq = (window.__huya_ck_noble_seq || 0) + 1),
        field_keys: fieldKeys(event),
      });
    } catch (error) {
      status(`noble-event-error:${error && error.message ? error.message : String(error)}`);
    }
  };
  const forwardSuperFan = (event) => {
    try {
      const values = textValues(event);
      const knownBanner = text(deepFirst(event, [
        "sBannerText", "sContent", "sNotice", "sDisplayInfo", "bannerText", "content"
      ])).trim();
      const actionText = (
        /\u8d85\u7c89/i.test(knownBanner) && /(\u5f00\u901a|\u7eed\u8d39)/.test(knownBanner)
          ? knownBanner
          : ""
      ) || values.find((value) =>
        /\u8d85\u7c89/i.test(value) && /(\u5f00\u901a|\u7eed\u8d39)/.test(value)
      ) || "";
      const knownNick = text(deepFirst(event, [
        "sNickName", "sUserNick", "sSenderNick", "userNick", "nick"
      ])).trim();
      const nick = knownNick || values.find((value) =>
        value !== actionText &&
        !/^#[0-9a-f]{6,8}$/i.test(value) &&
        !/^https?:\/\//i.test(value) &&
        !/\u8d85\u7c89/i.test(value) &&
        value.length <= 80
      ) || "";
      window.__huya_ck_on_10079({
        nick,
        action_text: actionText,
        text_values: values,
        room_id: integerText(deepFirst(event, ["lPid", "lRoomId", "roomId"])),
        event_time_ms: String(Date.now()),
        event_seq: String(window.__huya_ck_superfan_seq = (window.__huya_ck_superfan_seq || 0) + 1),
        field_keys: fieldKeys(event),
      });
    } catch (error) {
      status(`superfan-event-error:${error && error.message ? error.message : String(error)}`);
    }
  };
  const forwardSuperFanPlus = (event) => {
    try {
      const values = textValues(event);
      const marker = values.find((value) => /\u8d85\u7c89plus/i.test(value)) || "";
      if (!marker) return;
      const knownNick = text(deepFirst(event, [
        "sNickName", "sUserNick", "sSenderNick", "userNick", "nick"
      ])).trim();
      const nick = knownNick || values.find((value) =>
        !/^\s*(adr|ios|pc|web):/i.test(value) &&
        !/^#[0-9a-f]{6,8}$/i.test(value) &&
        !/^https?:\/\//i.test(value) &&
        !/\u8d85\u7c89plus/i.test(value) &&
        !/\u4e3a.+(\u5f00\u901a|\u7eed\u8d39)\u4e86/.test(value) &&
        !/barrage_name/i.test(value) &&
        value.length <= 80
      ) || "";
      window.__huya_ck_on_10079({
        uri: "2001231",
        nick,
        action_text: marker,
        text_values: values,
        room_id: integerText(deepFirst(event, ["lPid", "lRoomId", "roomId"])),
        event_time_ms: String(Date.now()),
        event_seq: String(window.__huya_ck_superfan_seq = (window.__huya_ck_superfan_seq || 0) + 1),
        field_keys: fieldKeys(event),
      });
    } catch (error) {
      status(`superfan-plus-event-error:${error && error.message ? error.message : String(error)}`);
    }
  };
  const forwardChat = (event) => {
    try {
      window.__huya_ck_on_1400({
        uid: integerText(deepFirst(event, [
          "lSenderUid", "lUid", "lUserId", "senderUid", "uid", "userId"
        ])),
        nick: text(deepFirst(event, [
          "sSenderNick", "sNickName", "sUserNick", "sendNick", "senderNick", "nick"
        ])).trim(),
        content: text(deepFirst(event, [
          "sContent", "sMessage", "sMsg", "content", "message"
        ])).trim(),
        room_id: integerText(deepFirst(event, ["lRoomId", "lPid", "roomId"])),
        show_mode: integerText(deepFirst(event, ["iShowMode", "showMode"])),
        message_id: integerText(deepFirst(event, ["lMsgId", "sMsgId", "messageId", "msgId"])),
        event_time_ms: String(Date.now()),
        event_seq: String(window.__huya_ck_chat_seq = (window.__huya_ck_chat_seq || 0) + 1),
        field_keys: fieldKeys(event),
      });
    } catch (error) {
      status(`chat-event-error:${error && error.message ? error.message : String(error)}`);
    }
  };
  const install = () => {
    if (window.__huya_ck_taf_business_attached) return true;
    if (!window.TTP || typeof window.TTP.ready !== "function") return false;
    window.__huya_ck_taf_business_attached = true;
    try {
      window.TTP.ready((signal) => {
        try {
          signal.addTafListener("6110", forwardEnter);
          signal.addTafListener("6501", forwardGift);
          signal.addTafListener("6540", forwardGuard);
          signal.addTafListener("1001", forwardNoble);
          signal.addTafListener("1400", forwardChat);
          try {
            signal.addTafListener("10079", forwardSuperFan);
            signal.addTafListener("2001231", forwardSuperFanPlus);
          } catch (error) {
            status(`10079-listener-error:${error && error.message ? error.message : String(error)}`);
          }
          status("attached");
          window.setInterval(() => status("heartbeat"), 30000);
        } catch (error) {
          window.__huya_ck_taf_business_attached = false;
          status(`attach-error:${error && error.message ? error.message : String(error)}`);
        }
      });
      return true;
    } catch (error) {
      window.__huya_ck_taf_business_attached = false;
      status(`ready-error:${error && error.message ? error.message : String(error)}`);
      return false;
    }
  };
  if (install()) return;
  const timer = window.setInterval(() => {
    if (install()) window.clearInterval(timer);
  }, 250);
})();
"""


def _integer(value: Any, default: int | None = None) -> int | None:
    if value is None or isinstance(value, bool):
        return default
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def _consume_level(prefixes: Any) -> int | None:
    if not isinstance(prefixes, list):
        return None
    for item in prefixes:
        if not isinstance(item, dict) or _integer(item.get("app_id")) != _CONSUME_BADGE_APP_ID:
            continue
        raw = item.get("data")
        if not isinstance(raw, list):
            continue
        try:
            data = bytes(value for value in raw if isinstance(value, int) and 0 <= value <= 255)
            return consume_badge_level(data)
        except (TypeError, ValueError):
            continue
    return None


def normalize_official_6110(payload: Any) -> dict | None:
    if not isinstance(payload, dict):
        return None
    uid = _integer(payload.get("uid"))
    nick = str(payload.get("nick") or "").strip()
    if uid is None or not nick:
        return None
    noble_level = _integer(payload.get("noble_level"))
    noble_name = str(payload.get("noble_name") or "").strip() or _NOBLE_NAMES.get(noble_level or 0, "")
    guard_uid = _integer(payload.get("guard_uid"), 0) or 0
    guard_text = str(payload.get("guard_text") or "")
    return {
        "type": "enter",
        "uri": 6110,
        "uid": uid,
        "nick": nick,
        "room_uid": _integer(payload.get("room_uid")),
        "noble_name": noble_name,
        "noble_level": noble_level,
        "consume_level": _consume_level(payload.get("decoration_prefix")),
        "has_guard": bool(guard_text) or guard_uid != 0,
        "guard_text": guard_text,
        "guard_level": _integer(payload.get("guard_level"), 0) or 0,
        "group": "official-taf",
    }


def normalize_official_6501(payload: Any) -> dict | None:
    if not isinstance(payload, dict):
        return None
    item_name = str(payload.get("item_name") or "").strip()
    sender_nick = str(payload.get("sender_nick") or "").strip()
    if not item_name and not sender_nick:
        return None
    value_fen = _integer(payload.get("value_fen"), 0) or 0
    count = _integer(payload.get("count"), 1) or 1
    return {
        "type": "gift",
        "uri": 6501,
        "item_id": _integer(payload.get("item_id")),
        "item_name": item_name,
        "count": count,
        "value_fen": value_fen,
        "value_yuan": value_fen / 100,
        "sender_uid": _integer(payload.get("sender_uid")),
        "sender_nick": sender_nick,
        "anchor_nick": str(payload.get("anchor_nick") or ""),
        "room_id": _integer(payload.get("room_id")),
        "order_id": str(payload.get("order_id") or ""),
        "group": "official-taf",
    }


def normalize_official_6540(payload: Any) -> dict | None:
    """把 6540 TAF 横幅转为守护开通/升级事件；不按 URI 猜测业务。"""
    if not isinstance(payload, dict):
        return None
    nick = str(payload.get("nick") or "").strip()
    uid = _integer(payload.get("uid"))
    union_id = str(payload.get("union_id") or "").strip()
    banner_text = str(payload.get("banner_text") or "").strip()
    guard_name = next(
        (name for name in ("至尊守护", "超级守护", "初爱守护") if name in banner_text),
        "",
    )
    if "升级" in banner_text or "荣升" in banner_text:
        action = "升级"
    elif "开通" in banner_text:
        action = "开通"
    else:
        action = ""
    if not nick or (uid is None and not union_id) or not guard_name or not action:
        return None
    return {
        "type": "guard_open",
        "uri": 6540,
        "uid": uid,
        "union_id": union_id,
        "nick": nick,
        "room_id": _integer(payload.get("room_id")),
        "anchor_nick": str(payload.get("anchor_nick") or "").strip(),
        "banner_text": banner_text,
        "action": action,
        "guard_name": guard_name,
        "group": "official-taf",
    }


def normalize_official_1001(payload: Any) -> dict | None:
    """把 1001 贵族开通、升级或续费通知转成领域事件。"""
    if not isinstance(payload, dict):
        return None
    nick = str(payload.get("nick") or "").strip()
    noble_name = str(payload.get("noble_name") or "").strip()
    noble_level = _integer(payload.get("noble_level")) or _NOBLE_LEVELS.get(noble_name)
    if not noble_name and noble_level is not None:
        noble_name = _NOBLE_NAMES.get(noble_level, "")
    open_flag = _integer(payload.get("open_flag"))
    if not nick or not noble_name or open_flag not in {1, 2}:
        return None
    pay_month = _integer(payload.get("pay_month"))
    open_days = _integer(payload.get("open_days"))
    if not pay_month and open_days and open_days > 0 and open_days % 30 == 0:
        pay_month = open_days // 30
    months = pay_month if pay_month and pay_month > 0 else 1
    action = "开通/升级" if open_flag == 1 else "续费"
    event_time_ms = _integer(payload.get("event_time_ms"))
    event_seq = _integer(payload.get("event_seq"))
    event = {
        "type": "noble_open",
        "uri": 1001,
        "uid": _integer(payload.get("uid")),
        "nick": nick,
        "room_id": _integer(payload.get("room_id")),
        "anchor_nick": str(payload.get("anchor_nick") or "").strip(),
        "noble_name": noble_name,
        "noble_level": noble_level,
        "open_flag": open_flag,
        "action": action,
        "months": months,
        "open_days": open_days,
        "banner_text": f"{action}{noble_name}{months}个月",
        "group": "official-taf",
    }
    if event_time_ms is not None:
        event["event_id"] = f"1001:{event_time_ms}:{event_seq or 0}:{nick}"
    return event


def normalize_official_10079(payload: Any) -> dict | None:
    """把 10079/2001231 超粉通知转成统一“开通”感谢事件。"""
    if not isinstance(payload, dict):
        return None
    values = payload.get("text_values")
    texts = [str(value).strip() for value in values if str(value).strip()] if isinstance(values, list) else []
    banner = str(payload.get("action_text") or "").strip()
    if not banner:
        banner = next((value for value in texts if "超粉" in value and ("开通" in value or "续费" in value)), "")
    nick = str(payload.get("nick") or "").strip()
    if not nick or "超粉" not in banner:
        return None
    if "开通" not in banner and "续费" not in banner:
        return None
    action = "开通"
    all_text = " ".join([banner, *texts])
    superfan_name = "超粉PLUS" if "plus" in all_text.lower() else "超粉"
    source_uri = _integer(payload.get("uri"), 10079) or 10079
    if source_uri == 2001231 and "plus" not in all_text.lower():
        return None
    event_time_ms = _integer(payload.get("event_time_ms"))
    event_seq = _integer(payload.get("event_seq"))
    event = {
        "type": "superfan_open",
        "uri": source_uri,
        "nick": nick,
        "room_id": _integer(payload.get("room_id")),
        "action": action,
        "superfan_name": superfan_name,
        "banner_text": banner,
        "group": "official-taf",
    }
    if event_time_ms is not None:
        event["event_id"] = f"{source_uri}:{event_time_ms}:{event_seq or 0}:{nick}"
    return event


def normalize_official_1400(payload: Any) -> dict | None:
    """只接受带有效 UID、昵称和正文的用户弹幕，不把系统通知当成指令。"""
    if not isinstance(payload, dict):
        return None
    uid = _integer(payload.get("uid"))
    nick = str(payload.get("nick") or "").strip()
    content = str(payload.get("content") or "").strip()
    if uid is None or uid <= 0 or not nick or not content:
        return None
    if nick in {"系统消息", "虎牙系统", "虎牙直播"}:
        return None
    event_time_ms = _integer(payload.get("event_time_ms"))
    event_seq = _integer(payload.get("event_seq"))
    message_id = str(payload.get("message_id") or "").strip()
    event = {
        "type": "chat_message",
        "uri": 1400,
        "uid": uid,
        "nick": nick,
        "content": content,
        "room_id": _integer(payload.get("room_id")),
        "show_mode": _integer(payload.get("show_mode")),
        "message_id": message_id,
        "group": "official-taf",
    }
    if message_id:
        event["event_id"] = f"1400:{message_id}:{uid}"
    elif event_time_ms is not None:
        event["event_id"] = f"1400:{event_time_ms}:{event_seq or 0}:{uid}"
    return event


def attach_official_taf(page: Any, on_event: Callable[[dict], None] | None = None) -> None:
    """导航前调用；init script 会在直播间页面等待 TTP 就绪并订阅。"""
    if getattr(page, "_huya_ck_official_taf", False):
        return
    page._huya_ck_official_taf = True
    callback = on_event or emit
    attached_logged = False
    last_chat_diagnostic = 0.0
    target_room_uids: set[int] = set()

    def remember_target_room(value: Any) -> None:
        room_uid = _integer(value)
        if room_uid is not None and room_uid > 0:
            target_room_uids.add(room_uid)

    def on_status(status: Any) -> None:
        nonlocal attached_logged
        value = str(status or "")
        if value in {"attached", "heartbeat"}:
            channel_state.mark_connected(_BRIDGE_IDENT)
            channel_state.mark_activity()
            chat_state.mark_attached()
            if value == "attached" and not attached_logged:
                attached_logged = True
                log.info("官方 TAF 业务通道已接入（1400 弹幕及自动场控事件）")
            return
        log.info("官方 1400/1001/6110/6501/6540/10079/2001231 通道异常：%s", value or "未知")

    def on_6110(payload: Any) -> None:
        channel_state.mark_connected(_BRIDGE_IDENT)
        channel_state.mark_activity()
        event = normalize_official_6110(payload)
        if event is None:
            log.info("官方 6110 收到一条进场，但关键字段无法解析：%r", payload)
            return
        remember_target_room(event.get("room_uid"))
        log.info(
            "官方通道收到贵族进场 6110（昵称=%s，贵族=%s，消费=%s，守护=%s，uid=%s）",
            event["nick"],
            event.get("noble_name") or "未知",
            event.get("consume_level") if event.get("consume_level") is not None else "未知",
            "是" if event.get("has_guard") else "否",
            event["uid"],
        )
        callback(event)

    def on_6501(payload: Any) -> None:
        channel_state.mark_connected(_BRIDGE_IDENT)
        channel_state.mark_activity()
        event = normalize_official_6501(payload)
        if event is None:
            log.info("官方 6501 收到一条礼物，但关键字段无法解析：%r", payload)
            return
        remember_target_room(event.get("room_id"))
        log.info(
            "官方通道收到礼物 6501（用户=%s，礼物=%s，数量=%s，金额=%s分，订单=%s）",
            event.get("sender_nick") or "未知",
            event.get("item_name") or "未知",
            event["count"],
            event["value_fen"],
            event.get("order_id") or "未知",
        )
        callback(event)

    def on_6540(payload: Any) -> None:
        channel_state.mark_connected(_BRIDGE_IDENT)
        channel_state.mark_activity()
        event = normalize_official_6540(payload)
        if event is None:
            keys = payload.get("field_keys", []) if isinstance(payload, dict) else []
            texts = payload.get("text_values", []) if isinstance(payload, dict) else []
            log.info(
                "官方 6540 收到候选事件，但未识别为守护开通/升级（文本=%s，字段=%s）",
                " | ".join(map(str, texts)) or "未知",
                ",".join(map(str, keys)) or "未知",
            )
            return
        remember_target_room(event.get("room_id"))
        log.info(
            "官方通道收到守护 6540（用户=%s，动作=%s，守护=%s，文本=%s）",
            event["nick"],
            event["action"],
            event["guard_name"],
            event["banner_text"],
        )
        callback(event)

    def on_1400(payload: Any) -> None:
        nonlocal last_chat_diagnostic
        channel_state.mark_connected(_BRIDGE_IDENT)
        channel_state.mark_activity()
        chat_state.mark_attached()
        event = normalize_official_1400(payload)
        if event is None:
            now = time.monotonic()
            if now - last_chat_diagnostic >= 60:
                last_chat_diagnostic = now
                keys = payload.get("field_keys", []) if isinstance(payload, dict) else []
                log.info(
                    "官方 1400 暂无法识别用户弹幕（仅记录字段名=%s）",
                    ",".join(map(str, keys)) or "未知",
                )
            return
        is_outbound = chat_state.is_recent_outbound(event["content"])
        authorization = chat_state.observe(event, is_outbound=is_outbound)
        if authorization is None:
            return
        log.info(
            "识别授权弹幕 1400（用户=%s，uid=%s，身份=%s）",
            event["nick"],
            event["uid"],
            authorization["role"],
        )
        callback(event)

    def on_1001(payload: Any) -> None:
        channel_state.mark_connected(_BRIDGE_IDENT)
        channel_state.mark_activity()
        event = normalize_official_1001(payload)
        if event is None:
            keys = payload.get("field_keys", []) if isinstance(payload, dict) else []
            log.info(
                "官方 1001 收到贵族候选事件，但关键字段无法解析（用户=%s，贵族=%s，开通标志=%s，月份=%s，字段=%s）",
                payload.get("nick") if isinstance(payload, dict) else "未知",
                payload.get("noble_name") if isinstance(payload, dict) else "未知",
                payload.get("open_flag") if isinstance(payload, dict) else "未知",
                payload.get("pay_month") if isinstance(payload, dict) else "未知",
                ",".join(map(str, keys)) or "未知",
            )
            return
        event_room_id = event.get("room_id")
        if not target_room_uids:
            log.info(
                "官方 1001 暂不处理（尚未从本房进场/礼物等事件确认主播 UID，候选用户=%s，主播UID=%s）",
                event["nick"],
                event_room_id if event_room_id is not None else "未知",
            )
            return
        if event_room_id not in target_room_uids:
            log.info(
                "官方 1001 忽略其他直播间贵族事件（用户=%s，主播UID=%s，本房UID=%s）",
                event["nick"],
                event_room_id if event_room_id is not None else "未知",
                ",".join(map(str, sorted(target_room_uids))),
            )
            return
        log.info(
            "官方通道收到贵族 1001（用户=%s，动作=%s，贵族=%s，月份=%s，主播=%s）",
            event["nick"],
            event["action"],
            event["noble_name"],
            event["months"],
            event.get("anchor_nick") or "未知",
        )
        callback(event)

    def on_10079(payload: Any) -> None:
        channel_state.mark_connected(_BRIDGE_IDENT)
        channel_state.mark_activity()
        event = normalize_official_10079(payload)
        if event is None:
            keys = payload.get("field_keys", []) if isinstance(payload, dict) else []
            texts = payload.get("text_values", []) if isinstance(payload, dict) else []
            log.info(
                "官方 %s 收到超粉候选事件，但关键字段无法解析（文本=%s，字段=%s）",
                payload.get("uri", 10079) if isinstance(payload, dict) else 10079,
                " | ".join(map(str, texts)) or "未知",
                ",".join(map(str, keys)) or "未知",
            )
            return
        remember_target_room(event.get("room_id"))
        log.info(
            "官方通道收到超粉 %s（用户=%s，动作=%s，类型=%s，文本=%s）",
            event["uri"],
            event["nick"],
            event["action"],
            event["superfan_name"],
            event["banner_text"],
        )
        callback(event)

    page.expose_function("__huya_ck_on_6110", on_6110)
    page.expose_function("__huya_ck_on_6501", on_6501)
    page.expose_function("__huya_ck_on_6540", on_6540)
    page.expose_function("__huya_ck_on_1001", on_1001)
    page.expose_function("__huya_ck_on_10079", on_10079)
    page.expose_function("__huya_ck_on_1400", on_1400)
    page.expose_function("__huya_ck_taf_status", on_status)
    page.add_init_script(script=OFFICIAL_TAF_BRIDGE_SCRIPT)
    log.debug("诊断：已准备网页官方 1400 及自动场控事件监听，等待直播间 TTP 通道就绪")
