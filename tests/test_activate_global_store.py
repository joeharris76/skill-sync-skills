from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "activate_global_store.py"


class ActivateGlobalStoreTest(unittest.TestCase):
    def test_repoints_only_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = root / "store"
            (store / "skill-sync").mkdir(parents=True)
            (store / "skill-sync" / "SKILL.md").write_text("# Skill Sync\n")
            first = root / "claude" / "skills"
            second = root / "codex" / "skills"

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(store),
                    "--link",
                    str(first),
                    "--link",
                    str(second),
                    "--apply",
                ],
                check=True,
            )

            self.assertEqual(first.resolve(), store.resolve())
            self.assertEqual(second.resolve(), store.resolve())

    def test_refuses_a_real_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = root / "store"
            (store / "skill-sync").mkdir(parents=True)
            (store / "skill-sync" / "SKILL.md").write_text("# Skill Sync\n")
            link = root / "skills"
            link.mkdir()

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(store), "--link", str(link), "--apply"],
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("refusing to replace non-symlink", result.stderr)


if __name__ == "__main__":
    unittest.main()
