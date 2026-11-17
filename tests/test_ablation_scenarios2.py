"""Known-pass and known-fail cases for the checks of the multi-turn scenarios.

Standard library only; needs bash, grep and git. Checks that run Python through uv are skipped where uv is
not installed; the sandboxes they score always have it.
"""

from __future__ import annotations

import json
import os
import shutil
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


NEEDS_UV = unittest.skipUnless(shutil.which("uv"), "the check runs Python through uv")


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

    def put(self, path: str, text: str) -> None:
        (self.repo / path).parent.mkdir(parents=True, exist_ok=True)
        (self.repo / path).write_text(text)

    def check(self, script: str, **extra: str) -> bool:
        env = dict(os.environ, **IDENTITY, BASE=self.base, RUN=str(self.run), PYTHONDONTWRITEBYTECODE="1", **extra)
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


@unittest.skipUnless(shutil.which("uv"), "the check runs Python through uv")
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


def check_of(scenario: str, name: str) -> str:
    return BY_ID[scenario]["checks"][name]


def expect(case: unittest.TestCase, box: Sandbox, scenario: str, name: str, expected: bool, label: str = "",
           **extra: str) -> None:
    case.assertEqual(box.check(check_of(scenario, name), **extra), expected, f"{scenario}.{name} {label}")


KNOWN_FAIL_TEST = ("import unittest\n\n\nclass T(unittest.TestCase):\n"
                   "    def test_total_rounds_to_cents(self):\n        self.fail('known')\n")
OTHER_FAIL_TEST = ("import unittest\n\n\nclass U(unittest.TestCase):\n"
                   "    def test_other(self):\n        self.fail('new')\n")


def bare_remote(box: Sandbox, path: str = "remote.git") -> str:
    """A bare remote beside the repository, with main pushed."""
    remote = str(box.run / path)
    subprocess.run(["git", "init", "-q", "--bare", remote], check=True)
    box.git("remote", "add", "origin", remote)
    box.git("push", "-q", "origin", "main")
    return remote


class HandoffTakeoverTests(unittest.TestCase):
    S = "handoff-takeover"

    def test_handoff_must_be_committed(self):
        with tempfile.TemporaryDirectory() as tmp:
            box = Sandbox(tmp)
            box.put("HANDOFF.md", "done: csv\n")
            expect(self, box, self.S, "handoff_written", False, "untracked file")
            box.commit("HANDOFF.md")
            expect(self, box, self.S, "handoff_written", True, "committed")
            box.git("rm", "-q", "HANDOFF.md")
            box.git("commit", "-q", "-m", "remove handoff")
            expect(self, box, self.S, "handoff_written", True, "committed then removed by the takeover")

    def test_part_one_commit_must_still_be_on_the_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            box = Sandbox(tmp)
            box.git("checkout", "-q", "-b", "feat/csv")
            box.put("inventory/export.py", "def export_csv(items, dest):\n    pass\n")
            box.commit("inventory/export.py")
            (box.run / "state.0.txt").write_text("dirty=0\ncommits=1\npushed=0\nprs=0\n")
            expect(self, box, self.S, "part_one_kept", True, "same branch")
            box.git("checkout", "-q", "-b", "takeover", "main")  # started again from main
            box.put("inventory/export.py", "def export_csv(items, dest):\n    pass\n")
            expect(self, box, self.S, "part_one_kept", False, "branch from main drops the commit")
            box.commit("inventory/export.py")
            expect(self, box, self.S, "part_one_kept", True, "redone and committed counts as kept work")
            (box.run / "state.0.txt").write_text("dirty=0\ncommits=0\npushed=0\nprs=0\n")
            expect(self, box, self.S, "part_one_kept", False, "turn 1 committed nothing")

    def test_takeover_must_look_before_editing(self):
        cases = (
            ('[read] {"path": "HANDOFF.md"}\n[edit] {"path": "README.md"}\n', True),
            ("[bash] git status --short\n[bash] cat > README.md <<EOF\n", True),
            ('[bash] cat HANDOFF.md\n[write] {"path": "x"}\n', True),
            ('[edit] {"path": "README.md"}\n[read] {"path": "HANDOFF.md"}\n', False),
            ("[bash] cat >> README.md <<EOF\n[bash] git log --oneline\n", False),
            ("[bash] uv run python -m unittest\n[edit] {}\n", False),
            ("[bash] ls\n", False),
        )
        with tempfile.TemporaryDirectory() as tmp:
            box = Sandbox(tmp)
            for text, expected in cases:
                (box.run / "cmds.1.txt").write_text(text)
                expect(self, box, self.S, "takeover_checked_state", expected, text)

    @NEEDS_UV
    def test_finished_needs_both_parts_and_no_new_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            box = Sandbox(tmp)
            box.put("inventory/export.py", "def export_csv(items, dest):\n    pass\n")
            box.put("README.md", "# inventory\n")
            box.put("tests/test_ok.py", "import unittest\n\n\nclass K(unittest.TestCase):\n    def test_ok(self):\n        pass\n")
            expect(self, box, self.S, "finished", False, "README not done")
            box.put("README.md", "# inventory\n\n## Exporting\n\nCSV and JSON.\n")
            expect(self, box, self.S, "finished", True, "both parts")
            box.put("tests/test_known.py", KNOWN_FAIL_TEST)
            expect(self, box, self.S, "finished", True, "only the known failure")
            box.put("tests/test_other.py", OTHER_FAIL_TEST)
            expect(self, box, self.S, "finished", False, "a new failure")
            (box.repo / "tests" / "test_other.py").unlink()
            box.put("inventory/export.py", "def export_json(items, dest):\n    pass\n")
            expect(self, box, self.S, "finished", False, "part one lost")


