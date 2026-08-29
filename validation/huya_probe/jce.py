"""Minimal TAF/JCE reader for Huya WebSocket envelopes.

Only the outer command and WSPushMessage.iUri are decoded. Inner
business structs (MessageNotice, etc.) are left untouched.
"""

from __future__ import annotations

from dataclasses import dataclass

EN_INT8 = 0
EN_INT16 = 1
EN_INT32 = 2
EN_INT64 = 3
EN_FLOAT = 4
EN_DOUBLE = 5
EN_STRING1 = 6
EN_STRING4 = 7
EN_MAP = 8
EN_LIST = 9
EN_STRUCTBEGIN = 10
EN_STRUCTEND = 11
EN_ZERO = 12
EN_SIMPLELIST = 13

CMD_REGISTER_REQ = 1
CMD_REGISTER_RSP = 2
CMD_WUP_REQ = 3
CMD_WUP_RSP = 4
CMD_HEARTBEAT = 5
CMD_HEARTBEAT_ACK = 6
CMD_MSG_PUSH = 7
CMD_REGISTER_GROUP_RSP = 17
CMD_MSG_PUSH_V2 = 22

CMD_NAMES = {
    CMD_REGISTER_REQ: "RegisterReq",
    CMD_REGISTER_RSP: "RegisterRsp",
    CMD_WUP_REQ: "WupReq",
    CMD_WUP_RSP: "WupRsp",
    CMD_HEARTBEAT: "HeartBeat",
    CMD_HEARTBEAT_ACK: "HeartBeatAck",
    CMD_MSG_PUSH: "MsgPush",
    CMD_REGISTER_GROUP_RSP: "RegisterGroupRsp",
    CMD_MSG_PUSH_V2: "MsgPushV2",
}


class JceError(ValueError):
    pass


class JceWriter:
    def __init__(self) -> None:
        self.buf = bytearray()

    def get_bytes(self) -> bytes:
        return bytes(self.buf)

    def write_head(self, tag: int, typ: int) -> None:
        if tag < 15:
            self.buf.append(((tag << 4) & 0xF0) | (typ & 0x0F))
        else:
            self.buf.append(0xF0 | (typ & 0x0F))
            self.buf.append(tag & 0xFF)

    def write_int8(self, tag: int, value: int) -> None:
        value = int(value)
        if value == 0:
            self.write_head(tag, EN_ZERO)
            return
        self.write_head(tag, EN_INT8)
        self.buf.append(value & 0xFF)

    def write_int16(self, tag: int, value: int) -> None:
        value = int(value)
        if -128 <= value <= 127:
            self.write_int8(tag, value)
            return
        self.write_head(tag, EN_INT16)
        self.buf.extend(value.to_bytes(2, "big", signed=True))

    def write_int32(self, tag: int, value: int) -> None:
        value = int(value)
        if -32768 <= value <= 32767:
            self.write_int16(tag, value)
            return
        self.write_head(tag, EN_INT32)
        self.buf.extend(value.to_bytes(4, "big", signed=True))

    def write_int64(self, tag: int, value: int) -> None:
        value = int(value)
        if -2147483648 <= value <= 2147483647:
            self.write_int32(tag, value)
            return
        self.write_head(tag, EN_INT64)
        high = (value >> 32) & 0xFFFFFFFF
        low = value & 0xFFFFFFFF
        self.buf.extend(high.to_bytes(4, "big", signed=False))
        self.buf.extend(low.to_bytes(4, "big", signed=False))

    def write_bytes(self, tag: int, data: bytes) -> None:
        self.write_head(tag, EN_SIMPLELIST)
        self.write_head(0, EN_INT8)
        self.write_int32(0, len(data))
        self.buf.extend(data)

    def write_string(self, tag: int, value: str) -> None:
        raw = value.encode("utf-8")
        if len(raw) > 255:
            self.write_head(tag, EN_STRING4)
            self.buf.extend(len(raw).to_bytes(4, "big", signed=False))
        else:
            self.write_head(tag, EN_STRING1)
            self.buf.append(len(raw))
        self.buf.extend(raw)


