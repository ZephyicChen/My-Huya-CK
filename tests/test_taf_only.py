import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TafOnlyBoundaryTest(unittest.TestCase):
    def test_worker_has_no_websocket_business_hook(self) -> None:
        source = (ROOT / "huya_ck" / "platform" / "worker.py").read_text(encoding="utf-8")
        self.assertNotIn("attach_page", source)
        self.assertNotIn("platform.ingest", source)
        self.assertNotIn("frame_stats", source)

    def test_legacy_websocket_business_modules_are_not_in_product(self) -> None:
        platform = ROOT / "huya_ck" / "platform"
        for relative in ("ingest.py", "pipeline.py", "jce.py"):
            self.assertFalse((platform / relative).exists(), relative)
        self.assertEqual(list((platform / "decode").glob("*.py")), [])

    def test_websocket_probe_remains_in_validation(self) -> None:
        probe = ROOT / "validation" / "huya_probe"
        self.assertTrue((probe / "capture.py").exists())
        self.assertTrue((probe / "jce.py").exists())


if __name__ == "__main__":
    unittest.main()