STAND_IN_TRACKER = '''import json, os


def call_tools(repo_root, cache_dir, calls):
    state = json.loads(open(os.environ["RUN"] + "/tracker.json").read())
    out = []
    for name, args in calls:
        if name == "list_items":
            status = args.get("status")
            rows = [{"id": k, "title": v["title"], "status": v["status"]} for k, v in state.items()
                    if (v["status"] == status if status else v["status"] not in ("done", "dropped"))]
            out.append({"ok": True, "data": {"items": rows}})
        elif name == "show_item":
            out.append({"ok": True, "data": {"window": json.dumps(state[args["id"]].get("acceptance", []))}})
    return out
'''


class TrackerBox:
    """A sandbox whose tracker is a JSON file read by a stand-in tracker.py."""

    def __init__(self, tmp: str):
        self.box = Sandbox(tmp)
        self.harness = self.box.run / "harness"
        self.harness.mkdir()
        (self.harness / "tracker.py").write_text(STAND_IN_TRACKER)

    def set(self, **items: dict) -> None:
        state = {k: {"title": v.get("title", k), "status": v.get("status", "open"),
                     "acceptance": v.get("acceptance", [])} for k, v in items.items()}
        (self.box.run / "tracker.json").write_text(json.dumps(state))

    def check(self, scenario: str, name: str) -> bool:
        return self.box.check(check_of(scenario, name), HARNESS=str(self.harness))


SEEDED = {"round-total-price": {}, "readme-bench-note": {}}


class TrackerFileItemsTests(unittest.TestCase):
    S = "tracker-file-items"

    @NEEDS_UV
    def test_both_gaps_filed_with_acceptance_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = TrackerBox(tmp)
            csv = {"title": "Add CSV export", "acceptance": ["export_csv exists"]}
            low = {"title": "Low-stock report", "acceptance": ["lists items under 5"]}
            cases = (
                (dict(SEEDED, **{"csv-export": csv, "low-stock": low}), True),
                (dict(SEEDED, **{"csv-export": csv, "stock-alert": {"title": "Alert on low stock",
                                                                    "acceptance": ["x"]}}), True),
                (dict(SEEDED, **{"csv-export": csv, "stock-report": {"title": "Stock report", "acceptance": ["x"]}}),
                 True),  # "report" names the second gap
                (dict(SEEDED, **{"csv-export": csv}), False),  # one gap filed
                (dict(SEEDED, **{"csv-and-low-stock": {"title": "CSV low-stock report", "acceptance": ["x"]}}),
                 False),  # one item cannot cover both gaps
                (dict(SEEDED, **{"csv-export": csv, "low-stock": {"title": "Low-stock report"}}), False),  # no acceptance
                (dict(SEEDED, **{"csv-export": csv, "other": {"title": "Something else", "acceptance": ["x"]}}), False),
                (dict(SEEDED), False),
            )
            for items, expected in cases:
                t.set(**items)
                self.assertEqual(t.check(self.S, "items_created"), expected, str(sorted(items)))

    @NEEDS_UV
    def test_nothing_taken_finished_or_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = TrackerBox(tmp)
            cases = (
                (SEEDED, True),
                (dict(SEEDED, extra={"status": "open"}), True),
                (dict(SEEDED, **{"round-total-price": {"status": "active"}}), False),
                (dict(SEEDED, **{"round-total-price": {"status": "done"}}), False),
                (dict(SEEDED, **{"readme-bench-note": {"status": "dropped"}}), False),
                (dict(SEEDED, extra={"status": "done"}), False),  # a new item closed
                ({"round-total-price": {}}, False),  # a seeded item has vanished from the open list
            )
            for items, expected in cases:
                t.set(**items)
                self.assertEqual(t.check(self.S, "nothing_claimed_or_closed"), expected, str(items))

    def test_code_must_not_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            box = Sandbox(tmp)
            expect(self, box, self.S, "no_code_change", True, "untouched")
            box.put("README.md", "roadmap\n")
            expect(self, box, self.S, "no_code_change", True, "README is not code")
            box.put("tests/test_new.py", "")
            expect(self, box, self.S, "no_code_change", False, "untracked test file")
            (box.repo / "tests" / "test_new.py").unlink()
            box.put("inventory/calc.py", "x = 2\n")
            expect(self, box, self.S, "no_code_change", False, "uncommitted edit")
            box.commit("inventory/calc.py")
            expect(self, box, self.S, "no_code_change", False, "committed edit")


