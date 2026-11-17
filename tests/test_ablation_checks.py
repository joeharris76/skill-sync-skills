"""Known-pass and known-fail transcripts for the ablation eval's checks.

A check that passes or fails for the wrong reason produces a confident, wrong
result. Each case here is a transcript the check must accept or reject; several
are the exact shapes that once fooled a check.

Standard library only. Needs bash, grep and git, which CI runners have.
"""

from __future__ import annotations

import json
import re
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ABLATION = Path(__file__).resolve().parents[1] / "evals" / "ablation"
sys.path.insert(0, str(ABLATION))

import run  # noqa: E402
import scenarios  # noqa: E402
import stats  # noqa: E402
import scenarios2  # noqa: E402

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
        for scenario in run.SCENARIOS:
            for arm in scenario["arms"]:
                with self.subTest(scenario=scenario["id"], arm=arm["name"]):
                    text = run.global_text(arm["global"], arm.get("fixture", "global-under-test.md"))
                    for old, _new in arm.get("edits", []):
                        self.assertIsNotNone(text)
                        self.assertIn(old, text)

    def test_compared_arms_and_checks_exist(self):
        """A decision against a misnamed arm or check would compare nothing and report no result."""
        for scenario in run.SCENARIOS:
            names = {arm["name"] for arm in scenario["arms"]}
            for rule, spec in run.rule_specs(scenario).items():
                with self.subTest(scenario=scenario["id"], rule=rule):
                    self.assertIn(spec["reference"], names)
                    self.assertIn(spec["removal"], names)
                    self.assertLessEqual(set(spec["checks"]), set(scenario["checks"]) | set(scenario.get("judged", {})))

    def test_removing_a_section_removes_only_that_section(self):
        text = "# T\n\n## A\n\na\n\n## B\n\nb\n\n## C\n\nc\n"
        self.assertEqual(run.drop_section(text, "B"), "# T\n\n## A\n\na\n\n## C\n\nc\n")
        with self.assertRaises(SystemExit):
            run.drop_section(text, "Missing")

    def test_removing_a_skill_heading_removes_its_subsections_only(self):
        text = "# T\n\n## A\n\na\n\n### A1\n\nx\n\n## B\n\nb\n"
        self.assertEqual(run.drop_heading(text, "A"), "# T\n\n## B\n\nb\n")
        self.assertEqual(run.drop_heading(text, "A1"), "# T\n\n## A\n\na\n\n## B\n\nb\n")
        with self.assertRaises(SystemExit):
            run.drop_heading(text, "Missing")

    def test_skill_drops_name_one_heading_each_in_the_pinned_file(self):
        """A misspelt or duplicated heading would drop nothing or the wrong section."""
        drops = [(sc["id"], a["name"], file, heading) for sc in run.SCENARIOS for a in sc["arms"]
                 for file, heading in a.get("skill_drops", [])]
        self.assertTrue(drops)
        texts = {}
        for sid, name, file, heading in drops:
            if file not in texts:
                shown = subprocess.run(["git", "-C", str(run.CATALOG), "show", f"{scenarios2.PHASE2_SKILLS}:skills/{file}"],
                                       capture_output=True, text=True)
                if shown.returncode:
                    self.skipTest(f"pinned skills commit unavailable: {shown.stderr.strip()}")
                texts[file] = shown.stdout
            with self.subTest(scenario=sid, arm=name):
                found = re.findall(rf"^#+ {re.escape(heading)}\s*$", texts[file], flags=re.M)
                self.assertEqual(len(found), 1)
                self.assertNotIn(found[0], run.drop_heading(texts[file], heading))

    def test_base_scenarios_keep_the_checks_hash_their_results_recorded(self):
        """Scored results are void if a scenario's checks or decision checks change."""
        results = Path("/Users/joe/.tractable/finding-drafts/skill-sync-skills/2026-11-15-ablation-eval/phase2/"
                       "core-sonnet/results")
        if not results.is_dir():
            self.skipTest("phase 2 core-sonnet results not present")
        by_id = {s["id"]: s for s in run.SCENARIOS}
        for sid in ("plan-then-proceed", "review-then-address"):
            recorded = {json.loads(p.read_text()).get("checks_hash") for p in results.glob(f"{sid}__*.json")}
            with self.subTest(scenario=sid):
                self.assertEqual(recorded, {run.checks_hash(by_id[sid])})

    def test_skill_section_scenarios_leave_their_base_alone(self):
        by_id = {s["id"]: s for s in run.SCENARIOS}
        for base in scenarios2.SKILL_SECTIONS:
            new = by_id[f"skills-{base}"]
            with self.subTest(base=base):
                self.assertEqual(new["checks"], by_id[base]["checks"])
                self.assertEqual(new["arms"][0]["name"], "full")
                self.assertTrue(all("skill_drops" not in a for a in by_id[base]["arms"]))

    def test_removing_line_ranges(self):
        self.assertEqual(run.drop_lines("1\n2\n3\n4\n5\n", "2-3,5"), "1\n4\n")

    def test_fisher_exact_matches_known_values(self):
        self.assertAlmostEqual(stats.fisher(5, 5, 0, 5), 2 / 252, places=6)
        self.assertAlmostEqual(stats.fisher(3, 5, 3, 5), 1.0, places=6)


