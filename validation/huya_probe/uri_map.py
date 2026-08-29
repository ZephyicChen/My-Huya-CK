"""Candidate URI map from Event.png.

This is a hypothesis to be confirmed against a live room session.
Do not treat struct names or event types as verified until capture
sees them on the page channel.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UriCandidate:
    uri: int
    struct_name: str | None
    event_type: str
    meaning: str
    struct_name_confirmed: bool = True


# Event.png lists 6111 as "(进场消息)" without a struct name.
# Product enter is 6110 only; field map is 贵族进场解析.md. 6111 stays in
# the capture table but must not be standardized as enter.
CANDIDATES: tuple[UriCandidate, ...] = (
    UriCandidate(1400, "MessageNotice", "chat", "弹幕"),
    UriCandidate(6110, "VipEnterBanner", "enter", "贵族进场横幅"),
    UriCandidate(6111, None, "enter", "普通用户进场", struct_name_confirmed=False),
    UriCandidate(1005, "NobleEnterNotice", "enter", "贵族进场通知"),
    UriCandidate(6200, "EnterPushInfo", "enter", "进场推送"),
    UriCandidate(6501, "SendItemSubBroadcastPacket", "gift", "礼物"),
    UriCandidate(6540, None, "guard_open", "守护开通横幅", struct_name_confirmed=False),
    UriCandidate(8006, "AttendeeCountNotice", "attendee_count", "人气值"),
)

CANDIDATE_BY_URI = {item.uri: item for item in CANDIDATES}


def lookup(uri: int | None) -> UriCandidate | None:
    if uri is None:
        return None
    return CANDIDATE_BY_URI.get(int(uri))
