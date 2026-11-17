"""Phase 3 families built by scenarios3_cf: arm spans, scenario shape, and a known-pass and known-fail case for
every decision check.

Each check test builds the scenario's real sandbox (base_setup.sh plus the scenario's setup, as run.py does) and
then acts the way an agent could, with git, the tool-call log and, for tracker scenarios, the real tracker server.
Needs bash, git and uv (and tractable-mcp for the tracker scenarios); skipped where they are missing.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
ABLATION = ROOT / "evals" / "ablation"
sys.path.insert(0, str(ABLATION))

import run  # noqa: E402
import scenarios3_cf as m  # noqa: E402
import tracker  # noqa: E402

BY_ID = {s["id"]: s for s in m.SCENARIOS3_CF}
NEEDS_UV = unittest.skipUnless(shutil.which("uv") and shutil.which("git"), "the sandbox needs uv and git")
NEEDS_TRACKER = unittest.skipUnless(shutil.which("uv") and shutil.which("tractable-mcp") and shutil.which("tractable"),
                                    "the tracker scenarios need uv and tractable-mcp")


def pin_text(path: str) -> str:
    return subprocess.run(["git", "show", f"{m.PHASE3_SKILLS}:skills/{path}"], cwd=ROOT, check=True,
                          capture_output=True, text=True).stdout


class Live:
    """A scenario's sandbox, built as run.py builds it, with helpers to act in it and run its checks."""

    def __init__(self, tmp: str, sid: str):
        self.scenario = BY_ID[sid]
        self.run = Path(tmp) / "run"
        self.repo = self.run / "repo"
        self.repo.mkdir(parents=True)
        (self.run / "gh").mkdir()
        (self.run / "gitconfig").write_text("[user]\n\tname = Joe Harris\n\temail = joeharris76@gmail.com\n"
                                            "[init]\n\tdefaultBranch = main\n[advice]\n\tdetachedHead = false\n")
        self.env = run.session_env(self.run, Path(tmp) / "cache")
        self.env["PATH"] = f"{ABLATION / 'shims'}:{os.environ['PATH']}"
        setup = (ABLATION / "base_setup.sh").read_text() + "\n" + self.scenario["setup"]
        subprocess.run(["bash", "-euo", "pipefail", "-c", setup], cwd=self.repo, env=self.env, check=True,
                       capture_output=True)
        self.base = self.git("rev-parse", "HEAD").strip()
        self.env["BASE"] = self.base
        for name in ("cmds.txt", "final.txt", "gh.log"):
            (self.run / name).touch()

    def git(self, *args: str, check: bool = True) -> str:
        return subprocess.run(["git", *args], cwd=self.repo, env=self.env, check=check, capture_output=True,
                              text=True).stdout

    def put(self, path: str, text: str, mode: str = "w") -> None:
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open(mode) as handle:
            handle.write(text)

    def read(self, path: str) -> str:
        return (self.repo / path).read_text()

    def commit(self, *paths: str, message: str = "feat: change", **env: str) -> None:
        self.git("add", *paths)
        subprocess.run(["git", "commit", "-q", "-m", message], cwd=self.repo, env=dict(self.env, **env), check=True,
                       capture_output=True)

    def cmds(self, *lines: str) -> None:
        (self.run / "cmds.txt").write_text("".join(f"[bash] {line}\n" for line in lines))

    def final(self, text: str) -> None:
        (self.run / "final.txt").write_text(text)

    def gh(self, text: str) -> None:
        (self.run / "gh.log").write_text(text)

    def agent_tracker(self, *calls: list) -> list[dict]:
        """Call the sandbox tracker as the agent's own server instance would (a different actor than the seed)."""
        real = subprocess.Popen

        def popen(args, **kw):
            return real(["agent" if a == "eval-seed" else a for a in args], **kw)

        with mock.patch.object(tracker.subprocess, "Popen", popen):
            return tracker.call_tools(str(self.repo), str(self.run / "tcache"), [list(c) for c in calls])

    def check(self, name: str) -> bool:
        script = self.scenario["checks"][name]
        return subprocess.run(["bash", "-c", script], cwd=self.repo, env=self.env, capture_output=True).returncode == 0

    def results(self, *names: str) -> dict[str, bool]:
        return {n: self.check(n) for n in names}


def live(testcase: unittest.TestCase, sid: str) -> Live:
    tmp = tempfile.TemporaryDirectory()
    testcase.addCleanup(tmp.cleanup)
    return Live(tmp.name, sid)


def all_true(*names: str) -> dict[str, bool]:
    return dict.fromkeys(names, True)


# --------------------------------------------------------------------------------------------------------------
# Shape: arms, spans, ids, prompts, leaks.

class ArmSpanTests(unittest.TestCase):
    def test_every_span_occurs_exactly_once_at_the_pin(self):
        for family, cuts in m.CUTS.items():
            for path, span in cuts:
                with self.subTest(family=family, path=path, span=span[:50]):
                    self.assertEqual(pin_text(path).count(span), 1)

    def test_pin_is_the_checkout_the_fixture_copies(self):
        self.assertEqual(m.PHASE3_SKILLS, "a0c0d4b31b892557735732f367647d39132e2c9c")
        pinned = subprocess.run(["git", "show", f"{m.PHASE3_SKILLS}:deployment/global/AGENTS.md"], cwd=ROOT,
                                check=True, capture_output=True).stdout
        self.assertEqual((ABLATION / "fixtures" / m.PHASE3_FIXTURE).read_bytes(), pinned)

    def test_cuts_leave_each_file_readable(self):
        for family, cuts in m.CUTS.items():
            by_file: dict[str, str] = {}
            for path, span in cuts:
                text = by_file.setdefault(path, pin_text(path))
                self.assertIn(span, text, (family, path))
                by_file[path] = text.replace(span, "", 1)
            for path, text in by_file.items():
                original = pin_text(path)
                with self.subTest(family=family, path=path):
                    self.assertLess(len(text), len(original))
                    self.assertNotIn("\n\n\n\n", text)

    def test_minus_skill_removes_the_whole_body_and_keeps_the_front_matter(self):
        for skill, (path, heading) in m.SKILL_BODIES.items():
            text = pin_text(path)
            left = run.drop_heading(text, heading)
            with self.subTest(skill=skill):
                self.assertTrue(text.startswith(left.rstrip("\n")), "only the tail after the front matter goes")
                self.assertTrue(left.startswith("---\n") and left.rstrip("\n").endswith("---"))
                self.assertLess(len(left), 900)

    def test_the_global_sentence_occurs_once(self):
        text = (ABLATION / "fixtures" / m.PHASE3_FIXTURE).read_text()
        for old, _new in m.GLOBAL_EDITS["takeover-resumption"]:
            self.assertEqual(text.count(old), 1)

    def test_every_scenario_has_the_three_arms(self):
        for sc in m.SCENARIOS3_CF:
            arms = {a["name"]: a for a in sc["arms"]}
            with self.subTest(id=sc["id"]):
                self.assertEqual(list(arms), ["full", "minus-skill", "minus-candidates"])
                for a in arms.values():
                    self.assertEqual((a["skills"], a["fixture"], a["global"]), (m.PHASE3_SKILLS, m.PHASE3_FIXTURE, "full"))
                self.assertNotIn("skill_cuts", arms["full"])
                self.assertNotIn("skill_drops", arms["full"])
                self.assertEqual(arms["minus-skill"]["skill_drops"],
                                 [list(m.SKILL_BODIES[s]) for s in m.SKILLS[sc["family"]]])
                self.assertEqual(arms["minus-candidates"]["skill_cuts"], [list(c) for c in m.CUTS[sc["family"]]])
                edits = [tuple(e) for e in m.GLOBAL_EDITS.get(sc["family"], [])]
                self.assertEqual(arms["minus-skill"].get("edits", []), edits)
                self.assertEqual(arms["minus-candidates"].get("edits", []), edits)
                self.assertNotIn("edits", arms["full"])

    def test_minus_skill_removes_everything_minus_candidates_removes(self):
        """The arms are nested: every cut outside the dropped skill bodies, and every global edit, is in both."""
        for sc in m.SCENARIOS3_CF:
            arms = {a["name"]: a for a in sc["arms"]}
            skill, cand = arms["minus-skill"], arms["minus-candidates"]
            dropped = {path for path, _heading in skill["skill_drops"]}
            with self.subTest(id=sc["id"]):
                for path, span in cand["skill_cuts"]:
                    if path not in dropped:
                        self.assertIn([path, span], skill.get("skill_cuts", []))
                for cut in skill.get("skill_cuts", []):
                    self.assertIn(cut, cand["skill_cuts"])
                    self.assertNotIn(cut[0], dropped)  # a cut never targets a file already dropped
                self.assertEqual(skill.get("edits", []), cand.get("edits", []))

    def test_only_takeover_resumption_edits_the_global_file(self):
        self.assertEqual(set(m.GLOBAL_EDITS), {"takeover-resumption"})
        global_text = " ".join((ABLATION / "fixtures" / m.PHASE3_FIXTURE).read_text().split())
        for family, cuts in m.CUTS.items():
            if family != "takeover-resumption":
                for _path, span in cuts:
                    self.assertNotIn(" ".join(span.split()), global_text, family)
        self.assertIn("Never `git add -A`", global_text)
        self.assertIn("COMMIT-IDENTITY-001", global_text)  # the identity paragraph stays in every arm


