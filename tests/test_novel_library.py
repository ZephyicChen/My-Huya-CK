import tempfile
import unittest
from pathlib import Path

from huya_ck.features.novel.library import NovelError, NovelLibrary


class NovelLibraryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp()) / "novels"
        self.library = NovelLibrary(self.root)

    def test_upload_list_delete_roundtrip(self) -> None:
        meta = self.library.upload("测试小说", "第一段。\n第二段。".encode("utf-8"))
        self.assertEqual([item["id"] for item in self.library.list()], [meta["id"]])
        self.assertTrue((self.root / meta["file_name"]).exists())
        text = self.library.read_text(meta["id"])
        self.assertEqual(text, "第一段。\n第二段。")
        self.library.delete(meta["id"])
        self.assertEqual(self.library.list(), [])
        self.assertFalse((self.root / meta["file_name"]).exists())

    def test_upload_rejects_empty_and_invalid_utf8(self) -> None:
        with self.assertRaises(NovelError):
            self.library.upload("空", b"")
        with self.assertRaises(NovelError):
            self.library.upload("乱码", b"\xff\xfe\xfa")

    def test_upload_rejects_duplicate_content(self) -> None:
        self.library.upload("一本", "内容".encode("utf-8"))
        with self.assertRaises(NovelError):
            self.library.upload("另一本", "内容".encode("utf-8"))

    def test_upload_rejects_oversize(self) -> None:
        with self.assertRaises(NovelError):
            self.library.upload("超大", b"a" * (5 * 1024 * 1024 + 1))

    def test_path_traversal_is_blocked(self) -> None:
        with self.assertRaises(NovelError):
            self.library.read_text("../../app")
        with self.assertRaises(NovelError):
            self.library.delete("../secrets")

    def test_tampered_file_fails_digest_check(self) -> None:
        meta = self.library.upload("会被改", "原文".encode("utf-8"))
        (self.root / meta["file_name"]).write_text("被改过了", encoding="utf-8")
        with self.assertRaises(NovelError):
            self.library.read_text(meta["id"])

    def test_display_name_is_not_used_as_path(self) -> None:
        meta = self.library.upload("../../evil", "内容".encode("utf-8"))
        self.assertNotIn("..", meta["file_name"])
        self.assertTrue((self.root / meta["file_name"]).exists())


if __name__ == "__main__":
    unittest.main()
