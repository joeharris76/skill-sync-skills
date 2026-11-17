"""Judged checks of the ablation eval: caching, the calibration gate, what the judge may see.

The judge model is replaced by a stub, so these tests make no model calls.
Standard library only.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ABLATION = Path(__file__).resolve().parents[1] / "evals" / "ablation"
sys.path.insert(0, str(ABLATION))

import judge  # noqa: E402
import run  # noqa: E402

SPEC = {"rubric": "Pass if the reply says hello.", "evidence": 'echo "reply: hello from $RUN"; echo "result: demo__secret-arm__0.json"'}
SCENARIO = {"id": "demo", "judged": {"demo-check": SPEC}}


def stub(verdict="pass"):
    return mock.patch.object(judge, "ask_judge", return_value=({"verdict": verdict, "reason": "stub"}, 0.5))


def write_summary(directory: Path, name: str, spec: dict, **over) -> None:
    summary = {"n": 40, "passes": 20, "fails": 20, "agreement": 0.95,
               "rubric": judge.rubric_hash(spec), "script": judge.script_hash(spec), **over}
    (directory / f"{name}.json").write_text(json.dumps(summary))


class CacheTests(unittest.TestCase):
    def test_same_rubric_and_evidence_is_judged_once(self):
        with tempfile.TemporaryDirectory() as tmp, stub() as ask:
            cache = Path(tmp)
            first = judge.judge("rubric", "evidence", cache)
            second = judge.judge("rubric", "evidence", cache)
            self.assertEqual(ask.call_count, 1)
            self.assertFalse(first["cached"])
            self.assertTrue(second["cached"])
            self.assertEqual(second["verdict"], "pass")

    def test_changed_rubric_or_evidence_is_judged_again(self):
        with tempfile.TemporaryDirectory() as tmp, stub() as ask:
            cache = Path(tmp)
            judge.judge("rubric", "evidence", cache)
            judge.judge("rubric two", "evidence", cache)
            judge.judge("rubric", "evidence two", cache)
            self.assertEqual(ask.call_count, 3)

    def test_each_call_is_recorded_in_the_ledger_as_uncapped_spend(self):
        with tempfile.TemporaryDirectory() as tmp, stub():
            ledger = run.Ledger(Path(tmp) / "ledger.json")
            judge.judge("rubric", "evidence", Path(tmp) / "cache", ledger)
            judge.judge("rubric", "evidence", Path(tmp) / "cache", ledger)  # cached: no second charge
            data = json.loads((Path(tmp) / "ledger.json").read_text())
            self.assertEqual(data["uncapped_usd"], 0.5)
            self.assertEqual(data["capped_usd"], 0.0)
            self.assertEqual(data["turns"], 1)

    def test_a_judge_from_the_agents_provider_is_refused(self):
        with self.assertRaises(judge.JudgeError):
            judge.ask_judge("rubric", "evidence", model="anthropic/claude-sonnet-5-5")

    def test_verdict_is_read_from_json_inside_other_text(self):
        got = judge.parse_verdict('Here you go:\n```json\n{"verdict": "FAIL", "reason": "no  claim\\nmade"}\n```')
        self.assertEqual(got, {"verdict": "fail", "reason": "no claim made"})
        with self.assertRaises(judge.JudgeError):
            judge.parse_verdict("looks fine to me")


class UsableGateTests(unittest.TestCase):
    def run_judged(self, calibration: Path, tmp: Path):
        repo = tmp / "repo"
        repo.mkdir(exist_ok=True)
        return judge.run_judged(SCENARIO, "arm-x", "demo__arm-x__0", repo, {"RUN": str(tmp / "run"), "PATH": "/usr/bin:/bin"},
                                tmp / "run", None, tmp / "out", tmp / "cache", calibration=calibration)

    def test_uncalibrated_check_never_enters_the_checks(self):
        with tempfile.TemporaryDirectory() as t, stub() as ask:
            tmp = Path(t)
            (tmp / "cal").mkdir()
            checks, details, unusable = self.run_judged(tmp / "cal", tmp)
            self.assertEqual((checks, details), ({}, {}))
            self.assertEqual(unusable, {"demo-check": "not calibrated"})
            ask.assert_not_called()
            self.assertTrue(list((tmp / "out" / "evidence").glob("*__demo-check.txt")))  # evidence is kept for labelling

    def test_low_agreement_or_few_examples_are_unusable(self):
        for over, expect in [({"agreement": 0.85}, "agreement 0.85"), ({"passes": 14, "fails": 26}, "has 14 and 26"),
                             ({"passes": 30, "fails": 3}, "has 30 and 3")]:
            with self.subTest(over=over), tempfile.TemporaryDirectory() as t, stub() as ask:
                tmp = Path(t)
                (tmp / "cal").mkdir()
                write_summary(tmp / "cal", "demo-check", SPEC, **over)
                checks, _, unusable = self.run_judged(tmp / "cal", tmp)
                self.assertEqual(checks, {})
                self.assertIn(expect, unusable["demo-check"])
                ask.assert_not_called()

    def test_summary_that_claims_usable_cannot_override_the_numbers(self):
        with tempfile.TemporaryDirectory() as t, stub():
            tmp = Path(t)
            (tmp / "cal").mkdir()
            write_summary(tmp / "cal", "demo-check", SPEC, agreement=0.5, usable=True)
            self.assertEqual(self.run_judged(tmp / "cal", tmp)[0], {})

    def test_calibration_for_another_rubric_is_unusable(self):
        with tempfile.TemporaryDirectory() as t, stub():
            tmp = Path(t)
            (tmp / "cal").mkdir()
            write_summary(tmp / "cal", "demo-check", {**SPEC, "rubric": "an older rubric"})
            checks, _, unusable = self.run_judged(tmp / "cal", tmp)
            self.assertEqual(checks, {})
            self.assertIn("another rubric", unusable["demo-check"])

    def test_calibrated_check_adds_its_verdict(self):
        with tempfile.TemporaryDirectory() as t, stub("fail"):
            tmp = Path(t)
            (tmp / "cal").mkdir()
            write_summary(tmp / "cal", "demo-check", SPEC)
            checks, details, unusable = self.run_judged(tmp / "cal", tmp)
            self.assertEqual(checks, {"demo-check": False})
            self.assertEqual(details["demo-check"]["reason"], "stub")
            self.assertEqual(unusable, {})

    def test_a_judge_error_leaves_the_check_out_rather_than_failing_it(self):
        with tempfile.TemporaryDirectory() as t, mock.patch.object(judge, "ask_judge", side_effect=judge.JudgeError("down")):
            tmp = Path(t)
            (tmp / "cal").mkdir()
            write_summary(tmp / "cal", "demo-check", SPEC)
            checks, _, unusable = self.run_judged(tmp / "cal", tmp)
            self.assertEqual(checks, {})
            self.assertIn("judge error", unusable["demo-check"])

    def test_shipped_checks_start_out_unusable_without_calibration(self):
        with tempfile.TemporaryDirectory() as t:
            for sc in run.SCENARIOS2:
                for name, spec in sc.get("judged", {}).items():
                    self.assertFalse(judge.usable(name, spec, Path(t))[0], name)


class EvidenceTests(unittest.TestCase):
    def test_evidence_never_carries_the_arm_name_the_run_path_or_global_text(self):
        global_text = "# Global Agent Preferences\n\nAlways answer in a way that flatters the reader.\nShort.\n"
        raw = ("reply: Always answer in a way that flatters the reader.\n"
               "ran in /private/tmp/omp-ablation/abc123def456/repo, saved as demo__Careful-Arm__2.json\n"
               "the full suite has none failing\n"
               "$ ls\nGLOBAL.md\nREADME.md\n")
        out = judge.scrub(raw, run="/tmp/omp-ablation/abc123def456", arm="careful-arm", global_text=global_text)
        self.assertNotIn("flatters", out)
        self.assertNotIn("abc123def456", out)
        self.assertNotIn("omp-ablation", out)
        self.assertNotIn("careful-arm", out.lower())
        self.assertNotIn("GLOBAL.md", out)
        self.assertIn("README.md", out)
        self.assertIn("the full suite has none failing", out)  # plain words are not arm markers

    def test_evidence_written_for_labelling_is_scrubbed_end_to_end(self):
        with tempfile.TemporaryDirectory() as t, stub():
            tmp = Path(t)
            (tmp / "cal").mkdir()
            repo = tmp / "repo"
            repo.mkdir()
            run_dir = tmp / "abc123"
            env = {"RUN": str(run_dir), "PATH": "/usr/bin:/bin"}
            judge.run_judged(SCENARIO, "secret-arm", "demo__secret-arm__0", repo, env, run_dir,
                             "Be nice to everyone always.\n", tmp / "out", tmp / "cache", calibration=tmp / "cal")
            text = (tmp / "out" / "evidence" / "demo__secret-arm__0__demo-check.txt").read_text()
            self.assertNotIn("secret-arm", text)
            self.assertNotIn("abc123", text)
            self.assertIn("hello", text)

    def test_the_prompt_sent_to_the_judge_holds_only_rubric_and_evidence(self):
        prompt = judge.prompt_for("the rubric", "the evidence")
        self.assertEqual(prompt, "# Rubric\n\nthe rubric\n\n# Evidence\n\nthe evidence\n")

    def test_a_very_long_excerpt_is_cut_in_the_middle(self):
        out = judge.scrub("a" * 50000)
        self.assertLessEqual(len(out), judge.MAX_EVIDENCE + 40)
        self.assertIn("[... cut ...]", out)


class AgreementTests(unittest.TestCase):
    def test_agreement_counts_matching_verdicts(self):
        got = judge.agreement(["pass", "pass", "fail", "fail"], ["pass", "fail", "fail", "fail"])
        self.assertEqual(got, {"n": 4, "passes": 2, "fails": 2, "agreement": 0.75})

    def test_gate_needs_agreement_and_fifteen_of_each_label(self):
        self.assertEqual(judge.gate({"passes": 15, "fails": 15, "agreement": 0.90}), (True, ""))
        self.assertFalse(judge.gate({"passes": 15, "fails": 15, "agreement": 0.899})[0])
        self.assertFalse(judge.gate({"passes": 14, "fails": 40, "agreement": 1.0})[0])

    def test_calibrate_reproduces_agreement_from_the_stored_labels(self):
        with tempfile.TemporaryDirectory() as t:
            cal = Path(t)
            rows = [{"evidence": f"e{i}", "label": "pass" if i % 2 else "fail", "reason": "r", "script": judge.script_hash(SPEC)}
                    for i in range(40)]
            judge.write_rows(cal / "demo-check.jsonl", rows)

            def fake(rubric, evidence, model=judge.JUDGE_MODEL, timeout=600):
                i = int(evidence[1:])
                wrong = i in (3, 8)  # two disagreements in 40
                label = "pass" if i % 2 else "fail"
                return {"verdict": ("fail" if label == "pass" else "pass") if wrong else label, "reason": "stub"}, 0.0

            with mock.patch.object(judge, "ask_judge", side_effect=fake), \
                    mock.patch.object(judge, "scenario_spec", return_value=SPEC):
                summary = judge.calibrate("demo-check", jobs=2, calibration=cal)
                again = judge.calibrate("demo-check", jobs=2, calibration=cal)  # from the verdict cache
            self.assertEqual((summary["n"], summary["passes"], summary["fails"], summary["agreement"]), (40, 20, 20, 0.95))
            self.assertTrue(summary["usable"])
            self.assertEqual(again["agreement"], 0.95)
            self.assertEqual(len(summary["disagreements"]), 2)
            self.assertEqual(json.loads((cal / "demo-check.json").read_text())["agreement"], 0.95)
            self.assertTrue(judge.usable("demo-check", SPEC, cal)[0])

    def test_calibrate_refuses_unlabelled_or_stale_rows(self):
        with tempfile.TemporaryDirectory() as t, mock.patch.object(judge, "scenario_spec", return_value=SPEC):
            cal = Path(t)
            judge.write_rows(cal / "demo-check.jsonl", [{"evidence": "e", "label": None, "reason": "", "script": judge.script_hash(SPEC)}])
            with self.assertRaises(SystemExit):
                judge.calibrate("demo-check", calibration=cal)
            judge.write_rows(cal / "demo-check.jsonl", [{"evidence": "e", "label": "pass", "reason": "r", "script": "old"}])
            with self.assertRaises(SystemExit):
                judge.calibrate("demo-check", calibration=cal)


class ResultHashTests(unittest.TestCase):
    def test_scenarios_without_judged_checks_keep_their_old_hash(self):
        import hashlib
        scenario = {"checks": {"a": "true"}, "rules": {"r": {"removal": "minus"}}}
        scored = {"checks": {"a": "true"}, "rules": {"r": {"removal": "minus"}}}
        old = hashlib.sha256(json.dumps(scored, sort_keys=True).encode()).hexdigest()[:16]
        self.assertEqual(run.checks_hash(scenario), old)

    def test_editing_a_rubric_changes_the_hash_so_old_results_are_dropped(self):
        one = {"checks": {}, "judged": {"c": {"rubric": "a", "evidence": "echo"}}}
        two = {"checks": {}, "judged": {"c": {"rubric": "b", "evidence": "echo"}}}
        self.assertNotEqual(run.checks_hash(one), run.checks_hash(two))

    def test_report_lists_only_judged_checks_that_every_result_has(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            (out / "results").mkdir(parents=True)
            scenario = next(s for s in run.SCENARIOS if s["id"] == "review-planted")
            base = {"scenario": "review-planted", "arm": "none", "model": "m", "run": "", "turns": 1, "prereg": None,
                    "checks_hash": run.checks_hash(scenario), "metrics": {}, "cost": 0.0, "tool_calls": 0, "skills_read": []}
            (out / "results" / "a.json").write_text(json.dumps({**base, "rep": 0, "checks": {"no_changes": True}}))
            with mock.patch("builtins.print") as shown:
                run.report_folder(out)
            header = next(c.args[0] for c in shown.call_args_list if c.args and str(c.args[0]).startswith("| arm"))
            self.assertIn("no_changes", header)
            self.assertNotIn("review-findings-match", header)  # unusable: no verdict in the result


if __name__ == "__main__":
    unittest.main()