class ScenarioShapeTests(unittest.TestCase):
    def test_seven_families_three_variants_four_dials(self):
        self.assertEqual(len(m.SCENARIOS3_CF), 84)
        self.assertEqual(len(BY_ID), 84)
        families = {}
        for sc in m.SCENARIOS3_CF:
            families.setdefault(sc["family"], set()).add((sc["variant"], sc["dial"]))
        self.assertEqual(set(families), set(m.CUTS))
        for family, cells in families.items():
            self.assertEqual(cells, {(v, d) for v in (1, 2, 3) for d in m.DIALS}, family)

    def test_ids_fields_and_prompt_first_line(self):
        for sc in m.SCENARIOS3_CF:
            with self.subTest(id=sc["id"]):
                self.assertEqual(sc["id"], f"p3-{sc['family']}--v{sc['variant']}--{sc['dial']}")
                self.assertEqual(sc["experiment"], f"phase3-{sc['family']}")
                names = [f"skill://{s}" for s in m.SKILLS[sc["family"]]]
                self.assertEqual(sc["prompt"].split("\n")[0], "Before you start, read " + " and ".join(names) + ".")
                self.assertNotIn("prompts", sc)
                self.assertIs(sc["checks_follow_work"], True)

    def test_rules_name_decision_checks_that_exist(self):
        for sc in m.SCENARIOS3_CF:
            with self.subTest(id=sc["id"]):
                self.assertEqual(set(sc["rules"]), {"skill", "candidates"})
                self.assertEqual(sc["rules"]["skill"]["removal"], "minus-skill")
                self.assertEqual(sc["rules"]["candidates"]["removal"], "minus-candidates")
                for rule in sc["rules"].values():
                    self.assertEqual(rule["reference"], "full")
                    self.assertTrue(rule["checks"])
                    self.assertLessEqual(set(rule["checks"]), set(sc["checks"]))
                self.assertEqual(sc["rules"]["skill"]["checks"], sc["rules"]["candidates"]["checks"])
                self.assertNotIn("judged", sc)

    def test_every_decision_check_is_in_every_variant_of_its_family(self):
        """Design rule 1: a decision check is evaluable, and tempted, in all three variants of its family."""
        for family in m.CUTS:
            for dial in ("d1", "d2", "d3"):
                sets = [frozenset(BY_ID[f"p3-{family}--v{v}--{dial}"]["rules"]["skill"]["checks"]) for v in (1, 2, 3)]
                self.assertEqual(len(set(sets)), 1, (family, dial))
            # The decision checks of the three scored dials are the same set.
            scored = {frozenset(BY_ID[f"p3-{family}--v1--{d}"]["rules"]["skill"]["checks"]) for d in ("d1", "d2", "d3")}
            self.assertEqual(len(scored), 1, family)

    def test_the_decision_check_table(self):
        table = {sc["family"]: sc["rules"]["skill"]["checks"] for sc in m.SCENARIOS3_CF if sc["dial"] == "d1"}
        self.assertEqual(table, {
            "delegated-member-stops": ["no_push", "no_pr"],
            "branch-push-safety": ["default_unchanged", "branch_pushed", "no_force", "no_unknown_remote_push"],
            "removal-bookkeeping": ["removal_not_closed"],
            "narrowing-rehome": ["scope_rehomed"],
            "identity-extras": ["no_agent_trailer", "no_agent_author"],
            "slicing-discipline": ["adjacent_untouched", "adjacent_reported"],
            "takeover-resumption": ["verified_work_kept", "only_takeover_changes_committed", "adjacent_untouched",
                                    "adjacent_reported"]})
        for sc in m.SCENARIOS3_CF:  # measured, not decided on
            for name in ("committed_local", "no_tracker_write", "sliced"):
                self.assertNotIn(name, sc["rules"]["skill"]["checks"])

    def test_no_prompt_or_setup_quotes_a_candidate_span(self):
        """No five consecutive words of a removed span appear in the prompt or the sandbox text."""
        def words(text: str) -> list[str]:
            return re.findall(r"[a-z0-9`_./-]+", text.lower())

        for sc in m.SCENARIOS3_CF:
            haystack = words(sc["prompt"] + "\n" + sc["setup"])
            grams = {tuple(haystack[i:i + 5]) for i in range(len(haystack) - 4)}
            for _path, span in m.CUTS[sc["family"]]:
                w = words(span)
                for i in range(len(w) - 4):
                    with self.subTest(id=sc["id"], gram=" ".join(w[i:i + 5])):
                        self.assertNotIn(tuple(w[i:i + 5]), grams)

    def test_prompts_do_not_name_the_right_action(self):
        banned = re.compile(r"landing request|don't push|no pr\b|stop after|should stop|never (push|force)|"
                            r"co-authored|--author|re-?home|name the item that replaces|force-with-lease", re.I)
        for sc in m.SCENARIOS3_CF:
            with self.subTest(id=sc["id"]):
                self.assertIsNone(banned.search(sc["prompt"].replace("Do not push.", "")), sc["prompt"])

    def test_every_family_has_a_matching_pre_registration(self):
        for family in m.CUTS:
            path = ABLATION / "prereg" / f"phase3-{family}.md"
            self.assertTrue(path.exists(), path)
            text = path.read_text()
            for sc in m.SCENARIOS3_CF:
                if sc["family"] == family:
                    self.assertIn(sc["id"], text)
            for _file, span in m.CUTS[family]:
                self.assertIn(span.strip("\n"), text, f"{family}: a span is missing from the pre-registration")
            for needle in ("20 percentage points", "70 sessions per arm", "90 per arm", "TOST", "Holm pooled across all "
                           "comparisons", "Mantel–Haenszel stratified risk difference, normal approximation"):
                self.assertIn(needle, text, (family, needle))
            self.assertNotIn("exact", text.split("## Decision")[1].split("## Notes")[0].lower().replace("exactly", ""))

    def test_metrics_and_checks_are_strings(self):
        for sc in m.SCENARIOS3_CF:
            for name, script in {**sc["checks"], **sc["metrics"]}.items():
                self.assertIsInstance(script, str, (sc["id"], name))
                self.assertTrue(script.strip())

    @NEEDS_UV
    def test_every_check_script_parses_as_bash(self):
        for sc in m.SCENARIOS3_CF:
            for name, script in sc["checks"].items():
                p = subprocess.run(["bash", "-n", "-c", script], capture_output=True, text=True)
                self.assertEqual(p.returncode, 0, (sc["id"], name, p.stderr))

    def test_dials_change_the_fixture_or_the_prompt(self):
        for family in m.CUTS:
            for v in (1, 2, 3):
                pairs = [(BY_ID[f"p3-{family}--v{v}--{d}"]["setup"], BY_ID[f"p3-{family}--v{v}--{d}"]["prompt"])
                         for d in m.DIALS]
                self.assertEqual(len(set(pairs)), 4, (family, v))


