"""Claude Code stream-json parsing and per-harness command construction for the ablation runner.

The sample is a recorded headless run: one Bash call, then a final answer.
Standard library only.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ABLATION = Path(__file__).resolve().parents[1] / "evals" / "ablation"
sys.path.insert(0, str(ABLATION))

import run  # noqa: E402

SAMPLE = Path(__file__).parent / "data" / "claude_stream_sample.jsonl"
CC = run.ClaudeCode


class StreamParsing(unittest.TestCase):
    def setUp(self):
        self.events = run.parse_events(SAMPLE.read_text())

    def test_final_text_is_last_assistant_message(self):
        self.assertEqual(CC.final_text(self.events), "PLUMBUS\n\n`a.txt` says: \"marker file\".")

    def test_commands_use_the_omp_line_format(self):
        self.assertEqual(CC.bash_commands(self.events), "[bash] cat a.txt\n")
        self.assertEqual(CC.tool_calls(self.events), 1)

    def test_cost_comes_from_the_result_event(self):
        self.assertAlmostEqual(CC.turn_cost(self.events), 0.0277358)

    def test_model_comes_from_init_and_messages(self):
        self.assertEqual(CC.answered(self.events), {"claude-sonnet-5-5"})

    def test_finished_needs_a_successful_result(self):
        self.assertTrue(CC.finished(self.events))
        self.assertFalse(CC.finished([e for e in self.events if e["type"] != "result"]))
        self.assertFalse(CC.finished([{"type": "result", "subtype": "error_max_budget_usd", "is_error": True}]))

    def test_other_model_in_usage_is_seen(self):
        events = self.events + [{"type": "result", "modelUsage": {"claude-haiku-4-5": {}}}]
        self.assertEqual(CC.answered(events), {"claude-sonnet-5-5", "claude-haiku-4-5"})

    def test_skill_call_is_a_skill_url_line(self):
        events = [{"type": "assistant", "message": {"id": "m", "content": [
            {"type": "tool_use", "id": "t", "name": "Skill", "input": {"skill": "review-protocol"}}]}}]
        self.assertEqual(CC.bash_commands(events), "[skill] skill://review-protocol\n")
        self.assertEqual(CC.skills_read(events, []), ["review-protocol"])

    def test_truncated_final_line_is_ignored(self):
        self.assertEqual(len(run.parse_events(SAMPLE.read_text() + '{"type": "assi')), len(self.events))

    def test_isolation_refuses_user_plugins_and_mcp(self):
        init = {"type": "system", "subtype": "init", "plugins": [{"name": "x", "path": "/home/u/.claude/plugins/x"}]}
        with self.assertRaises(RuntimeError):
            CC.check_isolation([init])
        with self.assertRaises(RuntimeError):
            CC.check_isolation([{**init, "plugins": [], "mcp_servers": [{"name": "m"}]}])
        CC.check_isolation(self.events)


class Commands(unittest.TestCase):
    def harness(self):
        tmp = Path(tempfile.mkdtemp())
        return CC(tmp, tmp / "repo")

    def test_turns_resume_the_first_session(self):
        h = self.harness()
        first = h.command("p", 0, 2, "anthropic/claude-sonnet-5-5", fresh=True)
        later = h.command("p", 1, 2, "anthropic/claude-sonnet-5-5")
        self.assertEqual(first[first.index("--session-id") + 1], h.session)
        self.assertEqual(later[later.index("--resume") + 1], h.session)
        self.assertEqual(first[first.index("--model") + 1], "claude-sonnet-5-5")

    def test_a_fresh_turn_starts_a_new_session_and_later_turns_resume_it(self):
        h = self.harness()
        first = h.command("p", 0, 3, "anthropic/claude-sonnet-5-5", fresh=True)
        taken_over = h.command("p", 1, 3, "anthropic/claude-sonnet-5-5", fresh=True)
        later = h.command("p", 2, 3, "anthropic/claude-sonnet-5-5")
        new = taken_over[taken_over.index("--session-id") + 1]
        self.assertNotEqual(new, first[first.index("--session-id") + 1])
        self.assertEqual(later[later.index("--resume") + 1], new)

    def test_only_anthropic_models(self):
        with self.assertRaises(SystemExit):
            CC.check_model("openai-codex/gpt-6")

    def test_omp_turns_continue_and_a_fresh_turn_uses_a_new_session_directory(self):
        tmp = Path(tempfile.mkdtemp())
        h = run.Omp(tmp, tmp / "repo")
        first = h.command("p", 0, 3, "m", fresh=True)
        later = h.command("p", 1, 3, "m")
        taken_over = h.command("p", 2, 3, "m", fresh=True)
        self.assertEqual(first[3:6], ["omp", "-p", "--mode"])
        self.assertNotIn("--continue", first)
        self.assertIn("--continue", later)
        self.assertEqual(later[later.index("--session-dir") + 1], first[first.index("--session-dir") + 1])
        self.assertNotIn("--continue", taken_over)
        self.assertNotEqual(taken_over[taken_over.index("--session-dir") + 1], first[first.index("--session-dir") + 1])
        self.assertEqual(later[-1], "p")

    def test_resumed_turns_charge_only_the_difference(self):
        h = self.harness()
        total = lambda x: [{"type": "result", "total_cost_usd": x}]  # noqa: E731
        self.assertAlmostEqual(h.charge(total(0.04)), 0.04)
        self.assertAlmostEqual(h.charge(total(0.065)), 0.025)
        self.assertAlmostEqual(h.charge(total(0.065)), 0.0)
        self.assertAlmostEqual(CC.turn_cost(total(0.04) + total(0.065)), 0.065)

    def test_turn_without_result_is_charged_the_budget(self):
        self.assertEqual(self.harness().charge([]), run.MAX_TURN_BUDGET)

    def test_redact_handles_bytes_and_none(self):
        h = self.harness()
        h._token = "secret-token"
        self.assertEqual(h.redact(b"x secret-token"), "x [redacted]")
        self.assertEqual(h.redact(None), "")

    def test_token_is_redacted(self):
        h = self.harness()
        h._token = "secret-token"
        self.assertEqual(h.redact("a secret-token b"), "a [redacted] b")


if __name__ == "__main__":
    unittest.main()
