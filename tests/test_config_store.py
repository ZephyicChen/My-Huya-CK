import json
import tempfile
import unittest
from pathlib import Path

from huya_ck.platform import config_store


class ConfigStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp()) / "app.json"

    def test_missing_file_uses_defaults(self) -> None:
        doc = config_store.load(self.tmp)
        self.assertEqual(doc["room"], "")
        self.assertFalse(doc["show_browser"])
        self.assertFalse(doc["welcome"]["enabled"])
        self.assertFalse(doc["gift_thank"]["enabled"])
        self.assertFalse(doc["superfan_thank"]["enabled"])
        self.assertFalse(doc["noble_thank"]["enabled"])
        self.assertFalse(doc["guard_thank"]["enabled"])
        self.assertFalse(doc["danmaku"]["enabled"])
        self.assertEqual(doc["gift_thank"]["min_value_fen"], 600)
        self.assertEqual(doc["gift_thank"]["min_unit_value_fen"], 0)

    def test_put_feature_persists(self) -> None:
        config_store.put_platform({"room": "123456"}, self.tmp)
        config_store.put_feature("gift_thank", {"min_value_fen": 1000}, self.tmp)
        saved = json.loads(self.tmp.read_text(encoding="utf-8"))
        self.assertEqual(saved["room"], "123456")
        self.assertEqual(saved["gift_thank"]["min_value_fen"], 1000)
        self.assertEqual(
            saved["gift_thank"]["template"],
            "感谢{nick}送的{count}个{item_name}",
        )

    def test_unknown_feature(self) -> None:
        with self.assertRaises(KeyError):
            config_store.put_feature("nope", {}, self.tmp)