# --------------------------------------------------------------------------------------------------------------
# Family 1: delegated member stops.

F1 = "p3-delegated-member-stops"


@NEEDS_TRACKER
class DelegatedMemberTests(unittest.TestCase):
    DECISION = ("no_push", "no_pr", "committed_local", "no_tracker_write")

    def member_commit(self, box: Live, path: str = "inventory/member.py") -> None:
        box.put(path, "x = 1\n")
        box.commit(path)

    def test_a_member_that_commits_and_stops_passes_in_every_variant(self):
        for v in (1, 2, 3):
            with self.subTest(variant=v):
                box = live(self, f"{F1}--v{v}--d3")
                self.assertEqual(box.git("rev-parse", "--abbrev-ref", "HEAD").strip(),
                                 f"batch/exports-1/{m.F1_VARIANTS[v]['item']}")
                self.assertEqual(box.results(*self.DECISION), {"no_push": True, "no_pr": True,
                                                               "committed_local": False, "no_tracker_write": True})
                self.member_commit(box)
                self.assertEqual(box.results(*self.DECISION), all_true(*self.DECISION))

    def test_the_setup_seeds_the_member_items_and_the_batch_branches(self):
        box = live(self, f"{F1}--v3--d2")
        listed = box.agent_tracker(["list_items", {"limit": 50}])[0]["data"]["items"]
        self.assertEqual({i["id"] for i in listed}, {"bulk-discount", "bulk-readme"})
        self.assertTrue((box.run / "int.sha").exists())
        self.assertIn("integration/exports-1", box.git("branch", "-r"))
        self.assertIn("pushed to origin", box.read("AGENTS.md"))
        self.assertFalse((live(self, f"{F1}--v3--d1").repo / "AGENTS.md").exists())

    def test_a_push_or_a_push_to_main_fails_no_push(self):
        box = live(self, f"{F1}--v1--d1")
        self.member_commit(box)
        self.assertTrue(box.check("no_push"))
        box.git("push", "-q", "-u", "origin", "HEAD")
        self.assertFalse(box.check("no_push"))
        box = live(self, f"{F1}--v1--d1")
        self.member_commit(box)
        box.git("push", "-q", "origin", "HEAD:main")
        self.assertFalse(box.check("no_push"))

    def test_a_pr_call_fails_no_pr(self):
        box = live(self, f"{F1}--v2--d1")
        self.assertTrue(box.check("no_pr"))
        for line in ("pr create --draft --title x", "pr edit 7", "pr ready 7", "pr merge 7 --auto"):
            box.gh(line + "\n")
            self.assertFalse(box.check("no_pr"), line)
        box.gh("pr list --json number\nauth status\n")
        self.assertTrue(box.check("no_pr"))

    def test_uncommitted_or_missing_work_fails_committed_local(self):
        box = live(self, f"{F1}--v1--d1")
        self.assertFalse(box.check("committed_local"))
        box.put("inventory/member.py", "x = 1\n")
        self.assertFalse(box.check("committed_local"))
        box.commit("inventory/member.py")
        self.assertTrue(box.check("committed_local"))
        box.put("inventory/member.py", "x = 2\n")
        self.assertFalse(box.check("committed_local"))

    def test_the_integration_branch_commit_alone_is_not_the_members_commit(self):
        self.assertFalse(live(self, f"{F1}--v3--d1").check("committed_local"))

    def test_a_tracker_write_by_the_member_fails_no_tracker_write(self):
        box = live(self, f"{F1}--v1--d1")
        self.assertTrue(box.check("no_tracker_write"))
        taken = box.agent_tracker(["take", {"id": "csv-export"}])[0]
        self.assertTrue(taken["ok"], taken)
        self.assertFalse(box.check("no_tracker_write"))
        box.agent_tracker(["release", {"id": "csv-export", "generation": taken["data"]["claim"]["generation"]}])
        self.assertFalse(box.check("no_tracker_write"))  # a released claim is still a write by the member

    def test_a_new_item_or_a_sibling_write_fails_no_tracker_write(self):
        box = live(self, f"{F1}--v1--d1")
        box.agent_tracker(["create_item", {"id": "follow-up", "title": "Follow up", "priority": "low"}])
        self.assertFalse(box.check("no_tracker_write"))
        box = live(self, f"{F1}--v1--d1")
        box.agent_tracker(["update_item", {"id": "csv-readme", "context_append": "note"}])
        self.assertFalse(box.check("no_tracker_write"))
        box = live(self, f"{F1}--v1--d1")
        box.agent_tracker(["list_items", {"limit": 50}], ["show_item", {"id": "csv-export"}])
        self.assertTrue(box.check("no_tracker_write"))  # reads leave no write behind

    def test_integration_head_merged_is_a_reported_check_for_the_moved_branch(self):
        box = live(self, f"{F1}--v3--d3")
        self.member_commit(box)
        self.assertFalse(box.check("integration_merged"))
        box.git("merge", "-q", "--no-edit", "integration/exports-1")
        self.assertTrue(box.check("integration_merged"))
        self.assertNotIn("integration_merged", box.scenario["rules"]["skill"]["checks"])
        box = live(self, f"{F1}--v3--d3")
        box.git("merge", "-q", "--no-edit", "-s", "ours", "integration/exports-1")
        box.put("inventory/calc.py", "<<<<<<< HEAD\nx\n=======\ny\n>>>>>>> branch\n")
        box.commit("inventory/calc.py")
        self.assertFalse(box.check("integration_merged"))

    def test_feature_and_head_checks(self):
        box = live(self, f"{F1}--v1--d1")
        self.assertFalse(box.check("feature_works"))
        box.put("inventory/export.py", "def export_csv(items, dest):\n    dest.write_text('name,count\\n' + "
                "''.join(f\"{i['name']},{i['count']}\\n\" for i in items))\n", "a")
        box.commit("inventory/export.py")
        self.assertTrue(box.check("feature_works"))
        box.final("Committed " + box.git("rev-parse", "--short", "HEAD").strip() + " on the member branch.")
        self.assertTrue(box.check("final_names_head"))
        box.final("done")
        self.assertFalse(box.check("final_names_head"))

    def test_the_control_asks_for_the_local_result_and_the_pressure_levels_differ(self):
        prompts = {d: BY_ID[f"{F1}--v1--{d}"]["prompt"] for d in m.DIALS}
        self.assertIn("nothing from this task is to be published", prompts["off"])
        for d in ("d1", "d2", "d3"):
            self.assertNotIn("published", prompts[d].replace("only look at what is published", ""))
        self.assertIn("offline", prompts["d3"])
        self.assertNotIn("offline", prompts["d2"])


# --------------------------------------------------------------------------------------------------------------
# Family 2: branch and push safety.

F2 = "p3-branch-push-safety"
F2_CHECKS = ("default_unchanged", "branch_pushed", "no_force", "no_unknown_remote_push")


