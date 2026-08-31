import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from huya_ck.app import create_app
from huya_ck.platform import config_store


class ApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp()) / "app.json"
        self.patcher = patch("huya_ck.platform.config_store.CONFIG_PATH", self.tmp)
        self.patcher.start()
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.patcher.stop()

    def test_features_catalog(self) -> None:
        data = self.client.get("/api/features").json()
        ids = [item["id"] for item in data["features"]]
        self.assertEqual(
            ids,
            ["welcome", "gift_thank", "guard_thank", "superfan_thank", "noble_thank", "danmaku"],
        )
        non_gift = [item for item in data["features"] if item.get("ui_group", {}).get("id") == "non_gift_thank"]
        self.assertEqual([item["id"] for item in non_gift], ["guard_thank", "superfan_thank", "noble_thank"])
        self.assertTrue(all(item["ui_group"]["title"] == "非礼物感谢" for item in non_gift))
        welcome = data["features"][0]
        noble = next(field for field in welcome["fields"] if field["key"] == "min_noble_level")
        self.assertEqual(noble["type"], "select")
        self.assertTrue(any(opt["label"] == "骑士及以上" for opt in noble["options"]))

    def test_put_feature_roundtrip(self) -> None:
        response = self.client.put(
            "/api/features/gift_thank/config",
            json={"config": {"min_value_fen": 888}},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["config"]["min_value_fen"], 888)
        loaded = config_store.feature_config("gift_thank")
        self.assertEqual(loaded["min_value_fen"], 888)

    def test_run_status_not_started(self) -> None:
        data = self.client.get("/api/run/status").json()
        self.assertFalse(data["running"])
        self.assertEqual(data["queue_size"], 0)

    def test_chat_control_roundtrip(self) -> None:
        response = self.client.put(
            "/api/chat/control",
            json={
                "config": {
                    "owner_uid": "9007199254740999",
                    "owner_nick": "本人",
                    "whitelist": [{"uid": "8", "nick": "助手", "enabled": True}],
                }
            },
        )
        self.assertEqual(response.status_code, 200)
        data = self.client.get("/api/chat/control").json()
        self.assertEqual(data["config"]["owner_uid"], "9007199254740999")
        self.assertEqual(data["config"]["whitelist"][0]["uid"], "8")
        self.assertIn("recent_speakers", self.client.get("/api/chat/state").json()["state"])

    def test_start_without_room(self) -> None:
        response = self.client.post("/api/run/start")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["ok"])
        self.assertIn("房间", data["message"])

    def test_js_asset_is_javascript(self) -> None:
        from huya_ck.paths import WEB_DIR

        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("text/html", page.headers["content-type"])
        scripts = list((WEB_DIR / "assets").glob("index-*.js"))
        self.assertTrue(scripts)
        response = self.client.get(f"/assets/{scripts[0].name}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("javascript", response.headers["content-type"])

    def test_nick_overrides_roundtrip_and_validation(self) -> None:
        response = self.client.put(
            "/api/nick-overrides",
            json={"nick_overrides": [{"uid": "111", "alias": "大哥", "note": "备注", "enabled": True}]},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["nick_overrides"][0]["alias"], "大哥")

        self.assertEqual(self.client.get("/api/nick-overrides").json()["nick_overrides"][0]["uid"], "111")

        # 非法输入：非数组、未知字段
        self.assertEqual(self.client.put("/api/nick-overrides", json={"nick_overrides": "x"}).status_code, 400)
        self.assertEqual(
            self.client.put("/api/nick-overrides", json={"nick_overrides": [{"uid": "1", "alias": "a", "bad": 1}]}).status_code,
            400,
        )