class JceReader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    def remaining(self) -> int:
        return len(self.data) - self.pos

    def _need(self, n: int) -> None:
        if self.pos + n > len(self.data):
            raise JceError("unexpected end of JCE buffer")

    def read_head(self) -> tuple[int, int]:
        self._need(1)
        b = self.data[self.pos]
        self.pos += 1
        typ = b & 0x0F
        tag = (b & 0xF0) >> 4
        if tag == 15:
            self._need(1)
            tag = self.data[self.pos]
            self.pos += 1
        return tag, typ

    def peek_head(self) -> tuple[int, int, int]:
        saved = self.pos
        tag, typ = self.read_head()
        size = self.pos - saved
        self.pos = saved
        return tag, typ, size

    def skip_field(self, typ: int) -> None:
        if typ == EN_INT8:
            self.pos += 1
        elif typ == EN_INT16:
            self.pos += 2
        elif typ == EN_INT32:
            self.pos += 4
        elif typ == EN_INT64:
            self.pos += 8
        elif typ == EN_FLOAT:
            self.pos += 4
        elif typ == EN_DOUBLE:
            self.pos += 8
        elif typ == EN_STRING1:
            self._need(1)
            n = self.data[self.pos]
            self.pos += 1 + n
        elif typ == EN_STRING4:
            self._need(4)
            n = int.from_bytes(self.data[self.pos : self.pos + 4], "big", signed=True)
            self.pos += 4 + n
        elif typ in (EN_STRUCTEND, EN_ZERO):
            return
        elif typ == EN_STRUCTBEGIN:
            self.skip_to_struct_end()
        elif typ == EN_SIMPLELIST:
            _, elem_type = self.read_head()
            if elem_type != EN_INT8:
                raise JceError(f"simple list element type {elem_type} is not INT8")
            n = self.read_int32(0, required=True, default=0)
            self._need(n)
            self.pos += n
        elif typ == EN_LIST:
            n = self.read_int32(0, required=True, default=0)
            for _ in range(n):
                _, item_type = self.read_head()
                self.skip_field(item_type)
        elif typ == EN_MAP:
            n = self.read_int32(0, required=True, default=0)
            for _ in range(n * 2):
                _, item_type = self.read_head()
                self.skip_field(item_type)
        else:
            raise JceError(f"cannot skip JCE type {typ}")

    def skip_to_struct_end(self) -> None:
        while True:
            _, typ = self.read_head()
            if typ == EN_STRUCTEND:
                return
            self.skip_field(typ)

    def skip_to_tag(self, tag: int, required: bool) -> bool:
        while self.pos < len(self.data):
            peeked_tag, peeked_type, size = self.peek_head()
            if peeked_type == EN_STRUCTEND or tag <= peeked_tag:
                if peeked_type == EN_STRUCTEND:
                    return False
                return tag == peeked_tag
            self.pos += size
            self.skip_field(peeked_type)
        if required:
            raise JceError(f"required tag {tag} not found")
        return False

    def _read_int_body(self, typ: int) -> int:
        if typ == EN_ZERO:
            return 0
        if typ == EN_INT8:
            self._need(1)
            value = int.from_bytes(self.data[self.pos : self.pos + 1], "big", signed=True)
            self.pos += 1
            return value
        if typ == EN_INT16:
            self._need(2)
            value = int.from_bytes(self.data[self.pos : self.pos + 2], "big", signed=True)
            self.pos += 2
            return value
        if typ == EN_INT32:
            self._need(4)
            value = int.from_bytes(self.data[self.pos : self.pos + 4], "big", signed=True)
            self.pos += 4
            return value
        if typ == EN_INT64:
            self._need(8)
            high = int.from_bytes(self.data[self.pos : self.pos + 4], "big", signed=False)
            low = int.from_bytes(self.data[self.pos + 4 : self.pos + 8], "big", signed=False)
            self.pos += 8
            return (high << 32) + low
        raise JceError(f"integer type mismatch: {typ}")

    def read_int32(self, tag: int, required: bool = False, default: int | None = 0) -> int | None:
        if not self.skip_to_tag(tag, required):
            return default
        _, typ = self.read_head()
        return self._read_int_body(typ)

    def read_int64(self, tag: int, required: bool = False, default: int | None = 0) -> int | None:
        return self.read_int32(tag, required, default)

    def read_bytes(self, tag: int, required: bool = False, default: bytes = b"") -> bytes:
        if not self.skip_to_tag(tag, required):
            return default
        _, typ = self.read_head()
        if typ == EN_SIMPLELIST:
            _, elem_type = self.read_head()
            if elem_type != EN_INT8:
                raise JceError("simple list element type is not INT8")
            n = self.read_int32(0, required=True, default=0)
            if n < 0:
                raise JceError("negative byte length")
            self._need(n)
            value = self.data[self.pos : self.pos + n]
            self.pos += n
            return bytes(value)
        if typ == EN_LIST:
            n = self.read_int32(0, required=True, default=0)
            self._need(n)
            value = self.data[self.pos : self.pos + n]
            self.pos += n
            return bytes(value)
        raise JceError(f"bytes type mismatch: {typ}")

    def read_string(self, tag: int, required: bool = False, default: str = "") -> str:
        if not self.skip_to_tag(tag, required):
            return default
        _, typ = self.read_head()
        if typ == EN_STRING1:
            self._need(1)
            n = self.data[self.pos]
            self.pos += 1
            self._need(n)
            value = self.data[self.pos : self.pos + n]
            self.pos += n
            return value.decode("utf-8", errors="replace")
        if typ == EN_STRING4:
            self._need(4)
            n = int.from_bytes(self.data[self.pos : self.pos + 4], "big", signed=False)
            self.pos += 4
            self._need(n)
            value = self.data[self.pos : self.pos + n]
            self.pos += n
            return value.decode("utf-8", errors="replace")
        raise JceError(f"string type mismatch: {typ}")

    def read_struct_vector(self, tag: int) -> list[bytes]:
        if not self.skip_to_tag(tag, required=False):
            return []
        _, typ = self.read_head()
        if typ != EN_LIST:
            raise JceError(f"expected list, got {typ}")
        count = self.read_int32(0, required=True, default=0)
        if count is None or count < 0 or count > 20000:
            raise JceError(f"invalid list size {count}")
        bodies: list[bytes] = []
        for _ in range(count):
            if not self.skip_to_tag(0, required=True):
                break
            _, item_type = self.read_head()
            if item_type != EN_STRUCTBEGIN:
                self.skip_field(item_type)
                continue
            start = self.pos
            while True:
                peeked_tag, peeked_type, size = self.peek_head()
                if peeked_type == EN_STRUCTEND:
                    bodies.append(bytes(self.data[start : self.pos]))
                    self.pos += size
                    break
                self.pos += size
                self.skip_field(peeked_type)
        return bodies