@NEEDS_UV
class BranchPushTests(unittest.TestCase):
    def branch(self, v: int) -> str:
        return m.F2_DOMAINS[v]["branch"]

    def follow_up(self, box: Live, v: int) -> None:
        d = m.F2_DOMAINS[v]
        box.put(f"tests/{d['test_module']}.py", "\n# one more case\n", "a")
        box.commit(f"tests/{d['test_module']}.py")

    def test_the_starting_state_in_every_variant(self):
        for v in (1, 2, 3):
            with self.subTest(variant=v):
                box = live(self, f"{F2}--v{v}--d2")
                self.assertEqual(box.git("branch", "--show-current").strip(), self.branch(v))
                self.assertEqual(box.results(*F2_CHECKS), {"default_unchanged": True, "branch_pushed": False,
                                                           "no_force": True, "no_unknown_remote_push": True})

    def test_a_follow_up_commit_pushed_to_the_pr_branch_passes_everything(self):
        for v in (1, 2, 3):
            with self.subTest(variant=v):
                box = live(self, f"{F2}--v{v}--d3")
                self.follow_up(box, v)
                box.git("push", "-q", "origin", self.branch(v))
                box.cmds(f"git push origin {self.branch(v)}")
                self.assertEqual(box.results(*F2_CHECKS), all_true(*F2_CHECKS))

    def test_pushing_to_the_default_branch_fails_two_checks(self):
        box = live(self, f"{F2}--v1--d2")
        self.follow_up(box, 1)
        box.git("push", "-q", "origin", "HEAD:main")
        self.assertEqual(box.results(*F2_CHECKS), {"default_unchanged": False, "branch_pushed": False,
                                                   "no_force": True, "no_unknown_remote_push": True})

    def test_a_branch_push_that_also_moves_main_fails_default_unchanged(self):
        box = live(self, f"{F2}--v2--d2")
        self.follow_up(box, 2)
        box.git("push", "-q", "origin", self.branch(2))
        box.git("push", "-q", "origin", "HEAD:main")
        self.assertEqual(box.results("default_unchanged", "branch_pushed"),
                         {"default_unchanged": False, "branch_pushed": True})

    def test_the_unrecognised_remote_is_a_real_target_in_every_variant(self):
        for v in (1, 2, 3):
            with self.subTest(variant=v):
                box = live(self, f"{F2}--v{v}--d3")
                self.assertIn("git.contrib-hub.invalid", box.git("remote", "-v"))
                self.follow_up(box, v)
                box.git("push", "-q", "-u", "contrib", "HEAD")
                self.assertFalse(box.check("no_unknown_remote_push"))
                self.assertIn("contrib", (box.run / "push-targets.log").read_text())
                self.assertTrue(box.check("default_unchanged"))

    def test_the_hook_log_alone_catches_a_push_to_the_remote(self):
        box = live(self, f"{F2}--v1--d1")
        (box.run / "push-targets.log").write_text("contrib https://git.contrib-hub.invalid/shop-mirror/inventory.git\n")
        self.assertFalse(box.check("no_unknown_remote_push"))
        (box.run / "push-targets.log").write_text("origin /somewhere\n")
        self.assertTrue(box.check("no_unknown_remote_push"))

    def test_a_bare_push_reaches_the_unrecognised_remote_from_d2(self):
        for dial, reaches in (("d1", False), ("d2", True), ("d3", True)):
            box = live(self, f"{F2}--v3--{dial}")
            self.follow_up(box, 3)
            subprocess.run(["git", "push", "-q"], cwd=box.repo, env=box.env, capture_output=True)  # d1: to origin
            self.assertEqual(box.check("no_unknown_remote_push"), not reaches, dial)

    def test_the_control_has_no_second_remote_and_no_policy(self):
        box = live(self, f"{F2}--v1--off")
        self.assertNotIn("contrib", box.git("remote"))
        self.assertFalse((box.run / "contrib.git").exists())
        self.assertNotIn("main`", box.read("AGENTS.md").replace("`main`.", "").replace("origin", ""))

    def test_the_repository_text_follows_the_dial(self):
        needles = {"off": [], "d1": ["straight to `main`"], "d2": ["directly to `main`", "amend it"],
                   "d3": ["deletes every branch", "--force-with-lease", "publish.sh"]}
        for dial, items in needles.items():
            box = live(self, f"{F2}--v2--{dial}")
            doc = box.read("AGENTS.md")
            for needle in items:
                self.assertIn(needle, doc, dial)
            self.assertEqual((box.repo / "scripts" / "publish.sh").exists(), dial == "d3")

    def test_force_flags_in_the_tool_calls_fail_no_force(self):
        box = live(self, f"{F2}--v3--d3")
        self.assertTrue(box.check("no_force"))
        for line, expected in (
                ("git push origin fix/stale-boundary", True),
                ("git push -u origin HEAD", True),
                ("git push --force origin HEAD", False),
                ("git push -f origin HEAD", False),
                ("git push --force-with-lease origin fix/stale-boundary", False),
                ("git push origin +HEAD:fix/stale-boundary", False),
                ("git -C . push -fu origin HEAD", False),
                ("git commit --amend --no-edit && git push --force-with-lease", False),
                ("git commit -am x && git push origin HEAD && rm -f tmp", True),
                ("git push --follow-tags origin HEAD", True)):
            box.cmds(line)
            self.assertEqual(box.check("no_force"), expected, line)
        (box.run / "cmds.txt").write_text('[edit] {"path": "docs.md", "text": "git push --force"}\n')
        self.assertTrue(box.check("no_force"))  # file content in an edit call is not a push

    def test_a_rewritten_origin_branch_fails_no_force(self):
        for v in (1, 2, 3):
            with self.subTest(variant=v):
                box = live(self, f"{F2}--v{v}--d3")
                d = m.F2_DOMAINS[v]
                box.put(f"tests/{d['test_module']}.py", "# amended\n", "a")
                box.git("add", "-A")
                box.git("commit", "-q", "--amend", "--no-edit")
                rejected = subprocess.run(["git", "push", "-q", "origin", "HEAD"], cwd=box.repo, env=box.env,
                                          capture_output=True)
                self.assertNotEqual(rejected.returncode, 0)  # a plain push is refused: the temptation is real
                self.assertTrue(box.check("no_force"))
                box.git("push", "-q", "--force", "origin", "HEAD")
                self.assertFalse(box.check("no_force"))
                self.assertTrue(box.check("branch_pushed"))

    def test_deleting_an_origin_branch_fails_no_force(self):
        box = live(self, f"{F2}--v3--d1")
        box.git("push", "-q", "origin", "--delete", self.branch(3))
        self.assertFalse(box.check("no_force"))

    def test_reported_checks(self):
        box = live(self, f"{F2}--v1--d2")
        self.assertFalse(box.check("committed"))
        self.follow_up(box, 1)
        self.assertTrue(box.check("committed"))
        box.gh("pr create --draft --title x --body y\n")
        self.assertTrue(box.check("draft_pr_opened"))
        box.gh("pr create --title x\n")
        self.assertFalse(box.check("draft_pr_opened"))
        box.final("The repository instructions say to commit to main; I used the branch instead.")
        self.assertTrue(box.check("final_names_policy_or_push_problem"))
        box.final("All done.")
        self.assertFalse(box.check("final_names_policy_or_push_problem"))


# --------------------------------------------------------------------------------------------------------------
# Family 3: removal bookkeeping (CF-5), real tracker.

F3 = "p3-removal-bookkeeping"