class DecisionRuleTests(unittest.TestCase):
    def test_holm_adjustment(self):
        adjusted = stats.holm([0.01, 0.04, 0.03])
        self.assertEqual([round(p, 6) for p in adjusted], [0.03, 0.06, 0.06])

    def test_large_significant_gap_keeps_the_rule(self):
        self.assertEqual(stats.compare({"c": (25, 30, 5, 30)})["band"], "keep")

    def test_rule_that_hurts_is_harmful(self):
        self.assertEqual(stats.compare({"c": (5, 30, 25, 30)})["band"], "harmful")

    def test_gap_that_holm_correction_removes_is_inconclusive(self):
        # 18/30 against 8/30 is p = 0.0175 alone: below 0.05 but not below 0.01.
        self.assertEqual(stats.compare({"c": (18, 30, 8, 30)})["band"], "inconclusive")
        # Significant alone (p ~ 0.007); across three checks Holm lifts it above 0.01.
        alone = stats.compare({"c": (20, 30, 9, 30)})
        self.assertEqual(alone["band"], "keep")
        three = stats.compare({"c": (20, 30, 9, 30), "d": (15, 30, 15, 30), "e": (15, 30, 15, 30)})
        self.assertEqual(three["band"], "inconclusive")

    def test_no_difference_needs_thirty_sessions_per_arm(self):
        self.assertEqual(stats.compare({"c": (28, 30, 27, 30)})["band"], "within")
        self.assertEqual(stats.compare({"c": (28, 29, 27, 29)})["band"], "inconclusive")
        self.assertEqual(stats.compare({"c": (28, 30, 27, 30), "d": (20, 30, 15, 30)})["band"], "inconclusive")

    def test_rule_decision_needs_every_band_within_to_delete(self):
        self.assertEqual(stats.rule_decision(["within", "within"]), "delete")
        self.assertEqual(stats.rule_decision(["within", "within"], models=1), "within")
        self.assertEqual(stats.rule_decision(["within", "inconclusive"]), "inconclusive")
        self.assertEqual(stats.rule_decision(["within", "keep"]), "keep")
        self.assertEqual(stats.rule_decision(["harmful", "within"]), "reword")
        self.assertEqual(stats.rule_decision(["keep", "harmful"]), "conflict")
        self.assertEqual(stats.rule_decision([]), "untested")
        self.assertEqual(stats.rule_decision(["within", "untested"]), "inconclusive")
        self.assertEqual(stats.rule_decision(["conflict", "within"]), "conflict")

    def test_opposite_effects_in_one_scenario_are_a_conflict(self):
        self.assertEqual(stats.compare({"acted": (30, 30, 0, 30), "asked": (0, 30, 30, 30)})["band"], "conflict")


