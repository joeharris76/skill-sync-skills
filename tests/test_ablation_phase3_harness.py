"""Phase 3 harness: text-span cuts, interleaving, reference-read logging. Standard library only."""

from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ABLATION = Path(__file__).resolve().parents[1] / "evals" / "ablation"
sys.path.insert(0, str(ABLATION))

import run  # noqa: E402

NAME_LINE = "\n" + re.search(r"^name: .*$", (run.CATALOG / "skills/todo/SKILL.md").read_text(), re.M).group(0) + "\n"


class SkillCuts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_cut_removes_the_text_once(self):
        dest = run.skills_dir("HEAD", self.cache, None, None, [["todo/SKILL.md", NAME_LINE]], "a")
        self.assertNotIn(NAME_LINE, (dest / "todo" / "SKILL.md").read_text())
        plain = run.skills_dir("HEAD", self.cache)
        self.assertIn(NAME_LINE, (plain / "todo" / "SKILL.md").read_text())

    def test_missing_text_names_arm_and_file(self):
        with self.assertRaises(SystemExit) as cm:
            run.skills_dir("HEAD", self.cache, None, None, [["todo/SKILL.md", "no such text anywhere"]], "arm-x")
        self.assertIn("arm-x", str(cm.exception))
        self.assertIn("todo/SKILL.md", str(cm.exception))

    def test_repeated_text_is_refused(self):
        with self.assertRaises(SystemExit) as cm:
            run.skills_dir("HEAD", self.cache, None, None, [["todo/SKILL.md", "\n"]], "arm-y")
        self.assertIn("arm-y", str(cm.exception))
        self.assertEqual(list((self.cache / "skills").glob(".*")), [])  # no staging left behind

    def test_no_cuts_keeps_the_plain_cache_path(self):
        self.assertEqual(run.skills_dir("HEAD", self.cache, None, None, None, "a"), run.skills_dir("HEAD", self.cache))


class Scheduling(unittest.TestCase):
    JOBS = [(s, a, r) for s in "xyz" for a in ("full", "minus") for r in range(5)]

    def test_same_seed_same_order_and_all_jobs_kept(self):
        a, b = run.interleave(self.JOBS, 7), run.interleave(self.JOBS, 7)
        self.assertEqual(a, b)
        self.assertNotEqual(a, self.JOBS)
        self.assertEqual(sorted(a), sorted(self.JOBS))
        self.assertNotEqual(a, run.interleave(self.JOBS, 8))

    def test_seed_is_recorded_per_run(self):
        with tempfile.TemporaryDirectory() as d:
            run.record_seed(Path(d) / "out", 5, 10)
            run.record_seed(Path(d) / "out", 6, 2)
            self.assertEqual([e["seed"] for e in json.loads((Path(d) / "out" / "seeds.json").read_text())], [5, 6])

    def test_ceiling_reaches_ledger(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(run.Ledger(Path(d) / "l.json", 5.0).ceiling, 5.0)


class ReferencesRead(unittest.TestCase):
    def test_omp_counts_tool_args_only(self):
        def start(tool, **args):
            return {"type": "tool_execution_start", "toolCallId": "t", "toolName": tool, "args": args, "intent": "x"}
        events = [start("read", path="skill://todo/references/x.md"),
                  start("bash", command="cat /a/skills/todo/references/y/z.md."),
                  start("read", path="skill://todo"),
                  {"type": "message_end", "message": {"content": [
                      {"type": "text", "text": "see skill://todo/references/mentioned.md"}]}}]
        stdout = ["".join(json.dumps(e) + "\n" for e in events)]
        self.assertEqual(run.HARNESSES["omp"].references_read(events, stdout),
                         ["todo/references/x.md", "todo/references/y/z.md"])

    def test_claude_code_read_tool(self):
        events = [{"type": "assistant", "message": {"id": "m", "content": [
            {"type": "tool_use", "id": "t", "name": "Read",
             "input": {"file_path": "/r/.claude/skills/todo/references/a.md"}}]}}]
        self.assertEqual(run.ClaudeCode.references_read(events, []), ["todo/references/a.md"])


class FollowWork(unittest.TestCase):
    def setUp(self):
        self.repo = Path(tempfile.mkdtemp())
        self.git("init", "-q", "-b", "main")
        (self.repo / "a.txt").write_text("base\n")
        self.git("add", "a.txt")
        self.git("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", "base")
        self.base = self.git("rev-parse", "HEAD")

    def git(self, *args: str) -> str:
        return run.subprocess.run(["git", *args], cwd=self.repo, capture_output=True, text=True).stdout.strip()

    def commit_on_branch(self) -> str:
        self.git("checkout", "-q", "-b", "fix")
        (self.repo / "a.txt").write_text("fixed\n")
        self.git("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qam", "fix")
        return self.git("rev-parse", "HEAD")

    def test_back_on_base_checks_out_the_work(self):
        work = self.commit_on_branch()
        self.git("checkout", "-q", "main")
        self.assertEqual(run.follow_work(self.repo, self.base), work)
        self.assertEqual((self.repo / "a.txt").read_text(), "fixed\n")

    def test_left_on_the_work_is_untouched(self):
        self.commit_on_branch()
        self.assertIsNone(run.follow_work(self.repo, self.base))

    def test_dirty_tree_is_untouched(self):
        self.commit_on_branch()
        self.git("checkout", "-q", "main")
        (self.repo / "a.txt").write_text("edited\n")
        self.assertIsNone(run.follow_work(self.repo, self.base))

    def test_stash_is_not_followed(self):
        (self.repo / "a.txt").write_text("stashed\n")
        self.git("-c", "user.name=t", "-c", "user.email=t@example.com", "stash", "-q")
        self.assertIsNone(run.follow_work(self.repo, self.base))

    def test_new_fields_change_the_hash_only_when_set(self):
        plain = {"checks": {"a": "true"}, "rules": {}}
        self.assertEqual(run.checks_hash(plain), run.checks_hash({**plain, "checks_follow_work": False}))
        self.assertNotEqual(run.checks_hash(plain), run.checks_hash({**plain, "checks_follow_work": True}))


if __name__ == "__main__":
    unittest.main()
