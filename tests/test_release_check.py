import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import release_check


class ReleaseCheckTest(unittest.TestCase):
    def test_sensitive_prefixes_cover_local_runtime_data(self) -> None:
        self.assertIn("logs/", release_check.SENSITIVE_PREFIXES)
        self.assertIn("playwright-profile/", release_check.SENSITIVE_PREFIXES)
        self.assertIn("config/app.json", release_check.SENSITIVE_PREFIXES)
        self.assertIn("validation/event-captures/", release_check.SENSITIVE_PREFIXES)
        self.assertIn(".venv/", release_check.SENSITIVE_PREFIXES)

    def test_web_assets_are_current(self) -> None:
        self.assertEqual(release_check.web_asset_errors(), [])

    def test_web_assets_report_stale_builds(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            assets = root / "assets"
            assets.mkdir()
            (root / "index.html").write_text(
                '<script src="/assets/index-current.js"></script>'
                '<link href="/assets/index-current.css" rel="stylesheet">',
                encoding="utf-8",
            )
            for name in ("index-current.js", "index-current.css", "index-old.js"):
                (assets / name).touch()
            with (
                patch.object(release_check, "WEB_INDEX", root / "index.html"),
                patch.object(release_check, "WEB_ASSETS", assets),
            ):
                errors = release_check.web_asset_errors()
        self.assertTrue(any("旧产物" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