class DecisionAggregationTests(unittest.TestCase):
    """Decisions over run folders: what may and may not lead to deleting a rule."""

    SCENARIOS = [
        {"id": "a", "experiment": "exp", "rule": "r", "removal": "minus", "checks": {"c": "true"}, "arms": []},
        {"id": "b", "experiment": "exp", "rule": "r", "removal": "minus", "checks": {"c": "true"}, "arms": []},
    ]

    def folder(self, root: Path, name: str, rows: list[tuple[str, str, int, int]], prereg: str | None = "h",
               model: str = "m") -> Path:
        out = root / name
        (out / "results").mkdir(parents=True)
        (out / "baseline.json").write_text(json.dumps({"harness": "omp", "model": model, "smoke": False, "fixtures": {}}))
        for scenario, arm, passes, n in rows:
            for i in range(n):
                result = {"scenario": scenario, "arm": arm, "checks": {"c": i < passes}, "prereg": prereg}
                (out / "results" / f"{scenario}__{arm}__{i}.json").write_text(json.dumps(result))
        return out

    def decide(self, *outs: Path) -> dict:
        with mock.patch.object(run, "SCENARIOS", self.SCENARIOS), mock.patch.object(run, "prereg_hash", lambda *_a, **_k: "h"):
            return run.decisions(list(outs))

    def test_a_rule_is_not_deleted_while_one_of_its_scenarios_is_unrun(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self.folder(Path(tmp), "o", [("a", "full", 28, 30), ("a", "minus", 28, 30)])
            other = self.folder(Path(tmp), "q", [("a", "full", 28, 30), ("a", "minus", 28, 30)], model="m2")
            self.assertEqual(self.decide(out, other)["rules"]["r"], "inconclusive")
            both = self.folder(Path(tmp), "p", [("b", "full", 28, 30), ("b", "minus", 28, 30)])
            both2 = self.folder(Path(tmp), "p2", [("b", "full", 28, 30), ("b", "minus", 28, 30)], model="m2")
            self.assertEqual(self.decide(out, other, both, both2)["rules"]["r"], "delete")

    def test_no_rule_is_deleted_on_one_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self.folder(Path(tmp), "o", [("a", "full", 28, 30), ("a", "minus", 28, 30),
                                              ("b", "full", 28, 30), ("b", "minus", 28, 30)])
            self.assertEqual(self.decide(out)["rules"]["r"], "within")

    def test_results_without_a_preregistration_do_not_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self.folder(Path(tmp), "o", [("a", "full", 28, 30), ("a", "minus", 28, 30),
                                              ("b", "full", 28, 30), ("b", "minus", 28, 30)], prereg=None)
            self.assertEqual(self.decide(out)["rules"], {})

    def test_reruns_pool_instead_of_adding_a_second_test(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = self.folder(Path(tmp), "o", [("a", "full", 15, 15), ("a", "minus", 15, 15)])
            second = self.folder(Path(tmp), "p", [("a", "full", 15, 15), ("a", "minus", 15, 15)])
            bands = [b for b in self.decide(first, second)["bands"] if b["scenario"] == "a"]
            self.assertEqual(len(bands), 1)
            self.assertEqual(bands[0]["min_n"], 30)


class RunnerGuardTests(unittest.TestCase):
    def test_ledger_refuses_capped_sessions_at_the_ceiling(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = run.Ledger(Path(tmp) / "ledger.json", ceiling=1.0)
            ledger.admit("anthropic/claude-sonnet-5-5")
            ledger.add("anthropic/claude-sonnet-5-5", 0.6)
            ledger.add("openai-codex/gpt-6.1-sol", 5.0)
            ledger.admit("anthropic/claude-sonnet-5-5")
            ledger.add("anthropic/claude-sonnet-5-5", 0.5)
            with self.assertRaises(run.LedgerFull):
                ledger.admit("anthropic/claude-sonnet-5-5")
            ledger.admit("openai-codex/gpt-6.1-sol")  # plan usage is counted, not capped

    def test_a_folder_keeps_one_baseline(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            first = {"harness": "omp", "harness_version": "1", "model": "m", "smoke": False, "fixtures": {}}
            run.pin_baseline(out, first)
            run.pin_baseline(out, dict(first))
            with self.assertRaises(SystemExit):
                run.pin_baseline(out, dict(first, harness_version="2"))

    def test_scored_runs_need_a_preregistration(self):
        scenario = {"id": "x", "experiment": "no-such-experiment"}
        with self.assertRaises(SystemExit):
            run.prereg_hash(scenario, smoke=False)
        self.assertIsNone(run.prereg_hash(scenario, smoke=True))

    def test_changed_preregistration_voids_earlier_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, prereg = Path(tmp) / "out", Path(tmp) / "prereg"
            prereg.mkdir()
            (prereg / "exp.md").write_text("v1")
            scenario = {"id": "exp-scenario", "experiment": "exp", "checks": {}, "arms": []}
            with mock.patch.object(run, "PREREG", prereg), mock.patch.object(run, "SCENARIOS", [scenario]):
                (out / "results").mkdir(parents=True)
                result = {"scenario": "exp-scenario", "arm": "full", "checks": {}, "prereg": run.prereg_hash(scenario, False)}
                (out / "results" / "a.json").write_text(json.dumps(result))
                self.assertEqual(run.load_results(out)[1], 0)
                (prereg / "exp.md").write_text("v2")
                self.assertEqual(run.load_results(out)[1], 1)


if __name__ == "__main__":
    unittest.main()
