import unittest

from huya_probe.jce import (
    CMD_MSG_PUSH,
    CMD_MSG_PUSH_V2,
    JceError,
    build_msg_push,
    build_msg_push_v2,
    parse_websocket_frame,
    parse_websocket_frames,
)
from huya_probe.inspect import extract_preview
from huya_probe.uri_map import CANDIDATES, lookup


class JceEnvelopeTest(unittest.TestCase):
    def test_roundtrip_known_uris(self) -> None:
        for uri in (1400, 6110, 6111, 1005, 6200, 6501, 6540, 8006):
            payload = b"sample-%d" % uri
            frame = build_msg_push(uri, payload, push_type=1, protocol_type=2)
            parsed = parse_websocket_frame(frame)
            self.assertEqual(parsed.cmd_type, CMD_MSG_PUSH)
            self.assertEqual(parsed.uri, uri)
            self.assertEqual(parsed.payload, payload)
            self.assertEqual(parsed.push_type, 1)
            self.assertEqual(parsed.protocol_type, 2)

    def test_empty_payload(self) -> None:
        parsed = parse_websocket_frame(build_msg_push(8006, b""))
        self.assertEqual(parsed.uri, 8006)
        self.assertEqual(parsed.payload, b"")

    def test_invalid_buffer(self) -> None:
        with self.assertRaises(JceError):
            parse_websocket_frame(b"")

    def test_candidate_lookup(self) -> None:
        self.assertEqual(lookup(1400).struct_name, "MessageNotice")
        self.assertIsNone(lookup(6111).struct_name)
        self.assertEqual(len(CANDIDATES), 8)
        self.assertIsNone(lookup(6540).struct_name)
        self.assertIsNone(lookup(999999))

    def test_msg_push_v2_msg_item(self) -> None:
        frame = build_msg_push_v2(
            [(1400, b"chat"), (6501, b"gift"), (6110, b"enter")],
            style="msg_item",
        )
        parsed = parse_websocket_frames(frame)
        self.assertEqual(parsed[0].cmd_type, CMD_MSG_PUSH_V2)
        self.assertEqual([(item.uri, item.payload) for item in parsed], [
            (1400, b"chat"),
            (6501, b"gift"),
            (6110, b"enter"),
        ])

    def test_msg_push_v2_push_message(self) -> None:
        frame = build_msg_push_v2([(8006, b"count")], style="push_message")
        parsed = parse_websocket_frames(frame)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].uri, 8006)
        self.assertEqual(parsed[0].payload, b"count")

    def test_msg_push_v2_with_group(self) -> None:
        frame = build_msg_push_v2(
            [(6111, b"enter"), (1400, b"chat")],
            group="live:1234567890123",
        )
        parsed = parse_websocket_frames(frame)
        self.assertEqual([(item.uri, item.payload) for item in parsed], [
            (6111, b"enter"),
            (1400, b"chat"),
        ])
        self.assertEqual(parsed[0].group, "live:1234567890123")

    def test_extract_preview_skips_urls(self) -> None:
        from huya_probe.jce import JceWriter

        writer = JceWriter()
        writer.write_string(1, "广州的游客")
        writer.write_string(2, "https://huyaimg.msstatic.com/avatar/x.jpg")
        writer.write_int32(3, 12)
        preview = extract_preview(writer.get_bytes())
        self.assertIn("广州的游客", preview["text_preview"])
        self.assertTrue(all("http" not in t for t in preview["text_preview"]))
        self.assertIn(12, preview["int_preview"])


if __name__ == "__main__":
    unittest.main()