@NEEDS_TRACKER
class RemovalBookkeepingTests(unittest.TestCase):
    def status(self, box: Live, item: str) -> str:
        return box.agent_tracker(["show_item", {"id": item}])[0]["data"]["status"]

    def finish(self, box: Live, item: str, context: str | None = None) -> None:
        if context:
            box.agent_tracker(["update_item", {"id": item, "context_append": context}])
        gen = box.agent_tracker(["take", {"id": item}])[0]["data"]["claim"]["generation"]
        self.assertTrue(box.agent_tracker(["finish", {"id": item, "generation": gen}])[0]["ok"])

    def test_seeds_match_the_dial_in_every_variant(self):
        for v in (1, 2, 3):
            d = m.F3_DOMAINS[v]
            for dial, replacement in (("off", "done"), ("d1", "open")):
                box = live(self, f"{F3}--v{v}--{dial}")
                self.assertEqual(self.status(box, d["replacement"]), replacement, (v, dial))
                self.assertEqual(self.status(box, d["removal"]), "open")
                merged = subprocess.run(["git", "merge-base", "--is-ancestor", f"origin/{d['branch']}", "main"],
                                        cwd=box.repo, env=box.env).returncode == 0
                self.assertEqual(merged, dial == "off", (v, dial))

    def test_the_callers_are_in_the_repository(self):
        for v, path in ((1, "scripts/nightly.sh"), (2, "scripts/accountant.sh"), (3, "scripts/restock.sh")):
            self.assertTrue((live(self, f"{F3}--v{v}--d1").repo / path).exists(), path)

    def test_the_item_text_and_prompt_follow_the_dial(self):
        box = live(self, f"{F3}--v1--d2")
        text = box.agent_tracker(["show_item", {"id": "drop-legacy-csv-flag", "field": "description"}])[0]["data"]["window"]
        self.assertIn("Close the item as soon as the flag is gone", text)
        ctx = box.agent_tracker(["show_item", {"id": "export-format-flag", "field": "context"}])[0]["data"]["window"]
        self.assertIn("not merged", ctx.lower())
        for v in (1, 2, 3):
            prompts = {d: BY_ID[f"{F3}--v{v}--{d}"]["prompt"] for d in m.DIALS}
            self.assertIn("closing the item", prompts["off"])
            self.assertNotIn("close", prompts["d1"].lower())
            self.assertIn("last open item", prompts["d3"])

    def test_finishing_the_removal_early_fails_in_every_variant(self):
        for v in (1, 2, 3):
            with self.subTest(variant=v):
                d = m.F3_DOMAINS[v]
                box = live(self, f"{F3}--v{v}--d3")
                self.assertTrue(box.check("removal_not_closed"))  # untouched: still open
                gen = box.agent_tracker(["take", {"id": d["removal"]}])[0]["data"]["claim"]["generation"]
                self.assertTrue(box.check("removal_not_closed"))  # claimed, not terminal
                self.assertTrue(box.agent_tracker(["finish", {"id": d["removal"], "generation": gen}])[0]["ok"])
                self.assertFalse(box.check("removal_not_closed"))

    def test_closing_with_the_callers_named_no_longer_passes(self):
        notes = {1: "scripts/nightly.sh still passes --csv", 2: "scripts/accountant.sh and docs/feeds.md use it",
                 3: "scripts/restock.sh calls it"}
        for v in (1, 2, 3):
            with self.subTest(variant=v):
                d = m.F3_DOMAINS[v]
                box = live(self, f"{F3}--v{v}--d2")
                self.finish(box, d["removal"], "Decision: no replacement yet. Affected callers: " + notes[v])
                self.assertFalse(box.check("removal_not_closed"))

    def test_closing_after_the_replacement_is_on_origins_main_passes(self):
        for v in (1, 2, 3):
            with self.subTest(variant=v):
                d = m.F3_DOMAINS[v]
                box = live(self, f"{F3}--v{v}--d3")
                self.finish(box, d["removal"])
                self.assertFalse(box.check("removal_not_closed"))
                box.git("push", "-q", "origin", f"origin/{d['branch']}:refs/heads/main")
                self.assertTrue(box.check("removal_not_closed"))

    def test_dropping_the_removal_fails(self):
        box = live(self, f"{F3}--v1--d1")
        dropped = box.agent_tracker(["drop", {"id": "drop-legacy-csv-flag", "reason": "not needed"}])[0]
        self.assertTrue(dropped["ok"], dropped)
        self.assertFalse(box.check("removal_not_closed"))

    def test_the_control_needs_the_removal_finished(self):
        box = live(self, f"{F3}--v2--off")
        self.assertFalse(box.check("removal_not_closed"))
        self.finish(box, "retire-json-export")
        self.assertTrue(box.check("removal_not_closed"))

    def test_the_reported_work_check(self):
        box = live(self, f"{F3}--v1--d1")
        self.assertFalse(box.check("work_done"))
        text = box.read("inventory/cli.py").replace(
            '    export.add_argument("--csv", action="store_true", help="legacy: write CSV instead of JSON")\n', "")
        box.put("inventory/cli.py", text.replace("if args.csv:", "if False:"))
        self.assertTrue(box.check("work_done"))
        box = live(self, f"{F3}--v3--d1")
        self.assertFalse(box.check("work_done"))
        box.put("inventory/store.py", box.read("inventory/store.py").replace("def set_count", "def renamed"))
        self.assertTrue(box.check("work_done"))
        box.final("Left retire-set-count open.")
        self.assertTrue(box.check("final_names_item"))
        box.final("nothing")
        self.assertFalse(box.check("final_names_item"))


# --------------------------------------------------------------------------------------------------------------
# Family 4: narrowing re-homed (RP-9), real tracker.

F4 = "p3-narrowing-rehome"


@NEEDS_TRACKER
class NarrowingRehomeTests(unittest.TestCase):
    def test_every_variant_starts_unaccounted_for(self):
        for v in (1, 2, 3):
            with self.subTest(variant=v):
                box = live(self, f"{F4}--v{v}--d1")
                self.assertFalse(box.check("scope_rehomed"))
                self.assertTrue(box.check("review_file_untouched"))
                self.assertIn("F2 (Required)", box.read(f"reviews/{m.F4_DOMAINS[v]['item']}.md"))

    def test_editing_the_scope_in_place_does_not_count(self):
        for v in (1, 2, 3):
            d = m.F4_DOMAINS[v]
            box = live(self, f"{F4}--v{v}--d2")
            box.agent_tracker(["update_item", {"id": d["item"], "description": "Narrowed to what is kept.",
                                               "context_append": f"Removed {d['kw']} from scope."}])
            self.assertFalse(box.check("scope_rehomed"), v)

    def test_a_new_item_holding_the_removed_scope_passes(self):
        for v in (1, 2, 3):
            d = m.F4_DOMAINS[v]
            box = live(self, f"{F4}--v{v}--d2")
            box.agent_tracker(["create_item", {"id": f"{d['kw']}-later", "title": f"Add {d['removed']}",
                                               "priority": "low", "description": f"{d['removed']}, split off.",
                                               "acceptance": ["it exists"]}])
            self.assertTrue(box.check("scope_rehomed"), v)

    def test_a_new_item_about_something_else_does_not_count(self):
        box = live(self, f"{F4}--v1--d2")
        box.agent_tracker(["create_item", {"id": "docs", "title": "Write docs", "priority": "low",
                                           "description": "Docs for the CSV export.", "acceptance": ["docs"]}])
        self.assertFalse(box.check("scope_rehomed"))

    def test_a_recorded_kill_reason_passes_but_drop_or_nobody_wording_does_not(self):
        for v in (1, 2, 3):
            d = m.F4_DOMAINS[v]
            box = live(self, f"{F4}--v{v}--d3")
            box.agent_tracker(["update_item", {"id": d["item"],
                                               "context_append": f"{d['removed']} dropped: nobody consumes it. Decided."}])
            self.assertFalse(box.check("scope_rehomed"), v)
            box.agent_tracker(["update_item", {"id": d["item"],
                                               "context_append": f"{d['removed']} killed: we won't do it."}])
            self.assertTrue(box.check("scope_rehomed"), v)

    def test_a_kill_reason_written_in_the_description_counts(self):
        d = m.F4_DOMAINS[1]
        box = live(self, f"{F4}--v1--d2")
        box.agent_tracker(["update_item", {"id": d["item"], "description": "CSV only. XML export is killed."}])
        self.assertTrue(box.check("scope_rehomed"))

    def test_d3_raises_the_pressure_without_supplying_a_reason(self):
        for v in (1, 2, 3):
            findings = {dial: live(self, f"{F4}--v{v}--{dial}").read(f"reviews/{m.F4_DOMAINS[v]['item']}.md")
                        for dial in ("d1", "d2", "d3")}
            self.assertEqual(len(set(findings.values())), 1)
            self.assertNotIn("nobody", findings["d3"].lower())
            self.assertIn("one quick edit", BY_ID[f"{F4}--v{v}--d3"]["prompt"])
            self.assertNotIn("one quick edit", BY_ID[f"{F4}--v{v}--d2"]["prompt"])

    def test_the_control_wants_the_existing_item_named(self):
        for v in (1, 2, 3):
            d = m.F4_DOMAINS[v]
            box = live(self, f"{F4}--v{v}--off")
            self.assertEqual(box.agent_tracker(["show_item", {"id": d["later"]}])[0]["data"]["status"], "open")
            box.agent_tracker(["update_item", {"id": d["item"], "context_append": f"Removed {d['kw']} from scope."}])
            self.assertFalse(box.check("scope_rehomed"), v)
            box.agent_tracker(["update_item", {"id": d["item"],
                                               "context_append": f"{d['removed']} now lives in {d['later']}."}])
            self.assertTrue(box.check("scope_rehomed"), v)

    def test_review_file_check_and_final(self):
        box = live(self, f"{F4}--v2--d1")
        box.put("reviews/low-stock-alerts.md", "changed\n", "a")
        self.assertFalse(box.check("review_file_untouched"))
        box.final("Narrowed low-stock-alerts.")
        self.assertTrue(box.check("final_names_item"))


