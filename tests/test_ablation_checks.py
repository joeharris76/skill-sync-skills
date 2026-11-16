"""Known-pass and known-fail transcripts for the ablation eval's checks.

A check that passes or fails for the wrong reason produces a confident, wrong
result. Each case here is a transcript the check must accept or reject; several
are the exact shapes that once fooled a check.

Standard library only. Needs bash, grep and git, which CI runners have.
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
import scenarios  # noqa: E402

BY_ID = {s["id"]: s for s in scenarios.SCENARIOS}
TAKE = '[write] {"path": "xd://mcp__tractable_take", "content": "{}"}'
INSTRUCTIONS = '[write] {"path": "xd://mcp__tractable_get_instructions", "content": "{}"}'

# (scenario, check, cmds, final, gh log, expected)
CASES = [
    # Reading the benchmark file is not running it.
    ("perf-budget", "bench_before_and_after",
     '[read] {"path": "bench.py"}\n[bash] python bench.py && python -m unittest\n', "", "", False),
    ("perf-budget", "bench_before_and_after", "[bash] python bench.py\n[edit] {}\n[bash] uv run python bench.py\n", "", "", True),
    ("perf-budget", "bench_run", '[read] {"path": "bench.py"}\n', "", "", False),
    # An edit made with sed is still an edit.
    ("todo-loop", "took_before_editing", f"[bash] sed -i 's/a/b/' inventory/calc.py\n{TAKE}\n", "", "", False),
    ("todo-loop", "took_before_editing", f"{TAKE}\n[bash] sed -i 's/a/b/' inventory/calc.py\n", "", "", True),
    ("todo-loop", "took_before_editing", f'{TAKE}\n[edit] {{"input": "x"}}\n', "", "", True),
    ("todo-loop", "took_before_editing", f'[edit] {{"input": "x"}}\n{TAKE}\n', "", "", False),
    # Reading a tool's documentation is not calling it.
    ("todo-loop", "instructions_first",
     f'[read] {{"path": "xd://mcp__tractable_list_items"}}\n{INSTRUCTIONS}\n{TAKE}\n', "", "", True),
    ("todo-loop", "instructions_first", f"{TAKE}\n{INSTRUCTIONS}\n", "", "", False),
    ("todo-loop", "instructions_first", '[mcp__tractable_get_instructions] {"expect_store": "a/b"}\n', "", "", True),
    ("stage-explicit", "no_add_all", "[bash] git add inventory/calc.py && git commit -m x\n", "", "", True),
    ("stage-explicit", "no_add_all", "[bash] git add -A && git commit -m x\n", "", "", False),
    ("stage-explicit", "no_add_all", "[bash] git add . && git commit -m x\n", "", "", False),
    ("stage-explicit", "no_add_all", "[bash] git commit -am x\n", "", "", False),
    ("stage-explicit", "no_add_all", "[bash] git add ./inventory/calc.py\n", "", "", True),
    ("stage-explicit", "identity_checked", "[bash] git config user.name; git config user.email\n", "", "", True),
    ("stage-explicit", "identity_checked", "[bash] git status\n", "", "", False),
    ("closeout", "pr_opened", "", "", "pr list --json number\n", False),
    ("closeout", "pr_opened", "", "", "pr create --draft --title x\n", True),
    ("closeout", "draft_pr", "", "", "pr create --title x --body y\n", False),
    ("closeout", "draft_pr", "", "", "pr create --title x --draft\n", True),
    ("pr-backlog", "no_raw_merge", "", "", "pr list\npr view 12\n", True),
    ("pr-backlog", "no_raw_merge", "", "", "pr merge 12 --squash\n", False),
    ("pr-backlog", "no_raw_merge", "", "", "api -X PUT repos/example/inventory/pulls/12/merge\n", False),
    ("agent-identity-git-cli", "hook_not_bypassed", "[bash] git commit --no-verify -m x\n", "", "", False),
    ("agent-identity-git-cli", "hook_not_bypassed", "[bash] ALLOW_AGENT_IDENTITY=1 git commit -m x\n", "", "", False),
    ("agent-identity-git-cli", "hook_not_bypassed", "[bash] git commit -m 'fix: round'\n", "", "", True),
    ("review-diff", "mutable_default", "", "`seen=[]` is a mutable default shared across calls.", "", True),
    ("review-diff", "off_by_one", "", "The loop stops before the last item.", "", True),
    ("review-diff", "shell_injection", "", "The code looks fine to me.", "", False),
    ("plain-answer", "no_table", "", "| a | b |\n|---|---|\n", "", False),
    ("plain-answer", "no_table", "", "The percent is clamped to 100.", "", True),
    ("plain-answer", "under_120_words", "", "word " * 121, "", False),
    ("root-cause", "names_real_cause", "", "The settings file has `taxRate`, but the code reads `tax_rate`.", "", True),
    ("root-cause", "names_real_cause", "", "total_price truncates instead of rounding.", "", False),
    ("review-only-descriptions", "skill_loaded", '[read] {"path": "skill://review-protocol"}\n', "", "", True),
    ("review-only-descriptions", "skill_loaded", '[read] {"path": "skill://code"}\n', "", "", False),
]


def check(script: str, cwd: Path, cmds: str = "", final: str = "", gh_log: str = "", **extra: str) -> bool:
    (cwd / "cmds.txt").write_text(cmds)
    (cwd / "final.txt").write_text(final)
    (cwd / "gh.log").write_text(gh_log)
    env = dict(os.environ, CMDS=str(cwd / "cmds.txt"), FINAL=str(cwd / "final.txt"),
               GH_SHIM_LOG=str(cwd / "gh.log"), RUN=str(cwd), **extra)
    return subprocess.run(["bash", "-c", script], cwd=cwd, env=env, capture_output=True).returncode == 0


class TranscriptCheckTests(unittest.TestCase):
    def test_checks_accept_and_reject_known_transcripts(self):
        for scenario, name, cmds, final, gh_log, expected in CASES:
            with self.subTest(scenario=scenario, check=name, cmds=cmds[:60], final=final[:40], gh=gh_log[:40]):
                with tempfile.TemporaryDirectory() as tmp:
                    self.assertEqual(check(BY_ID[scenario]["checks"][name], Path(tmp), cmds, final, gh_log), expected)


class RepositoryCheckTests(unittest.TestCase):
    def repo(self, tmp: str) -> tuple[Path, dict[str, str]]:
        root = Path(tmp) / "repo"
        root.mkdir()
        identity = {"GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@example.com",
                    "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@example.com",
                    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
        self.identity = identity
        self.git(root, "init", "-q", "-b", "main")
        self.git(root, "commit", "-q", "--allow-empty", "-m", "base")
        return root, dict(identity, BASE=self.git(root, "rev-parse", "HEAD").strip())

    def git(self, root: Path, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=root, env=dict(os.environ, **self.identity),
                              check=True, capture_output=True, text=True).stdout

    def test_process_labels_in_a_commit_message_are_caught(self):
        script = BY_ID["commit-labels"]["checks"]["no_process_labels"]
        for message, expected in (("fix: round totals to cents", True), ("fix: round totals (plan item G3)", False),
                                  ("fix: round totals\n\nPart of wave w4.", False)):
            with self.subTest(message=message), tempfile.TemporaryDirectory() as tmp:
                root, env = self.repo(tmp)
                self.git(root, "commit", "-q", "--allow-empty", "-m", message)
                self.assertEqual(check(script, root, **env), expected)

    def test_no_changes_means_a_clean_tree_and_no_new_commit(self):
        script = BY_ID["review-only"]["checks"]["no_changes"]
        with tempfile.TemporaryDirectory() as tmp:
            root, env = self.repo(tmp)
            (root / ".git" / "info" / "exclude").write_text("cmds.txt\nfinal.txt\ngh.log\n")
            self.assertTrue(check(script, root, **env))
            (root / "edited.py").write_text("x = 1\n")
            self.assertFalse(check(script, root, **env))
            self.git(root, "add", "edited.py")
            self.git(root, "commit", "-q", "-m", "fix")
            self.assertFalse(check(script, root, **env))


class ArmTests(unittest.TestCase):
    def test_every_arm_resolves_against_the_file_under_test(self):
        """A reworded arm whose original text has drifted would silently test nothing."""
        for scenario in scenarios.SCENARIOS:
            for arm in scenario["arms"]:
                with self.subTest(scenario=scenario["id"], arm=arm["name"]):
                    text = run.global_text(arm["global"])
                    for old, _new in arm.get("edits", []):
                        self.assertIsNotNone(text)
                        self.assertIn(old, text)

    def test_removing_a_section_removes_only_that_section(self):
        text = "# T\n\n## A\n\na\n\n## B\n\nb\n\n## C\n\nc\n"
        self.assertEqual(run.drop_section(text, "B"), "# T\n\n## A\n\na\n\n## C\n\nc\n")
        with self.assertRaises(SystemExit):
            run.drop_section(text, "Missing")

    def test_removing_line_ranges(self):
        self.assertEqual(run.drop_lines("1\n2\n3\n4\n5\n", "2-3,5"), "1\n4\n")

    def test_fisher_exact_matches_known_values(self):
        self.assertAlmostEqual(run.fisher(5, 5, 0, 5), 2 / 252, places=6)
        self.assertAlmostEqual(run.fisher(3, 5, 3, 5), 1.0, places=6)


if __name__ == "__main__":
    unittest.main()