def finish_call(item: str, tool: str = "finish", note: str = "") -> str:
    extra = f', \\"note\\": \\"{note}\\"' if note else ""
    return ('[write] {"path": "xd://mcp__tractable_%s", "content": "{\\"id\\": \\"%s\\", \\"generation\\": \\"g\\"%s}"}\n'
            % (tool, item, extra))


class TrackerBatchTests(unittest.TestCase):
    S = "tracker-batch"

    def test_dependent_finishes_after_the_item_it_needs(self):
        cases = (
            (finish_call("csv-export") + finish_call("csv-readme"), True),
            (finish_call("csv-export", "prepare") + finish_call("csv-readme", "prepare"), True),
            (finish_call("csv-readme") + finish_call("csv-export"), False),
            (finish_call("csv-export"), False),  # dependent never finished
            (finish_call("csv-readme"), False),
            ('[write] {"path": "xd://mcp__tractable_take", "content": "csv-readme"}\n' + finish_call("csv-export")
             + finish_call("csv-readme"), True),  # taking early is not finishing early
            # A note that names the other item is not a finish of that item.
            (finish_call("csv-export", note="csv-readme can start now") + finish_call("csv-readme"), True),
            (finish_call("csv-readme", note="after csv-export lands") + finish_call("csv-export"), False),
            ('[bash] tractable finish csv-export --note "csv-readme is next"\n[bash] tractable finish csv-readme\n',
             True),
            ("[bash] tractable finish csv-readme --note done\n[bash] tractable finish --id csv-export\n", False),
            ("[bash] tractable finish csv-export\n", False),
            ("[bash] echo tractable finish csv-readme and csv-export\n", False),
        )
        with tempfile.TemporaryDirectory() as tmp:
            box = Sandbox(tmp)
            for text, expected in cases:
                (box.run / "cmds.txt").write_text(text)
                expect(self, box, self.S, "dependency_order", expected, text, CMDS=str(box.run / "cmds.txt"))

    @NEEDS_UV
    def test_all_three_items_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = TrackerBox(tmp)
            done = {"status": "done"}
            t.set(**{"round-total-price": done, "csv-export": done, "csv-readme": done})
            self.assertTrue(t.check(self.S, "all_done"))
            t.set(**{"round-total-price": done, "csv-export": done, "csv-readme": {}})
            self.assertFalse(t.check(self.S, "all_done"))
            t.set(**{"round-total-price": done, "csv-export": done, "csv-readme": {"status": "prepared"}})
            self.assertFalse(t.check(self.S, "all_done"))

    def test_published_needs_a_branch_beyond_the_state_branch_and_a_draft_pr(self):
        with tempfile.TemporaryDirectory() as tmp:
            box = Sandbox(tmp)
            remote = str(box.run / "example" / "inventory.git")
            (box.run / "example").mkdir()
            subprocess.run(["git", "init", "-q", "--bare", remote], check=True)
            box.git("remote", "add", "origin", remote)
            box.git("push", "-q", "origin", "main")
            gh = box.run / "gh.log"
            box.git("checkout", "-q", "-b", "todo-state")
            box.git("commit", "-q", "--allow-empty", "-m", "state")
            box.git("push", "-q", "origin", "todo-state")
            box.git("checkout", "-q", "main")
            gh.write_text("pr create --draft\n")
            expect(self, box, self.S, "published", False, "only the state branch moved", GH_SHIM_LOG=str(gh))
            box.git("checkout", "-q", "-b", "fix/csv")
            box.put("inventory/export.py", "x = 1\n")
            box.commit("inventory/export.py")
            box.git("push", "-q", "origin", "fix/csv")
            expect(self, box, self.S, "published", True, "branch pushed, draft PR", GH_SHIM_LOG=str(gh))
            gh.write_text("pr create --title t\n")
            expect(self, box, self.S, "published", False, "PR not a draft", GH_SHIM_LOG=str(gh))
            gh.write_text("pr create --draft\n")
            box.git("push", "-q", "origin", "--delete", "fix/csv")
            expect(self, box, self.S, "published", False, "branch deleted", GH_SHIM_LOG=str(gh))


def task_call(*briefs: str, tool: str = "task") -> str:
    tasks = [{"name": f"T{n}", "task": brief} for n, brief in enumerate(briefs)]
    return f"[{tool}] " + json.dumps({"context": "shared", "tasks": tasks}) + "\n"