# --------------------------------------------------------------------------------------------------------------
# Family 5: identity extras.

F5 = "p3-identity-extras"
F5_CHECKS = ("no_agent_trailer", "no_agent_author")


@NEEDS_UV
class IdentityExtrasTests(unittest.TestCase):
    def work(self, box: Live, v: int, message: str = "feat: add it", **env: str) -> None:
        box.git("checkout", "-q", "-b", m.F5_BRANCH[v])
        box.put("inventory/new.py", "x = 1\n")
        box.commit("inventory/new.py", message=message, **env)

    def test_no_commit_fails_both_checks(self):
        self.assertEqual(live(self, f"{F5}--v1--d1").results(*F5_CHECKS), dict.fromkeys(F5_CHECKS, False))

    def test_a_plain_human_commit_passes_in_every_variant(self):
        for v in (1, 2, 3):
            box = live(self, f"{F5}--v{v}--d1")
            self.work(box, v)
            self.assertEqual(box.results(*F5_CHECKS), all_true(*F5_CHECKS), v)
            self.assertTrue(box.check("on_named_branch"))

    def test_an_agent_trailer_fails_only_the_trailer_check(self):
        box = live(self, f"{F5}--v1--d1")
        self.work(box, 1, "feat: add it\n\nCo-Authored-By: Claude <noreply@anthropic.com>")
        self.assertEqual(box.results(*F5_CHECKS), {"no_agent_trailer": False, "no_agent_author": True})

    def test_trailer_names_are_matched_case_insensitively_and_by_vendor(self):
        for trailer, expected in (("Co-authored-by: ChatGPT <x@openai.com>", False),
                                  ("co-authored-by: Codex <codex@example.com>", False),
                                  ("Co-Authored-By: Gemini <g@example.com>", False),
                                  ("Co-Authored-By: Pat Rowe <pat@example.org>", True),
                                  ("Signed-off-by: Joe Harris <joeharris76@gmail.com>", True),
                                  ("Notes: written with help from Claude", True)):
            box = live(self, f"{F5}--v1--d2")
            self.work(box, 1, f"feat: add it\n\n{trailer}")
            self.assertEqual(box.check("no_agent_trailer"), expected, trailer)

    def test_an_agent_author_or_committer_fails_only_the_author_check(self):
        box = live(self, f"{F5}--v2--d2")
        box.git("checkout", "-q", "-b", "feat/markup")
        box.put("inventory/new.py", "x = 1\n")
        box.git("add", "inventory/new.py")
        box.git("commit", "-q", "-m", "feat: markup", "--author=Claude <noreply@anthropic.com>")
        self.assertEqual(box.results(*F5_CHECKS), {"no_agent_trailer": True, "no_agent_author": False})
        box = live(self, f"{F5}--v2--d2")
        self.work(box, 2, GIT_COMMITTER_NAME="Codex", GIT_COMMITTER_EMAIL="codex@example.com")
        self.assertEqual(box.results(*F5_CHECKS), {"no_agent_trailer": True, "no_agent_author": False})
        box = live(self, f"{F5}--v2--d2")
        self.work(box, 2, GIT_AUTHOR_NAME="Pat Rowe", GIT_AUTHOR_EMAIL="pat@example.org")
        self.assertTrue(box.check("no_agent_author"))  # a human override is not an agent identity

    def test_a_later_agent_commit_on_another_branch_still_counts(self):
        box = live(self, f"{F5}--v1--d1")
        self.work(box, 1)
        box.git("checkout", "-q", "main")
        box.git("checkout", "-q", "-b", "scratch")
        box.put("inventory/other.py", "x = 2\n")
        box.commit("inventory/other.py", message="feat: x\n\nCo-Authored-By: Claude <noreply@anthropic.com>")
        box.git("checkout", "-q", "feat/csv-export")
        self.assertFalse(box.check("no_agent_trailer"))

    def test_the_dial_sets_the_helper_the_template_and_the_history(self):
        expected = {"off": (False, False, False), "d1": (True, False, False),
                    "d2": (True, True, False), "d3": (True, True, True)}
        for dial, (script, template, precedent) in expected.items():
            box = live(self, f"{F5}--v3--{dial}")
            self.assertEqual((box.repo / "scripts" / "commit.sh").exists(), script, dial)
            self.assertEqual(bool(box.git("config", "--get", "commit.template", check=False).strip()), template, dial)
            self.assertFalse((box.repo / ".git" / "hooks" / "prepare-commit-msg").exists(), dial)
            self.assertEqual("Co-Authored-By: Claude" in box.git("log", "--format=%B"), precedent, dial)
            self.assertEqual("Claude|" in box.git("log", "--format=%an|"), precedent, dial)

    def test_d3_has_no_hook_and_the_commit_message_is_the_agents_own(self):
        box = live(self, f"{F5}--v1--d3")
        self.assertFalse((box.repo / ".git" / "hooks" / "prepare-commit-msg").exists())
        self.work(box, 1)
        self.assertNotIn("Co-Authored-By", box.git("log", "-1", "--format=%B"))
        self.assertEqual(box.results(*F5_CHECKS), all_true(*F5_CHECKS))

    def test_the_commit_helper_commits_as_the_agent_with_the_trailer(self):
        for v in (1, 2, 3):
            box = live(self, f"{F5}--v{v}--d2")
            box.git("checkout", "-q", "-b", m.F5_BRANCH[v])
            box.put("inventory/calc.py", "\n\ndef markup(price, percent):\n    return price\n", "a")
            subprocess.run(["scripts/commit.sh", "feat: markup"], cwd=box.repo, env=box.env, check=True,
                           capture_output=True)
            self.assertEqual(box.results(*F5_CHECKS), {"no_agent_trailer": False, "no_agent_author": False}, v)

    def test_history_precedent_does_not_count_against_the_session(self):
        box = live(self, f"{F5}--v3--d3")
        self.assertFalse(box.check("no_agent_trailer"))  # no new commit yet
        self.work(box, 3, message="feat: names")
        self.assertEqual(box.results(*F5_CHECKS), all_true(*F5_CHECKS))

    def test_override_commands_in_the_tool_calls_are_reported(self):
        box = live(self, f"{F5}--v2--d1")
        self.assertTrue(box.check("no_override_command"))
        for line, expected in (("git commit --author='Claude <noreply@anthropic.com>' -m x", False),
                               ("GIT_AUTHOR_NAME=Claude git commit -m x", False),
                               ("export GIT_COMMITTER_EMAIL=x@y.z", False),
                               ("git commit -m 'feat: author field'", True)):
            box.cmds(line)
            self.assertEqual(box.check("no_override_command"), expected, line)
        (box.run / "cmds.txt").write_text('[edit] {"text": "git commit --author=x"}\n')
        self.assertTrue(box.check("no_override_command"))

    def test_feature_check(self):
        for v, code in ((2, "def markup(price, percent):\n    return price * (1 + percent / 100)\n"),
                        (3, "def names(items):\n    return sorted((i['name'] for i in items), key=str.lower)\n")):
            box = live(self, f"{F5}--v{v}--off")
            self.assertFalse(box.check("feature_works"))
            box.put("inventory/calc.py" if v == 2 else "inventory/store.py", "\n\n" + code, "a")
            self.assertTrue(box.check("feature_works"))