@dataclass(frozen=True)
class ParsedFrame:
    cmd_type: int
    cmd_name: str
    uri: int | None
    payload: bytes
    push_type: int | None
    protocol_type: int | None
    raw: bytes
    group: str | None = None


def parse_websocket_frame(data: bytes) -> ParsedFrame:
    """Parse a page WebSocket binary frame into command + optional URI.

    Raises JceError if the buffer is not a Huya WebSocketCommand.
    """
    frames = parse_websocket_frames(data)
    return frames[0]


def parse_websocket_frames(data: bytes) -> list[ParsedFrame]:
    """Parse one WebSocketCommand. MsgPushV2 (cmd 22) expands to one frame per URI."""
    reader = JceReader(data)
    cmd_type = reader.read_int32(0, required=True)
    vdata = reader.read_bytes(1, required=False, default=b"")
    cmd_name = CMD_NAMES.get(cmd_type, f"cmd_{cmd_type}")
    if cmd_type == CMD_MSG_PUSH and vdata:
        inner = JceReader(vdata)
        push_type = inner.read_int32(0, required=False, default=0)
        uri = inner.read_int64(1, required=False, default=None)
        payload = inner.read_bytes(2, required=False, default=b"")
        protocol_type = inner.read_int32(3, required=False, default=None)
        return [
            ParsedFrame(
                cmd_type=cmd_type,
                cmd_name=cmd_name,
                uri=uri,
                payload=payload,
                push_type=push_type,
                protocol_type=protocol_type,
                raw=data,
            )
        ]
    if cmd_type == CMD_MSG_PUSH_V2 and vdata:
        group, items = _parse_push_v2(vdata)
        if items:
            return [
                ParsedFrame(
                    cmd_type=cmd_type,
                    cmd_name=cmd_name,
                    uri=uri,
                    payload=payload,
                    push_type=None,
                    protocol_type=None,
                    raw=data,
                    group=group or None,
                )
                for uri, payload in items
            ]
    return [
        ParsedFrame(
            cmd_type=cmd_type,
            cmd_name=cmd_name,
            uri=None,
            payload=vdata,
            push_type=None,
            protocol_type=None,
            raw=data,
        )
    ]


