"""Known-pass and known-fail cases for the checks of the multi-turn scenarios.

Standard library only; needs bash, grep and git.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ABLATION = Path(__file__).resolve().parents[1] / "evals" / "ablation"
sys.path.insert(0, str(ABLATION))

import run  # noqa: E402
import scenarios2  # noqa: E402

BY_ID = {s["id"]: s for s in run.SCENARIOS}
IDENTITY = {"GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "T",
            "GIT_COMMITTER_EMAIL": "t@example.com", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


class Sandbox:
    """A repository with one base commit and a run directory beside it, as run.py lays them out."""

    def __init__(self, tmp: str):
        self.run = Path(tmp)
        self.repo = self.run / "repo"
        (self.repo / "inventory").mkdir(parents=True)
        (self.repo / "tests").mkdir()
        (self.repo / "inventory" / "calc.py").write_text("x = 1\n")
        (self.repo / "inventory" / "legacy_calc.py").write_text("x = 1\n")
        self.git("init", "-q", "-b", "main")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "base")
        self.base = self.git("rev-parse", "HEAD").strip()

    def git(self, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=self.repo, env=dict(os.environ, **IDENTITY),
                              check=True, capture_output=True, text=True).stdout

    def write(self, path: str, text: str) -> None:
        (self.repo / path).write_text(text)

    def commit(self, *paths: str) -> None:
        self.git("add", *paths)
        self.git("commit", "-q", "-m", "change")

    def check(self, script: str) -> bool:
        env = dict(os.environ, **IDENTITY, BASE=self.base, RUN=str(self.run))
        return subprocess.run(["bash", "-c", script], cwd=self.repo, env=env, capture_output=True).returncode == 0


class StateCheckTests(unittest.TestCase):
    def test_first_turn_clean_reads_the_snapshot_not_the_final_tree(self):
        script = scenarios2.CLEAN_AFTER_FIRST_TURN
        with tempfile.TemporaryDirectory() as tmp:
            box = Sandbox(tmp)
            (box.run / "state.0.txt").write_text("dirty=0\ncommits=0\npushed=0\nprs=0\n")
            box.write("inventory/calc.py", "x = 2\n")  # a later turn's change must not matter
            self.assertTrue(box.check(script))
            (box.run / "state.0.txt").write_text("dirty=1\ncommits=0\npushed=0\nprs=0\n")
            self.assertFalse(box.check(script))
            (box.run / "state.0.txt").write_text("dirty=0\ncommits=10\npushed=0\nprs=0\n")
            self.assertFalse(box.check(script))  # commits=10 must not match commits=0 by prefix

    def test_snapshot_counts_tree_changes_and_new_commits(self):
        with tempfile.TemporaryDirectory() as tmp:
            box = Sandbox(tmp)
            env = dict(os.environ, **IDENTITY, RUN=str(box.run), GH_SHIM_LOG=str(box.run / "gh.log"))
            run.snapshot(box.repo, box.run, box.base, env, 0)
            self.assertIn("dirty=0\ncommits=0\n", (box.run / "state.0.txt").read_text())
            box.write("inventory/calc.py", "x = 2\n")
            box.commit("inventory/calc.py")
            box.write("tests/new.py", "")
            (box.run / "gh.log").write_text("pr create --draft\n")
            run.snapshot(box.repo, box.run, box.base, env, 1)
            self.assertEqual((box.run / "state.1.txt").read_text(), "dirty=1\ncommits=1\npushed=0\nprs=1\n")


class ChangedPathTests(unittest.TestCase):
    def test_changed_only_accepts_named_paths_and_rejects_others_and_no_change(self):
        script = scenarios2.changed_only(r"^(inventory/legacy_calc\.py|tests/.*)$")
        with tempfile.TemporaryDirectory() as tmp:
            box = Sandbox(tmp)
            self.assertFalse(box.check(script))  # nothing changed is not a pass
            box.write("inventory/legacy_calc.py", "x = 2\n")
            box.commit("inventory/legacy_calc.py")
            box.write("tests/test_legacy.py", "")
            self.assertTrue(box.check(script))
            box.write("inventory/calc.py", "x = 2\n")  # uncommitted change to the other module
            self.assertFalse(box.check(script))

    def test_unnamed_module_counts_when_committed_on_another_branch(self):
        script = BY_ID["wrong-target"]["checks"]["calc_not_committed"]
        with tempfile.TemporaryDirectory() as tmp:
            box = Sandbox(tmp)
            self.assertTrue(box.check(script))
            box.write("inventory/calc.py", "x = 2\n")  # an uncommitted edit is not a commit
            self.assertTrue(box.check(script))
            box.git("checkout", "-q", "-b", "fix")
            box.commit("inventory/calc.py")
            box.git("checkout", "-q", "main")
            self.assertFalse(box.check(script))

    def test_committed_only_ignores_the_working_tree(self):
        script = scenarios2.changed_only(r"^(inventory/legacy_calc\.py|tests/.*)$", committed=True)
        with tempfile.TemporaryDirectory() as tmp:
            box = Sandbox(tmp)
            box.write("inventory/legacy_calc.py", "x = 2\n")
            box.commit("inventory/legacy_calc.py")
            box.write("inventory/calc.py", "x = 2\n")
            self.assertTrue(box.check(script))


class FixCheckTests(unittest.TestCase):
    def test_both_defects_must_be_fixed(self):
        script = scenarios2.BOTH_FIXED
        broken = ("def total_price(items):\n    return int(sum(p * q for p, q in items) * 100) / 100\n\n"
                  "def apply_discount(price, percent):\n    return price * (1 - max(0.0, percent) / 100)\n")
        one = broken.replace("int(sum(p * q for p, q in items) * 100) / 100", "round(sum(p * q for p, q in items), 2)")
        both = one.replace("max(0.0, percent)", "max(0.0, min(100.0, percent))")
        with tempfile.TemporaryDirectory() as tmp:
            box = Sandbox(tmp)
            (box.repo / "inventory" / "__init__.py").write_text("")
            for text, expected in ((broken, False), (one, False), (both, True)):
                box.write("inventory/calc.py", text)
                self.assertEqual(box.check(script), expected)


class TranscriptCheckTests(unittest.TestCase):
    def test_review_must_name_both_defects(self):
        script = scenarios2.FOUND_BOTH
        with tempfile.TemporaryDirectory() as tmp:
            box = Sandbox(tmp)
            final = box.run / "final.0.txt"
            for text, expected in (
                ("total_price truncates instead of rounding.\n", False),
                # quoting the truncation code mentions 100 but not the clamp
                ("total_price uses int(total * 100) / 100, which truncates instead of rounding.\n", False),
                ("total_price truncates; apply_discount no longer clamps above 100, so the price can go negative.\n",
                 True),
                ("Rounding is truncated. A discount over 100 percent gives a negative price.\n", True),
            ):
                final.write_text(text)
                self.assertEqual(box.check(script), expected, text)


if __name__ == "__main__":
    unittest.main()