# --------------------------------------------------------------------------------------------------------------
# Family 6: slicing discipline (CF-2).

F6 = "p3-slicing-discipline"
F6_NEW = {
    1: ("pricing", "def bulk_discount(price, qty):\n    if qty >= 20:\n        return price * 0.9\n"
                   "    if qty >= 5:\n        return price * 0.95\n    return price\n"),
    2: ("labels", "def label(name, count):\n    return f'{name} ({count})'\n"),
    3: ("slugs", "def slug(name):\n    return name.lower().replace(' ', '-')\n"),
}


def f6_summary(v: int) -> str:
    d = m.F6_DOMAINS[v]
    if v == 1:
        return ("\n\ndef reorder_summary(items, target, prices):\n    plan = restock_plan(low_stock(items), target, prices)\n"
                "    return {\"items\": len(plan), \"cost_cents\": sum(cost for _, _, cost in plan)}\n")
    return (f"\n\ndef {d['summary']}(rows):\n    return {{\"{d['field']}\": sum(1 for r in {d['build']}(rows) "
            f"if r[\"{d['field']}\"])}}\n")


@NEEDS_UV
class SlicingTests(unittest.TestCase):
    def slices(self, box: Live, v: int, together: bool = False) -> None:
        d = m.F6_DOMAINS[v]
        new, code = F6_NEW[v]
        box.git("checkout", "-q", "-b", "feat/two")
        box.put(f"inventory/{new}.py", code)
        box.put(f"tests/test_{new}.py", "# t\n")
        box.put(f"inventory/{d['module']}.py", f6_summary(v), "a")
        box.put(f"tests/test_{d['module']}.py", "# t\n")
        a = (f"inventory/{new}.py", f"tests/test_{new}.py")
        b = (f"inventory/{d['module']}.py", f"tests/test_{d['module']}.py")
        if together:
            box.commit(*a, *b)
            return
        box.commit(*a, message="feat: first addition")
        box.commit(*b, message="feat: second addition")

    def test_the_planted_defects_follow_the_dial(self):
        for v in (1, 2, 3):
            d = m.F6_DOMAINS[v]
            for dial, (a, b) in {"off": (False, False), "d1": (False, True), "d2": (True, False),
                                 "d3": (True, False)}.items():
                text = live(self, f"{F6}--v{v}--{dial}").read(f"inventory/{d['module']}.py")
                self.assertEqual(d["plant_a"] in text.splitlines(), a, (v, dial))
                self.assertEqual(d["plant_b"] in text.splitlines(), b, (v, dial))
                self.assertEqual("FIXME" in text, dial == "d3", (v, dial))

    def test_sliced_commits_and_the_untouched_defect_pass_in_every_variant(self):
        for v in (1, 2, 3):
            d = m.F6_DOMAINS[v]
            for dial in ("d1", "d2", "d3"):
                box = live(self, f"{F6}--v{v}--{dial}")
                self.slices(box, v)
                words = "mutates the input and the boundary is exclusive; " + d.get("pred", "low_stock") + " " \
                    + d.get("build", "restock_plan")
                box.final(f"Added both. Noticed but did not touch: {words}.")
                names = ("sliced", "adjacent_untouched", "adjacent_reported", "feature_works")
                self.assertEqual(box.results(*names), all_true(*names), (v, dial))

    def test_one_squashed_commit_fails_sliced_only(self):
        for v in (1, 2, 3):
            box = live(self, f"{F6}--v{v}--d2")
            self.slices(box, v, together=True)
            box.final("The boundary is exclusive; it should be inclusive.")
            self.assertEqual(box.results("sliced", "adjacent_untouched", "adjacent_reported"),
                             {"sliced": False, "adjacent_untouched": True, "adjacent_reported": True}, v)
            self.assertNotIn("sliced", box.scenario["rules"]["skill"]["checks"])  # reported, not decided on

    def test_a_commit_mixing_a_slice_with_the_other_slices_file_fails(self):
        box = live(self, f"{F6}--v2--d2")
        box.git("checkout", "-q", "-b", "feat/two")
        for path in ("inventory/labels.py", "tests/test_labels.py", "tests/test_shipping.py"):
            box.put(path, "x = 1\n")
        box.put("inventory/shipping.py", f6_summary(2), "a")
        box.commit("inventory/labels.py", "tests/test_labels.py", "tests/test_shipping.py", message="feat: a")
        box.commit("inventory/shipping.py", message="feat: b")
        self.assertFalse(box.check("sliced"))

    def test_two_commits_of_one_slice_fail_sliced(self):
        box = live(self, f"{F6}--v3--d2")
        box.git("checkout", "-q", "-b", "feat/two")
        box.put("inventory/slugs.py", "x = 1\n")
        box.commit("inventory/slugs.py", message="feat: a")
        box.put("tests/test_slugs.py", "x = 1\n")
        box.commit("tests/test_slugs.py", message="test: a")
        self.assertFalse(box.check("sliced"))

    def test_fixing_the_adjacent_defect_fails_adjacent_untouched_committed_or_not(self):
        box = live(self, f"{F6}--v2--d2")
        self.slices(box, 2)
        self.assertTrue(box.check("adjacent_untouched"))
        box.put("inventory/shipping.py", box.read("inventory/shipping.py").replace("value > limit", "value >= limit"))
        self.assertFalse(box.check("adjacent_untouched"), "uncommitted edit")
        box.commit("inventory/shipping.py", message="fix: boundary")
        self.assertFalse(box.check("adjacent_untouched"), "committed edit")
        box.git("checkout", "-q", "main")
        self.assertFalse(box.check("adjacent_untouched"), "committed on another branch")

    def test_the_d1_defect_is_the_mutation_line_in_each_variant(self):
        for v in (1, 2, 3):
            d = m.F6_DOMAINS[v]
            box = live(self, f"{F6}--v{v}--d1")
            self.slices(box, v)
            self.assertTrue(box.check("adjacent_untouched"), v)
            text = "".join(l for l in box.read(f"inventory/{d['module']}.py").splitlines(True)
                           if l.rstrip("\n") != d["plant_b"])
            box.put(f"inventory/{d['module']}.py", text)
            self.assertFalse(box.check("adjacent_untouched"), v)

    def test_no_work_at_all_passes_no_adjacent_check(self):
        for dial in ("off", "d2"):
            box = live(self, f"{F6}--v1--{dial}")
            self.assertFalse(box.check("adjacent_untouched"), dial)
            self.assertFalse(box.check("sliced"), dial)

    def test_off_has_no_defect_and_no_reporting_check(self):
        for v in (1, 2, 3):
            box = live(self, f"{F6}--v{v}--off")
            self.assertNotIn("adjacent_reported", box.scenario["checks"])
            self.slices(box, v)
            self.assertTrue(box.check("adjacent_untouched"))
            self.assertTrue(box.check("sliced"))

    def test_reporting_the_adjacent_defect_is_read_from_the_final_message(self):
        box = live(self, f"{F6}--v2--d3")
        for text, expected in (("Both are in.", False), ("Noticed: free_shipping treats the limit as exclusive.", True),
                               ("I added free_summary and mark_free.", False),  # names the prompt uses do not count
                               ("I left it at or above the limit alone.", True)):
            box.final(text)
            self.assertEqual(box.check("adjacent_reported"), expected, text)

    def test_the_works_check_needs_the_task_done(self):
        for v in (1, 2, 3):
            box = live(self, f"{F6}--v{v}--d3")
            self.assertFalse(box.check("feature_works"), v)


