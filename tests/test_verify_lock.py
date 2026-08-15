import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import verify_lock


class VerifyLockWriterTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        (self.root / "skills" / "alpha").mkdir(parents=True)
        (self.root / "skills" / "alpha" / "SKILL.md").write_text("alpha\n", encoding="utf-8")
        (self.root / "skill-sync.yaml").write_text("skills:\n  - alpha\n", encoding="utf-8")
        self.original_lock = {
            "version": 1,
            "lockedAt": "2026-01-01T00:00:00.000Z",
            "catalogMetadata": {"preserve": True},
            "skills": {
                "alpha": {
                    "source": {"type": "git", "url": "example.invalid/catalog", "ref": "abc123"},
                    "installMode": "copy",
                    "custom": "preserve",
                    "files": {
                        "removed.md": {"sha256": "stale", "size": 5},
                    },
                }
            },
        }
        self.lock_path = self.root / "skill-sync.lock"
        self.lock_path.write_text(json.dumps(self.original_lock, indent=2) + "\n", encoding="utf-8")

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_write_refreshes_files_and_preserves_provenance(self):
        reference = self.root / "skills" / "alpha" / "references" / "guide.md"
        reference.parent.mkdir()
        reference.write_text("guide\n", encoding="utf-8")

        self.assertEqual(verify_lock.write_lock(self.root), [])
        written = json.loads(self.lock_path.read_text(encoding="utf-8"))

        self.assertEqual(written["version"], self.original_lock["version"])
        self.assertEqual(written["catalogMetadata"], self.original_lock["catalogMetadata"])
        self.assertEqual(written["skills"]["alpha"]["source"], self.original_lock["skills"]["alpha"]["source"])
        self.assertEqual(written["skills"]["alpha"]["installMode"], "copy")
        self.assertEqual(written["skills"]["alpha"]["custom"], "preserve")
        self.assertNotEqual(written["lockedAt"], self.original_lock["lockedAt"])
        self.assertEqual(set(written["skills"]["alpha"]["files"]), {"SKILL.md", "references/guide.md"})

        skill_entry = written["skills"]["alpha"]["files"]["SKILL.md"]
        self.assertEqual(skill_entry["size"], 6)
        self.assertEqual(skill_entry["sha256"], hashlib.sha256(b"alpha\n").hexdigest())
        self.assertEqual(verify_lock.verify(self.root), [])

    def test_write_refuses_manifest_lock_skill_mismatch(self):
        (self.root / "skill-sync.yaml").write_text("skills:\n  - alpha\n  - beta\n", encoding="utf-8")
        original_bytes = self.lock_path.read_bytes()

        problems = verify_lock.write_lock(self.root)

        self.assertEqual(problems, ["beta: declared in skill-sync.yaml but absent from the lock"])
        self.assertEqual(self.lock_path.read_bytes(), original_bytes)

    def test_write_refuses_missing_skill_directory(self):
        (self.root / "skills" / "alpha" / "SKILL.md").unlink()
        (self.root / "skills" / "alpha").rmdir()
        original_bytes = self.lock_path.read_bytes()

        problems = verify_lock.write_lock(self.root)

        self.assertIn("alpha: locked but skills/alpha does not exist", problems)
        self.assertEqual(self.lock_path.read_bytes(), original_bytes)

    def test_atomic_replace_failure_leaves_original_lock(self):
        original_bytes = self.lock_path.read_bytes()

        with mock.patch.object(verify_lock.os, "replace", side_effect=OSError("replace failed")):
            with self.assertRaisesRegex(OSError, "replace failed"):
                verify_lock.write_lock(self.root)

        self.assertEqual(self.lock_path.read_bytes(), original_bytes)
        self.assertFalse((self.root / ".skill-sync.lock.tmp").exists())


if __name__ == "__main__":
    unittest.main()