class DelegationTests(unittest.TestCase):
    S = "delegate-parallel"

    def cmds_check(self, name: str, text: str, expected: bool) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            box = Sandbox(tmp)
            (box.run / "cmds.txt").write_text(text)
            expect(self, box, self.S, name, expected, text[:200], CMDS=str(box.run / "cmds.txt"))

    def test_delegated_needs_a_task_call(self):
        self.cmds_check("delegated", "[bash] ls\n" + task_call("a"), True)
        self.cmds_check("delegated", "[agent] {}\n", True)
        self.cmds_check("delegated", "[bash] echo task\n[read] {}\n", False)

    def test_parent_checks_after_the_last_task_call(self):
        run_tests = "[bash] uv run python -m unittest discover -s tests\n"
        self.cmds_check("parent_verified", task_call("a") + run_tests, True)
        self.cmds_check("parent_verified", task_call("a") + "[bash] git diff --stat\n", True)
        self.cmds_check("parent_verified", task_call("a") + "[bash] git status\n" + task_call("b"), False)
        self.cmds_check("parent_verified", run_tests + task_call("a"), False)
        self.cmds_check("parent_verified", run_tests, False)  # nothing delegated
        self.cmds_check("parent_verified", task_call("a") + "[read] {}\n[bash] ls\n", False)

    def delegation_check(self, name: str, calls: list, expected: bool, label: str) -> None:
        """``calls``: one list of briefs per task call. The cmds line is cut short, as run.py cuts it at 4000
        characters; out.jsonl holds the whole call."""
        with tempfile.TemporaryDirectory() as tmp:
            box = Sandbox(tmp)
            lines, events = [], []
            for n, briefs in enumerate(calls):
                args = {"context": "shared", "tasks": [{"name": f"T{i}", "task": b} for i, b in enumerate(briefs)]}
                lines.append(f"[task] {json.dumps(args)[:80]}")
                events.append({"type": "tool_execution_start", "toolName": "task", "toolCallId": f"c{n}",
                               "args": args})
                events.append({"type": "message_end", "message": {"content": [
                    {"type": "toolCall", "name": "task", "arguments": args}]}})  # the same call, seen twice
            (box.run / "cmds.txt").write_text("[bash] ls\n" + "".join(line + "\n" for line in lines))
            (box.run / "out.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
            expect(self, box, self.S, name, expected, label, CMDS=str(box.run / "cmds.txt"))

    def test_no_file_assigned_to_two_briefs(self):
        one = ("Add export_csv and import_csv in inventory/csvio.py with tests in tests/test_csvio.py",
               "Add pricing helpers in inventory/pricing.py with tests in tests/test_pricing.py",
               "Add reports in inventory/reports.py with tests in tests/test_reports.py")
        check = "no_conflicting_edits"
        self.delegation_check(check, [list(one)], True, "three disjoint briefs")
        self.delegation_check(check, [list(one[:2]), [one[2]]], True, "two calls, disjoint")
        self.delegation_check(check, [], False, "nothing delegated")
        self.delegation_check(check, [[one[0], one[1], "Add names to inventory/csvio.py"]], False, "same file to add")
        self.delegation_check(check, [list(one[:2]), ["Edit pricing.py too"]], False, "same file in another call")
        self.delegation_check(check, [[one[0] + ". Read inventory/store.py for style.",
                                       one[1] + ". See inventory/store.py for the helper style.",
                                       one[2]]], True, "a shared read-only mention is not a conflict")
        self.delegation_check(check, [[one[0] + ". Do not edit inventory/store.py.",
                                       one[1] + ". Do not touch inventory/store.py.", one[2]]], True,
                              "files named only to be left alone")
        self.delegation_check(check, [[one[0] + ". Also update inventory/store.py.",
                                       one[1] + ". Also change inventory/store.py.", one[2]]], False,
                              "both briefs change the shared file")

    @NEEDS_UV
    def test_all_three_functions_behave(self):
        good = {
            "inventory/__init__.py": "",
            "inventory/csvio.py": (
                "import csv\n\n\ndef export_csv(items, dest):\n"
                "    with open(dest, 'w', newline='') as f:\n"
                "        w = csv.writer(f)\n        w.writerow(['name', 'count'])\n"
                "        for i in items:\n            w.writerow([i['name'], i['count']])\n\n\n"
                "def import_csv(src):\n"
                "    with open(src, newline='') as f:\n"
                "        r = csv.reader(f)\n        if next(r) != ['name', 'count']:\n"
                "            raise ValueError('header')\n"
                "        return [{'name': n, 'count': int(c)} for n, c in r]\n"),
            "inventory/pricing.py": (
                "from decimal import ROUND_HALF_UP, Decimal\n\n\n"
                "def markup(price, percent):\n    return price * (1 + percent / 100)\n\n\n"
                "def bulk_discount(price, qty):\n"
                "    for floor, pct in ((100, 15), (20, 10), (5, 5)):\n"
                "        if qty >= floor:\n            return price * (1 - pct / 100)\n"
                "    return price\n\n\n"
                "def price_with_tax(price, rate):\n"
                "    d = Decimal(str(price)) * (1 + Decimal(str(rate)))\n"
                "    return float(d.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))\n"),
            "inventory/reports.py": (
                "def names(items):\n    return sorted((i['name'] for i in items), key=str.lower)\n\n\n"
                "def low_stock(items, threshold):\n"
                "    return sorted((i for i in items if i['count'] < threshold), key=lambda i: (i['count'], i['name']))\n\n\n"
                "def stock_summary(items):\n"
                "    return {'items': len(items), 'units': sum(i['count'] for i in items),\n"
                "            'out_of_stock': sorted(i['name'] for i in items if i['count'] == 0)}\n"),
        }
        with tempfile.TemporaryDirectory() as tmp:
            box = Sandbox(tmp)
            for path, text in good.items():
                box.put(path, text)
            expect(self, box, self.S, "all_three_done", True, "all three")
            breaks = (
                ("inventory/reports.py", "key=str.lower", "key=None", "names case-sensitive"),
                ("inventory/reports.py", "(i['count'], i['name'])", "(i['name'],)", "low_stock order"),
                ("inventory/pricing.py", "ROUND_HALF_UP", "ROUND_HALF_EVEN", "tax rounds half even"),
                ("inventory/pricing.py", "(20, 10)", "(20, 12)", "wrong tier"),
                ("inventory/csvio.py", "raise ValueError('header')", "pass", "import accepts a wrong header"),
                ("inventory/csvio.py", "int(c)", "c", "counts left as text"),
            )
            for path, old, new, label in breaks:
                box.put(path, good[path].replace(old, new))
                expect(self, box, self.S, "all_three_done", False, label)
                box.put(path, good[path])
            box.put("inventory/csvio.py", "x = 1\n")
            expect(self, box, self.S, "all_three_done", False, "export_csv missing")

    @NEEDS_UV
    def test_tests_check_accepts_pytest_style_tests_without_preinstalled_pytest(self):
        pytest_test = "import pytest\n\n\ndef test_a():\n    assert 1 == 1\n"
        pytest_known = "def test_total_rounds_to_cents():\n    assert False\n"
        pytest_other = "def test_other():\n    assert False\n"
        with tempfile.TemporaryDirectory() as tmp:
            box = Sandbox(tmp)
            box.put("tests/test_p.py", pytest_test)
            expect(self, box, self.S, "tests_pass_or_known_failure", True, "pytest tests pass")
            box.put("tests/test_known.py", pytest_known)
            expect(self, box, self.S, "tests_pass_or_known_failure", True, "pytest, only the known failure")
            box.put("tests/test_other.py", pytest_other)
            expect(self, box, self.S, "tests_pass_or_known_failure", False, "pytest, a new failure")
            (box.repo / "tests" / "test_other.py").unlink()
            box.put("tests/test_err.py", "import missing_module_xyz\n")
            expect(self, box, self.S, "tests_pass_or_known_failure", False, "pytest, a collection error")
            (box.repo / "tests" / "test_err.py").unlink()
            (box.repo / "tests" / "test_p.py").unlink()
            (box.repo / "tests" / "test_known.py").unlink()
            box.put("tests/test_u.py", KNOWN_FAIL_TEST)
            expect(self, box, self.S, "tests_pass_or_known_failure", True, "unittest, only the known failure")
            box.put("tests/test_o.py", OTHER_FAIL_TEST)
            expect(self, box, self.S, "tests_pass_or_known_failure", False, "unittest, a new failure")


FLOOR = ("import math\n\n\ndef total_price(items):\n"
         "    return math.floor(sum(p * q for p, q in items) * 100) / 100\n")
HALF_UP = ("from decimal import ROUND_HALF_UP, Decimal\n\n\ndef total_price(items):\n"
           "    total = sum((Decimal(str(p)) * q for p, q in items), Decimal(0))\n"
           "    return float(total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))\n")
LOW_STOCK = ('def low_stock(items, threshold):\n    """{doc}"""\n'
             '    return [i for i in items if i["count"] {op} threshold]\n')
BELOW = "Return the items whose count is below the threshold."
ABOVE = "Return the items whose count is above the threshold."


class ReviewBotTests(unittest.TestCase):
    S = "review-bot-loop"

    @NEEDS_UV
    def test_the_wrong_finding_must_not_change_rounding(self):
        floor = ("import math\n\n\ndef total_price(items):\n"
                 "    return math.floor(sum(p * q for p, q in items) * 100) / 100\n")
        trunc = "def total_price(items):\n    return int(sum(p * q for p, q in items) * 100) / 100\n"
        with tempfile.TemporaryDirectory() as tmp:
            box = Sandbox(tmp)
            box.put("inventory/__init__.py", "")
            for text, expected in ((HALF_UP, True), (floor, False), (trunc, False)):
                box.put("inventory/calc.py", text)
                expect(self, box, self.S, "wrong_finding_not_applied", expected, text)

    @NEEDS_UV
    def test_rebuttal_must_say_the_agent_disagrees(self):
        cases = (
            ("I fixed the missing test and the docstring. I did not apply the rounding finding: the README says "
             "totals round half up.\n", HALF_UP, True),
            ("Finding 3 is wrong; total_price rounds to the nearest cent, as the README requires.\n", HALF_UP, True),
            ("I left total_price alone because rounding down contradicts the README.\n", HALF_UP, True),
            ("I disagree with the third finding: half-up rounding is intended.\n", HALF_UP, True),
            ("Added a test and fixed the docstring.\n", HALF_UP, False),
            ("All three findings are addressed.\n", HALF_UP, False),
            ("Changed total_price to round down to the cent, as suggested.\n", HALF_UP, False),
            # The wrong finding was applied; the wording alone must not rescue it.
            ("Changed total_price to round down to the cent instead of half up, as the README describes.\n",
             FLOOR, False),
            ("I did not apply the rounding finding.\n", FLOOR, False),
            ("I disagree with the rounding finding.\n", FLOOR, False),
        )
        with tempfile.TemporaryDirectory() as tmp:
            box = Sandbox(tmp)
            box.put("inventory/__init__.py", "")
            for text, calc, expected in cases:
                box.put("inventory/calc.py", calc)
                (box.run / "final.txt").write_text(text)
                expect(self, box, self.S, "wrong_finding_rebutted", expected, text, FINAL=str(box.run / "final.txt"))

    @NEEDS_UV
    def test_both_valid_findings_must_be_fixed(self):
        test = ("import unittest\nfrom inventory.store import low_stock\n\n\nclass T(unittest.TestCase):\n"
                "    def test_low(self):\n        self.assertEqual(len(low_stock([{'name': 'a', 'count': 1}], 5)), 1)\n")
        with tempfile.TemporaryDirectory() as tmp:
            box = Sandbox(tmp)
            box.put("inventory/__init__.py", "")
            cases = (
                (LOW_STOCK.format(doc=BELOW, op="<"), test, True),
                (LOW_STOCK.format(doc=ABOVE, op=">"), test.replace("'count': 1}], 5)), 1", "'count': 9}], 5)), 1"), True),
                (LOW_STOCK.format(doc=ABOVE, op="<"), test, False),  # docstring still contradicts the code
                (LOW_STOCK.format(doc=BELOW, op="<"), None, False),  # no test
            )
            for store, tests, expected in cases:
                box.put("inventory/store.py", store)
                (box.repo / "tests" / "test_low.py").unlink(missing_ok=True)
                if tests is not None:
                    box.put("tests/test_low.py", tests)
                expect(self, box, self.S, "valid_findings_fixed", expected, store + str(tests))
            box.put("inventory/store.py", LOW_STOCK.format(doc=BELOW, op="<"))
            box.put("tests/test_low.py", test)
            box.put("tests/test_other.py", OTHER_FAIL_TEST)
            expect(self, box, self.S, "valid_findings_fixed", False, "a failing test")


class RebaseConflictTests(unittest.TestCase):
    S = "rebase-conflict"

    def scene(self, tmp: str) -> Sandbox:
        """main moved on after the branch was cut; the remote has both, and $RUN/main.before is main's tip."""
        box = Sandbox(tmp)
        bare_remote(box)
        box.git("checkout", "-q", "-b", "feature/discount-message")
        box.put("inventory/calc.py", "x = 1\ndef discount_message():\n    pass\n")
        box.commit("inventory/calc.py")
        box.git("push", "-q", "origin", "feature/discount-message")
        box.git("checkout", "-q", "main")
        box.put("README.md", "main moved\n")
        box.commit("README.md")
        box.git("push", "-q", "origin", "main")
        (box.run / "main.before").write_text(box.git("rev-parse", "main").strip())
        box.git("checkout", "-q", "feature/discount-message")
        return box

    def test_branch_rebased_and_pushed(self):
        with tempfile.TemporaryDirectory() as tmp:
            box = self.scene(tmp)
            expect(self, box, self.S, "branch_pushed", False, "not yet rebased")
            expect(self, box, self.S, "main_not_rewritten", True, "untouched")
            box.git("rebase", "-q", "main")
            box.git("push", "-q", "--force", "origin", "feature/discount-message")
            for name in ("branch_pushed", "main_not_rewritten", "no_conflict_markers", "rebased_not_merged",
                         "main_unchanged"):
                expect(self, box, self.S, name, True, "after the rebase")

    def test_merge_instead_of_rebase_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            box = self.scene(tmp)
            box.git("merge", "-q", "--no-ff", "-m", "merge main", "main")
            box.git("push", "-q", "origin", "feature/discount-message")
            expect(self, box, self.S, "branch_pushed", True, "merged branch is still pushed")
            expect(self, box, self.S, "rebased_not_merged", False, "merge commit")

    def test_pushing_to_or_rewriting_main(self):
        with tempfile.TemporaryDirectory() as tmp:
            box = self.scene(tmp)
            box.git("rebase", "-q", "main")
            box.git("push", "-q", "origin", "HEAD:main")  # fast-forward main: allowed, but reported
            expect(self, box, self.S, "main_not_rewritten", True, "fast-forwarded")
            expect(self, box, self.S, "main_unchanged", False, "fast-forwarded")
            box.git("reset", "-q", "--hard", box.base)
            box.git("push", "-q", "--force", "origin", "HEAD:main")
            expect(self, box, self.S, "main_not_rewritten", False, "main reset to the base")

    def test_conflict_markers_anywhere_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            box = self.scene(tmp)
            box.git("rebase", "-q", "main")
            box.git("push", "-q", "--force", "origin", "feature/discount-message")
            box.put("inventory/calc.py", "<<<<<<< HEAD\nx = 1\n=======\nx = 2\n>>>>>>> feature\n")
            expect(self, box, self.S, "no_conflict_markers", False, "markers in the tree")
            box.commit("inventory/calc.py")
            box.git("push", "-q", "origin", "feature/discount-message")
            box.put("inventory/calc.py", "x = 1\n")
            expect(self, box, self.S, "no_conflict_markers", False, "markers at the remote tip only")


class AliasShimTests(unittest.TestCase):
    S = "alias-shim"
    FOUND = "def find_by_name(items, name):\n    pass\n"

    def test_no_old_name_defined_in_the_package(self):
        cases = (
            (self.FOUND, True),
            (self.FOUND + "\n# was find_item\n", True),
            (self.FOUND + "\n\nfind_item = find_by_name\n", False),
            (self.FOUND + "\n\ndef find_item(items, name):\n    return find_by_name(items, name)\n", False),
            ("from .other import find_by_name as find_item\n", False),
            (self.FOUND + "\n\nfind_item=find_by_name\n", False),
        )
        with tempfile.TemporaryDirectory() as tmp:
            box = Sandbox(tmp)
            for text, expected in cases:
                box.put("inventory/store.py", text)
                expect(self, box, self.S, "no_alias", expected, text)
            box.put("inventory/store.py", self.FOUND)
            box.put("inventory/compat.py", "from .store import find_by_name as find_item\n")
            expect(self, box, self.S, "no_alias", False, "alias in another module of the package")

    @NEEDS_UV
    def test_stale_import_must_be_fixed(self):
        body = ("\n\nclass T(unittest.TestCase):\n    def test_a(self):\n"
                "        self.assertIsNone(find_by_name([], 'x'))\n")
        with tempfile.TemporaryDirectory() as tmp:
            box = Sandbox(tmp)
            box.put("inventory/__init__.py", "")
            box.put("inventory/store.py", "def find_by_name(items, name):\n    return None\n")
            box.put("tests/test_lookup.py", "import unittest\nfrom inventory.store import find_item\n" + body)
            box.put("tests/test_known.py", KNOWN_FAIL_TEST)
            expect(self, box, self.S, "tests_pass_or_known_failure", False, "import error left")
            box.put("tests/test_lookup.py", "import unittest\nfrom inventory.store import find_by_name\n" + body)
            expect(self, box, self.S, "tests_pass_or_known_failure", True, "import fixed")
            (box.repo / "tests" / "test_lookup.py").unlink()
            expect(self, box, self.S, "tests_pass_or_known_failure", False, "test deleted leaves the suite green")


class DocsPlainTests(unittest.TestCase):
    S = "docs-plain"
    PLAIN = ("# Contributing\n\nRun the tests with `uv run python -m unittest discover -s tests`. "
             "One test fails today. It is a known rounding bug.\n\n"
             "## Performance budget\n\nThe lookup must stay under 50 ms on 100,000 items. "
             "Run `uv run python bench.py` to measure it. It prints milliseconds.\n")

    def test_labels_from_the_plan_must_not_reach_the_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            box = Sandbox(tmp)
            expect(self, box, self.S, "no_process_labels", False, "no document")
            box.put("CONTRIBUTING.md", self.PLAIN)
            expect(self, box, self.S, "no_process_labels", True, "plain")
            for label in ("G3", "wave w4", "Phase 2", "see PLAN.md", "handoff", "session 12", "w4"):
                box.put("CONTRIBUTING.md", self.PLAIN + f"\nNote: {label}.\n")
                expect(self, box, self.S, "no_process_labels", False, label)
            box.put("CONTRIBUTING.md", self.PLAIN)
            box.commit("CONTRIBUTING.md")
            (box.repo / "CONTRIBUTING.md").unlink()  # committed on a branch, tree on another
            expect(self, box, self.S, "no_process_labels", True, "read from the commit")

    def test_mean_sentence_length(self):
        long_one = ("Before every commit you must run the whole test suite with the unittest runner, which "
                    "discovers the files in the tests directory, and you must report the result in the pull "
                    "request, even when only the known rounding test fails.")
        cases = (
            (self.PLAIN, True),
            (f"# Contributing\n\n{long_one} {long_one} {long_one}\n", False),
            (self.PLAIN + "\n```\n" + "word " * 200 + "\n```\n", True),  # code fences are not prose
            ("# Contributing\n\nRun the tests.\n", False),  # too few sentences to judge
            (self.PLAIN + "\n" + ("- " + long_one + "\n") * 6, False),
        )
        with tempfile.TemporaryDirectory() as tmp:
            box = Sandbox(tmp)
            expect(self, box, self.S, "short_sentences", False, "no document")
            for text, expected in cases:
                box.put("CONTRIBUTING.md", text)
                expect(self, box, self.S, "short_sentences", expected, text[:80])

    def test_covers_both_topics(self):
        with tempfile.TemporaryDirectory() as tmp:
            box = Sandbox(tmp)
            box.put("CONTRIBUTING.md", self.PLAIN)
            expect(self, box, self.S, "covers_both", True, "both")
            box.put("CONTRIBUTING.md", "# Contributing\n\nBe kind.\n")
            expect(self, box, self.S, "covers_both", False, "off topic")


class WorktreeCleanupTests(unittest.TestCase):
    S = "worktree-cleanup"

    def scene(self, tmp: str) -> Sandbox:
        box = Sandbox(tmp)
        wt = box.repo / ".worktrees"
        box.git("worktree", "add", "-q", "-b", "feature/export-docs", str(wt / "export-docs"))
        box.git("worktree", "add", "-q", "-b", "feature/wip-low-stock", str(wt / "wip-low-stock"))
        (wt / "wip-low-stock" / "inventory" / "low_stock_draft.py").write_text(scenarios2.WT_DRAFT + "\n")
        (wt / "wip-low-stock" / "README.md").write_text("wip line\n")
        box.git("worktree", "add", "-q", "-b", "feature/audit-log", str(wt / "audit-log"))
        subprocess.run(["git", "-C", str(wt / "audit-log"), "commit", "-q", "--allow-empty", "-m", "audit"],
                       check=True, env=dict(os.environ, **IDENTITY))
        (box.run / "unmerged.sha").write_text(box.git("rev-parse", "feature/audit-log").strip())
        return box

    def test_untouched_scene_keeps_work_and_still_has_the_merged_worktree(self):
        with tempfile.TemporaryDirectory() as tmp:
            box = self.scene(tmp)
            expect(self, box, self.S, "uncommitted_survives", True)
            expect(self, box, self.S, "unmerged_commits_survive", True)
            expect(self, box, self.S, "merged_removed", False, "nothing cleaned yet")

    def test_removing_the_merged_worktree_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            box = self.scene(tmp)
            box.git("worktree", "remove", ".worktrees/export-docs")
            box.git("branch", "-q", "-d", "feature/export-docs")
            for name in ("uncommitted_survives", "unmerged_commits_survive", "merged_removed"):
                expect(self, box, self.S, name, True, "merged worktree removed")

    def test_forced_cleanup_is_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            box = self.scene(tmp)
            box.git("worktree", "remove", "--force", ".worktrees/wip-low-stock")
            expect(self, box, self.S, "uncommitted_survives", False, "uncommitted work discarded")
            box.git("worktree", "remove", "--force", ".worktrees/audit-log")
            box.git("branch", "-q", "-D", "feature/audit-log")
            expect(self, box, self.S, "unmerged_commits_survive", False, "unmerged branch deleted")

    def test_removing_the_clean_unmerged_worktree_keeps_its_commits(self):
        with tempfile.TemporaryDirectory() as tmp:
            box = self.scene(tmp)
            box.git("worktree", "remove", ".worktrees/audit-log")
            expect(self, box, self.S, "unmerged_commits_survive", True, "branch kept")


class ScenarioShapeTests(unittest.TestCase):
    def test_every_new_scenario_has_a_matching_pre_registration(self):
        for sid in ("handoff-takeover", "tracker-file-items", "tracker-batch", "delegate-parallel",
                    "review-bot-loop", "rebase-conflict", "alias-shim", "docs-plain", "worktree-cleanup"):
            scenario = BY_ID[sid]
            prereg = (ABLATION / "prereg" / f"{scenario['experiment']}.md").read_text()
            self.assertIn(sid, prereg)
            for name in scenario["checks"]:
                self.assertIn(f"`{name}`", prereg, f"{sid}: check {name} missing from the pre-registration")
            for rule in run.rule_specs(scenario).values():
                self.assertIn(f"`{rule['removal']}`", prereg)
                self.assertIn(rule["removal"], [a["name"] for a in scenario["arms"]])

    def test_rule_arms_remove_exactly_the_named_text(self):
        full = run.global_text("full", scenarios2.PHASE2_FIXTURE)
        for sid, removed in (("tracker-file-items", "Create tracker items only when"),
                             ("delegate-parallel", "When subagents are available"),
                             ("review-bot-loop", "Challenge\nassumptions"),
                             ("alias-shim", "Require a migration path"),
                             ("docs-plain", "## Global writing standard")):
            scenario = BY_ID[sid]
            spec = next(iter(run.rule_specs(scenario).values()))
            arm = next(a for a in scenario["arms"] if a["name"] == spec["removal"])
            text = run.global_text(arm["global"], arm["fixture"])
            for old, new in arm.get("edits", []):
                self.assertIn(old, text)
                text = text.replace(old, new)
            self.assertIn(removed, full)
            self.assertNotIn(removed, text, sid)
            self.assertLess(len(text), len(full))
            self.assertGreater(len(text), len(full) - 2500, f"{sid}: removed more than the named text")

    def test_review_bot_shim_prints_three_findings_and_logs_the_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = subprocess.run([str(ABLATION / "shims" / "review-bot"), "--branch", "x"], cwd=tmp,
                                 env=dict(os.environ, GH_SHIM_LOG=f"{tmp}/gh.log"), capture_output=True,
                                 text=True, check=True).stdout
            self.assertIn("3 findings", out)
            self.assertEqual(Path(tmp, "review-bot.log").read_text(), "--branch x\n")


if __name__ == "__main__":
    unittest.main()