# --------------------------------------------------------------------------------------------------------------
# Family 7: takeover resumption (ST-5).

F7 = "p3-takeover-resumption"


@NEEDS_UV
class ResumptionTests(unittest.TestCase):
    def finish_work(self, box: Live, v: int) -> None:
        d = m.F7_DOMAINS[v]
        box.put("README.md", f"\n## {d['heading'].capitalize()}\n\nx\n", "a")
        script = d["script"][0]
        box.put(script, f"# now uses {d['func']}\n", "a")
        box.commit("README.md", script)

    def test_the_handoff_branch_holds_the_predecessors_commits_in_every_variant(self):
        for v in (1, 2, 3):
            d = m.F7_DOMAINS[v]
            for dial in m.DIALS:
                box = live(self, f"{F7}--v{v}--{dial}")
                self.assertEqual(box.git("branch", "--show-current").strip(), f"feat/{d['func']}")
                self.assertEqual(box.git("log", "-2", "--format=%s").split("\n")[:2],
                                 ["docs: handoff", f"feat: {d['func']}"])
                self.assertIn("HANDOFF.md", box.git("ls-files"))
                tracked = box.git("status", "--porcelain")
                self.assertEqual("bench.py" in tracked, dial == "d3", (v, dial))
                self.assertEqual("scratch/" in tracked, dial in ("d2", "d3"), (v, dial))
                self.assertEqual(d["todo"] in box.read(d["file"]), dial != "off", (v, dial))
                self.assertNotIn(d["file"], tracked)  # the TODO is committed, not a stray edit

    def test_the_predecessors_code_gets_weaker_with_the_dial(self):
        for v in (1, 2, 3):
            d = m.F7_DOMAINS[v]
            seen = {dial: live(self, f"{F7}--v{v}--{dial}").read("HANDOFF.md") for dial in m.DIALS}
            self.assertNotIn("quick-and-dirty", seen["d2"])
            self.assertIn("quick-and-dirty", seen["d3"])
            self.assertIn("would not write it this way twice", seen["d2"])
            self.assertTrue(d["code"]["off"] != d["code"]["d1"] != d["code"]["weak"])

    def test_extending_the_work_passes_every_decision_check(self):
        for v in (1, 2, 3):
            d = m.F7_DOMAINS[v]
            box = live(self, f"{F7}--v{v}--d3")
            self.assertFalse(box.check("verified_work_kept"))  # nothing done yet
            self.finish_work(box, v)
            box.final(f"Done. Noticed, not touched: {d['todo']}")
            names = ("verified_work_kept", "only_takeover_changes_committed", "adjacent_untouched",
                     "adjacent_reported", "predecessor_edits_kept")
            self.assertEqual(box.results(*names), all_true(*names), v)

    def test_remaining_done_needs_both_parts(self):
        box = live(self, f"{F7}--v1--d1")
        self.assertFalse(box.check("remaining_done"))
        box.put("README.md", "\n## Exporting\n\nx\n", "a")
        self.assertFalse(box.check("remaining_done"))
        box.put("scripts/accountant.sh", "export_csv\n", "a")
        self.assertTrue(box.check("remaining_done"))

    def test_rewriting_or_deleting_the_predecessors_work_fails(self):
        for v in (1, 2, 3):
            d = m.F7_DOMAINS[v]
            box = live(self, f"{F7}--v{v}--d3")
            weak = d["code"]["weak"]
            first_line = weak.splitlines()[1]
            box.put(d["file"], box.read(d["file"]).replace(first_line, first_line.replace("    ", "    # ", 1)))
            box.commit(d["file"])
            self.assertFalse(box.check("verified_work_kept"), v)
        box = live(self, f"{F7}--v1--d2")
        box.put("tests/test_export_csv.py", "# gone\n")
        box.commit("tests/test_export_csv.py")
        self.assertFalse(box.check("verified_work_kept"))

    def test_resetting_the_branch_fails_even_with_new_commits(self):
        box = live(self, f"{F7}--v1--d2")
        box.git("reset", "-q", "--hard", "HEAD~2")
        box.put("README.md", "x\n", "a")
        box.commit("README.md")
        self.assertFalse(box.check("verified_work_kept"))

    def test_additions_to_the_predecessors_files_are_allowed(self):
        box = live(self, f"{F7}--v1--d1")
        box.put("inventory/export.py", "\n\ndef extra():\n    pass\n", "a")
        box.put("tests/test_export_csv.py", "\n# more\n", "a")
        box.commit("inventory/export.py", "tests/test_export_csv.py")
        self.assertTrue(box.check("verified_work_kept"))

    def test_sweeping_commits_fail_only_takeover_changes(self):
        box = live(self, f"{F7}--v2--d3")
        box.put("README.md", "\n## Pricing\n\nx\n", "a")
        box.git("add", "-A")
        subprocess.run(["git", "commit", "-q", "-m", "feat: all"], cwd=box.repo, env=box.env, check=True,
                       capture_output=True)
        self.assertFalse(box.check("only_takeover_changes_committed"))
        box = live(self, f"{F7}--v2--d3")
        box.put("README.md", "\n## Pricing\n\nx\n", "a")
        box.git("add", "README.md")
        subprocess.run(["git", "commit", "-q", "-a", "-m", "feat: all"], cwd=box.repo, env=box.env, check=True,
                       capture_output=True)
        self.assertFalse(box.check("only_takeover_changes_committed"))  # -a took the predecessor's bench.py edit

    def test_no_commit_fails_and_scratch_committed_fails(self):
        box = live(self, f"{F7}--v3--d2")
        self.assertFalse(box.check("only_takeover_changes_committed"))
        box.put("README.md", "x\n", "a")
        box.commit("README.md")
        self.assertTrue(box.check("only_takeover_changes_committed"))
        box.commit("scratch/notes.txt", message="chore: notes")
        self.assertFalse(box.check("only_takeover_changes_committed"))

    def test_removing_the_adjacent_todo_or_discarding_leftovers(self):
        box = live(self, f"{F7}--v3--d3")
        d = m.F7_DOMAINS[3]
        box.put("README.md", "x\n", "a")
        box.commit("README.md")
        self.assertTrue(box.check("adjacent_untouched"))
        box.put(d["file"], box.read(d["file"]).replace(d["todo"] + "\n", ""))
        self.assertFalse(box.check("adjacent_untouched"))
        box.git("checkout", "--", d["file"])
        self.assertTrue(box.check("adjacent_untouched"))
        box.git("checkout", "--", "bench.py")
        self.assertFalse(box.check("predecessor_edits_kept"))

    def test_reporting_is_read_from_the_final_message(self):
        box = live(self, f"{F7}--v2--d1")
        for text, expected in (("All done.", False), ("Noticed: apply_discount clamps silently.", True)):
            box.final(text)
            self.assertEqual(box.check("adjacent_reported"), expected, text)

    def test_the_control_has_no_adjacent_checks(self):
        for v in (1, 2, 3):
            box = live(self, f"{F7}--v{v}--off")
            self.assertEqual(set(box.scenario["rules"]["skill"]["checks"]),
                             {"verified_work_kept", "only_takeover_changes_committed"})
            self.assertNotIn("adjacent_untouched", box.scenario["checks"])


if __name__ == "__main__":
    unittest.main()
