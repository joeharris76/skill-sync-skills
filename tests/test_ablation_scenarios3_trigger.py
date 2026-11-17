"""Shape and setup checks for the phase 3 trigger evaluation scenarios.

Standard library only; the setup run needs bash, git and uv, and skips where uv is not installed.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

ABLATION = Path(__file__).resolve().parents[1] / "evals" / "ablation"
sys.path.insert(0, str(ABLATION))

import scenarios3_trigger as trig  # noqa: E402

SCENARIOS = trig.SCENARIOS3_TRIGGER
IDENTITY = {"GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "T",
            "GIT_COMMITTER_EMAIL": "t@example.com", "GIT_CONFIG_GLOBAL": os.devnull}
PINNED_SKILLS = "a0c0d4b31b892557735732f367647d39132e2c9c"


class TriggerScenarioShape(unittest.TestCase):
    def test_twenty_prompts_per_skill_with_type_counts(self):
        self.assertEqual(len(SCENARIOS), 180)
        for skill in trig.SKILLS:
            kinds = Counter(s["kind"] for s in SCENARIOS if s["skill"] == skill)
            self.assertEqual(dict(kinds), {"explicit": 6, "implicit": 6, "contextual": 4, "near-miss": 4}, skill)
        self.assertEqual(set(s["skill"] for s in SCENARIOS), set(trig.SKILLS))

    def test_in_scope_skills(self):
        self.assertEqual(trig.SKILLS, ["change-framework", "review-protocol", "investigation-framework",
                                       "agent-execution", "session-takeover", "todo", "code", "test", "docs"])

    def test_ids_unique_and_prompts_unique_per_skill(self):
        ids = [s["id"] for s in SCENARIOS]
        self.assertEqual(len(ids), len(set(ids)))
        for skill in trig.SKILLS:
            prompts = [s["prompt"] for s in SCENARIOS if s["skill"] == skill]
            self.assertEqual(len(prompts), len(set(prompts)), skill)

    def test_single_full_arm_on_the_pins(self):
        for s in SCENARIOS:
            self.assertEqual(len(s["arms"]), 1)
            arm = s["arms"][0]
            self.assertEqual((arm["name"], arm["global"], arm["skills"], arm["fixture"]),
                             ("full", "full", PINNED_SKILLS, "global-phase3.md"))
        self.assertTrue((ABLATION / "fixtures" / "global-phase3.md").read_text().strip())

    def test_one_turn_and_no_decision_checks(self):
        for s in SCENARIOS:
            self.assertIsInstance(s["prompt"], str)
            self.assertNotIn("prompts", s)
            self.assertEqual(s["checks"], {})
            self.assertNotIn("rules", s)
            self.assertIn("read_by_path", s["metrics"])

    def test_prereg_file_exists(self):
        for s in SCENARIOS:
            self.assertTrue((ABLATION / "prereg" / f"{s['experiment']}.md").exists())

    def test_prompts_do_not_name_skills_or_ask_to_load_them(self):
        pattern = re.compile(r"skill|SKILL|shared-|change-framework|review-protocol|investigation-framework|"
                             r"agent-execution|session-takeover", re.I)
        for s in SCENARIOS:
            self.assertIsNone(pattern.search(s["prompt"]), s["prompt"])

    def test_no_private_text(self):
        for s in SCENARIOS:
            text = s["prompt"] + s["setup"]
            for bad in ("/Users/", "joeharris", "Joe", "BenchBox", "benchbox", "@gmail"):
                self.assertNotIn(bad, text.replace("Joe Harris", ""), s["id"])

    def test_setup_keys_exist(self):
        keys = {s["setup"] for s in SCENARIOS}
        self.assertTrue(keys <= set(trig.SETUPS.values()))
        self.assertEqual({k for k, v in trig.SETUPS.items() if v in keys}, set(trig.SETUPS))


class TriggerMetric(unittest.TestCase):
    def metric(self, skill: str, events: str) -> str:
        script = next(s for s in SCENARIOS if s["skill"] == skill)["metrics"]["read_by_path"]
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "out.jsonl").write_text(events)
            return subprocess.run(["bash", "-c", script], env=dict(os.environ, RUN=tmp), capture_output=True,
                                  text=True).stdout.strip()

    def test_counts_reads_by_uri_and_by_path(self):
        start = '{"type":"tool_execution_start","args":{"path":"%s"}}\n'
        self.assertEqual(self.metric("todo", start % "skill://todo"), "1")
        self.assertEqual(self.metric("todo", start % "skill://todo/batch.md"), "1")
        self.assertEqual(self.metric("code", start % "/x/skills/code/SKILL.md"), "1")
        self.assertEqual(self.metric("change-framework", start % "/x/skills/shared-change-framework/SKILL.md"), "1")

    def test_ignores_other_skills_and_non_calls(self):
        start = '{"type":"tool_execution_start","args":{"path":"%s"}}\n'
        self.assertEqual(self.metric("todo", start % "skill://test"), "0")
        self.assertEqual(self.metric("todo", ""), "0")
        # Text that merely mentions the skill, such as a catalogue in a message, is not a call.
        self.assertEqual(self.metric("todo", '{"type":"message_end","text":"skill://todo"}\n'), "0")


@unittest.skipUnless(shutil.which("uv") and shutil.which("git"), "base_setup.sh needs uv and git")
class TriggerSetupsRun(unittest.TestCase):
    def test_every_setup_runs_cleanly_on_the_base_repository(self):
        base = (ABLATION / "base_setup.sh").read_text()
        for name, setup in trig.SETUPS.items():
            if name == "tracker" and not shutil.which("tractable"):
                continue
            with self.subTest(setup=name), tempfile.TemporaryDirectory() as tmp:
                run = Path(tmp)
                repo = run / "repo"
                repo.mkdir()
                env = dict(os.environ, **IDENTITY, RUN=str(run), HARNESS=str(ABLATION))
                proc = subprocess.run(["bash", "-euo", "pipefail", "-c", base + "\n" + setup], cwd=repo, env=env,
                                      capture_output=True, text=True)
                self.assertEqual(proc.returncode, 0, proc.stderr[-400:])


if __name__ == "__main__":
    unittest.main()