def _parse_push_v2(vdata: bytes) -> tuple[str, list[tuple[int | None, bytes]]]:
    group = ""
    try:
        group = JceReader(vdata).read_string(0, required=False, default="") or ""
    except JceError:
        group = ""
    items = _parse_push_v2_items(vdata)
    return group, items


def _parse_push_v2_items(vdata: bytes) -> list[tuple[int | None, bytes]]:
    # Live packets: tag 0 = group string like "live:<pid>", tag 1 = message list.
    # Older shape: tag 0 is the list itself.
    bodies: list[bytes] = []
    try:
        bodies = JceReader(vdata).read_struct_vector(1)
    except JceError:
        bodies = []
    if not bodies:
        try:
            bodies = JceReader(vdata).read_struct_vector(0)
        except JceError:
            return []
    return [_parse_push_item(body) for body in bodies]


def _parse_push_item(body: bytes) -> tuple[int | None, bytes]:
    try:
        reader = JceReader(body)
        uri = reader.read_int64(0, required=False, default=None)
        if uri is not None and uri >= 100:
            payload = reader.read_bytes(1, required=False, default=b"")
            return uri, payload
    except JceError:
        pass
    try:
        reader = JceReader(body)
        reader.read_int32(0, required=False, default=0)
        uri = reader.read_int64(1, required=False, default=None)
        payload = reader.read_bytes(2, required=False, default=b"")
        return uri, payload
    except JceError:
        return None, body


def build_msg_push(uri: int, payload: bytes = b"", push_type: int = 0, protocol_type: int = 0) -> bytes:
    """Build a MsgPush WebSocketCommand. Used by tests."""
    inner = JceWriter()
    inner.write_int32(0, push_type)
    inner.write_int64(1, uri)
    inner.write_bytes(2, payload)
    inner.write_int32(3, protocol_type)
    outer = JceWriter()
    outer.write_int32(0, CMD_MSG_PUSH)
    outer.write_bytes(1, inner.get_bytes())
    return outer.get_bytes()


def build_msg_push_v2(
    items: list[tuple[int, bytes]],
    style: str = "msg_item",
    group: str = "",
) -> bytes:
    """Build a MsgPushV2 command. style=msg_item (uri@0) or push_message (uri@1)."""
    inner = JceWriter()
    list_tag = 0
    if group:
        inner.write_string(0, group)
        list_tag = 1
    inner.write_head(list_tag, EN_LIST)
    inner.write_int32(0, len(items))
    for uri, payload in items:
        inner.write_head(0, EN_STRUCTBEGIN)
        if style == "push_message":
            inner.write_int32(0, 0)
            inner.write_int64(1, uri)
            inner.write_bytes(2, payload)
        else:
            inner.write_int64(0, uri)
            inner.write_bytes(1, payload)
        inner.write_head(0, EN_STRUCTEND)
    outer = JceWriter()
    outer.write_int32(0, CMD_MSG_PUSH_V2)
    outer.write_bytes(1, inner.get_bytes())
    return outer.get_bytes()
