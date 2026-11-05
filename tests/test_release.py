"""Проверки правил публикации и формирования описания релиза."""

from pathlib import Path
import tempfile
import unittest

from tools.release import ROOT, changelog_entry, package_version, prepare, validate, version_from_tag

CURRENT_VERSION = package_version(ROOT)
CURRENT_TAG = "v" + CURRENT_VERSION


class Release(unittest.TestCase):
    def test_changelog_contains_only_requested_version(self):
        source = "# История\n\n## [0.2.0] - 2026-11-05\n\n- Новое\n\n## [0.1.0] - 2026-11-05\n\n- Старое\n"
        self.assertEqual(changelog_entry(source, "0.2.0"), "- Новое\n")

    def test_invalid_or_missing_version_is_rejected(self):
        for tag in ["main", "v01.2.0", "v0.2.0;echo bad", "0.2.0"]:
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                version_from_tag(tag)
        with self.assertRaises(ValueError):
            changelog_entry("## [0.1.0] - 2026-11-05\n- Старое\n", "0.2.0")

    def test_package_tag_and_changelog_versions_agree(self):
        self.assertTrue(validate(CURRENT_TAG).strip())
        with self.assertRaises(ValueError):
            validate("v9.9.9")

    def test_checksums_require_all_platforms_and_ignore_other_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            wheel = directory / f"pob_poe2_mcp-{CURRENT_VERSION}-py3-none-any.whl"
            wheel.write_bytes(b"wheel")
            with self.assertRaises(ValueError):
                prepare(CURRENT_TAG, directory)
            (directory / "pob-poe2-mcp-windows-x64.zip").write_bytes(b"zip")
            with self.assertRaises(ValueError):
                prepare(CURRENT_TAG, directory)
            for target in ['linux-x64', 'macos-arm64']:
                (directory / f'pob-poe2-mcp-native-{target}.zip').write_bytes(b'native')
            (directory / "private.txt").write_text("Не публиковать", encoding="utf-8")
            packages = prepare(CURRENT_TAG, directory)
            self.assertEqual(len(packages), 4)
            sums = (directory / "SHA256SUMS").read_text(encoding="utf-8")
            self.assertEqual(len(sums.splitlines()), 4)
            self.assertNotIn("private", sums)
            self.assertTrue((directory / "RELEASE_NOTES.md").read_text(encoding="utf-8").strip())


if __name__ == "__main__":
    unittest.main()
