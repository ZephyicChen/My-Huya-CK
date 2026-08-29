import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from huya_ck.app import create_app
from huya_ck.features.novel.library import NovelLibrary
from huya_ck.platform import config_store

TEXT = "。".join(f"第{i}段的内容" for i in range(6)) + "。"


class NovelApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.path_patch = patch("huya_ck.platform.config_store.CONFIG_PATH", self.tmp / "app.json")
        self.path_patch.start()
        self.library = NovelLibrary(self.tmp / "novels")
        for target in (
            "huya_ck.features.novel.player.library_module.library",
            "huya_ck.api.novels.library",
        ):
            patch(target, self.library).start()
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        patch.stopall()
        self.path_patch.stop()

    def test_upload_list_and_preview(self) -> None:
        response = self.client.post(
            "/api/novels?name=测试小说", content=TEXT.encode("utf-8")
        )
        self.assertEqual(response.status_code, 200)
        novel_id = response.json()["novel"]["id"]
        listing = self.client.get("/api/novels").json()["novels"]
        self.assertEqual([item["id"] for item in listing], [novel_id])
        preview = self.client.get(f"/api/novels/{novel_id}/preview")
        self.assertEqual(preview.status_code, 200)
        self.assertIn("total_chars", preview.json())

    def test_upload_rejects_invalid_utf8(self) -> None:
        response = self.client.post("/api/novels?name=坏文件", content=b"\xff\xfe")
        self.assertEqual(response.status_code, 400)
        self.assertIn("UTF-8", response.json()["detail"])

    def test_upload_rejects_oversize(self) -> None:
        response = self.client.post("/api/novels?name=超大", content=b"a" * (5 * 1024 * 1024 + 1))
        self.assertEqual(response.status_code, 413)

    def test_settings_validation(self) -> None:
        response = self.client.put("/api/novels/settings", json={"config": {"max_chars": 14}})
        self.assertEqual(response.status_code, 400)
        response = self.client.put("/api/novels/settings", json={"config": {"max_chars": 999}})
        self.assertEqual(response.status_code, 400)
        response = self.client.put("/api/novels/settings", json={"config": {"max_chars": 28}})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["config"]["max_chars"], 28)

    def test_loop_setting_roundtrip(self) -> None:
        response = self.client.put("/api/novels/settings", json={"config": {"loop": True}})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["config"]["loop"])

    def test_player_actions(self) -> None:
        novel_id = self.client.post(
            "/api/novels?name=测试小说", content=TEXT.encode("utf-8")
        ).json()["novel"]["id"]
        self.client.put("/api/interaction", json={"interaction": {"enabled": True}})
        self.client.put(
            "/api/novels/settings",
            json={"config": {"enabled": True, "novel_id": novel_id, "max_chars": 28}},
        )
        response = self.client.post("/api/novels/player/start")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["player"]["config"]["state"], "playing")
        response = self.client.post("/api/novels/player/pause")
        self.assertEqual(response.json()["player"]["config"]["state"], "paused")
        response = self.client.post("/api/novels/player/unknown")
        self.assertEqual(response.status_code, 404)

    def test_delete_playing_novel_is_refused(self) -> None:
        novel_id = self.client.post(
            "/api/novels?name=测试小说", content=TEXT.encode("utf-8")
        ).json()["novel"]["id"]
        self.client.put("/api/interaction", json={"interaction": {"enabled": True}})
        self.client.put(
            "/api/novels/settings",
            json={"config": {"enabled": True, "novel_id": novel_id, "max_chars": 28}},
        )
        self.client.post("/api/novels/player/start")
        response = self.client.delete(f"/api/novels/{novel_id}")
        self.assertEqual(response.status_code, 409)
        self.client.post("/api/novels/player/stop")
        response = self.client.delete(f"/api/novels/{novel_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/novels").json()["novels"], [])

    def test_path_traversal_in_id_is_404(self) -> None:
        response = self.client.delete("/api/novels/..%2F..%2Fapp")
        self.assertIn(response.status_code, (404, 400))


if __name__ == "__main__":
    unittest.main()
