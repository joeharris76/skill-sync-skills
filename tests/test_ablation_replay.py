"""Tests for replaying a recorded session turn: cutting, path rewriting, commit lookup, cleanup.

Standard library only; no model calls and no network.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ABLATION = Path(__file__).resolve().parents[1] / "evals" / "ablation"
sys.path.insert(0, str(ABLATION))

import replay  # noqa: E402
import run  # noqa: E402

REPO = os.path.realpath(Path.home() / "Developer" / "example-repo")


def user(n: int, parent: str, text: str) -> dict:
    return {"type": "message", "id": f"u{n}", "parentId": parent, "timestamp": f"2026-11-13T18:0{n}:00.000Z",
            "message": {"role": "user", "content": [{"type": "text", "text": text}]}}


def assistant(n: int, parent: str, calls: list[dict] | None = None) -> dict:
    return {"type": "message", "id": f"a{n}", "parentId": parent, "timestamp": f"2026-11-13T18:0{n}:30.000Z",
            "message": {"role": "assistant", "content": [{"type": "text", "text": f"reply {n}"}] + (calls or [])}}


def bash_call(call_id: str, command: str) -> dict:
    return {"type": "toolCall", "id": call_id, "name": "bash", "arguments": {"command": command}}


def bash_result(n: int, parent: str, call_id: str, output: str, cwd: str = REPO) -> dict:
    return {"type": "message", "id": f"r{n}", "parentId": parent, "timestamp": "2026-11-13T18:00:40.000Z",
            "message": {"role": "toolResult", "toolName": "bash", "toolCallId": call_id,
                        "content": [{"type": "text", "text": output}], "details": {"cwd": cwd}}}


HEADER = {"type": "session", "version": 3, "id": "s0", "timestamp": "2026-11-13T18:00:00.000Z", "cwd": REPO}


def session_with_git(output: str, command: str = "git log --oneline -5", then: list[dict] | None = None) -> list[dict]:
    rows = [{"type": "title", "title": "t"}, HEADER, user(1, "s0", "first"),
            assistant(1, "u1", [bash_call("c1", command)]), bash_result(1, "a1", "c1", output)]
    rows += then or []
    parent = rows[-1]["id"]
    return rows + [user(2, parent, "second")]


class TruncateTest(unittest.TestCase):
    def setUp(self):
        self.rows = [{"type": "title", "title": "t"}, HEADER, user(1, "s0", "first"), assistant(1, "u1"),
                     user(2, "a1", "second"), assistant(2, "u2"), user(3, "a2", "third"), assistant(3, "u3")]

    def kinds(self, rows):
        return [r.get("id") or r["type"] for r in rows]

    def test_keeps_exactly_the_rows_before_the_turn(self):
        self.assertEqual(self.kinds(replay.truncate(self.rows, 0)), ["title", "s0"])
        self.assertEqual(self.kinds(replay.truncate(self.rows, 1)), ["title", "s0", "u1", "a1"])
        self.assertEqual(self.kinds(replay.truncate(self.rows, 2)), ["title", "s0", "u1", "a1", "u2", "a2"])

    def test_turn_out_of_range(self):
        with self.assertRaises(IndexError):
            replay.truncate(self.rows, 3)

    def test_side_branch_is_dropped(self):
        rows = self.rows[:4] + [user(9, "a1", "abandoned branch"), assistant(9, "u9")] + self.rows[4:]
        kept = self.kinds(replay.truncate(rows, 2))  # user messages are u1, u9, u2, u3
        self.assertEqual(kept, ["title", "s0", "u1", "a1"])

    def test_recorded_cost_counts_messages_and_side_usage(self):
        rows = [{"message": {"usage": {"cost": {"total": 1.5}}}},
                {"type": "model_usage", "usage": {"cost": {"total": 0.25}}}, {"type": "title"}]
        self.assertAlmostEqual(replay.recorded_cost(rows), 1.75)


class RewriteTest(unittest.TestCase):
    NEW = "/tmp/omp-ablation/abc/repo"

    def test_cwd_and_tool_arguments_are_rewritten(self):
        rows = [dict(HEADER, cwd=REPO),
                assistant(1, "s0", [bash_call("c", f"cd {REPO} && ls"),
                                    {"type": "toolCall", "id": "e", "name": "edit",
                                     "arguments": {"path": f"{REPO}/src/a.py", "edits": []}}]),
                bash_result(1, "a1", "c", f"{REPO}/src/a.py\n", cwd=REPO)]
        text = replay.rewritten_lines(rows, REPO, self.NEW)
        self.assertNotIn(REPO, text)
        parsed = [json.loads(line) for line in text.splitlines()]
        self.assertEqual(parsed[0]["cwd"], self.NEW)
        self.assertEqual(parsed[1]["message"]["content"][1]["arguments"]["command"], f"cd {self.NEW} && ls")
        self.assertEqual(parsed[1]["message"]["content"][2]["arguments"]["path"], f"{self.NEW}/src/a.py")
        self.assertEqual(parsed[2]["message"]["details"]["cwd"], self.NEW)

    def test_path_after_a_newline_or_tab_is_rewritten(self):
        output = f"first line\n{REPO}/a.py\n\t{REPO}/b.py\tand\t{REPO}\r\n{REPO}.wt-x/c.py"
        row = bash_result(1, "a1", "c", output)
        text = replay.rewritten_lines([row], REPO, self.NEW)
        got = json.loads(text)["message"]["content"][0]["text"]
        self.assertEqual(got, output.replace(f"{REPO}/", f"{self.NEW}/").replace(f"{REPO}\r", f"{self.NEW}\r")
                         .replace(f"{self.NEW}.wt-x", f"{REPO}.wt-x"))

    def test_signed_compaction_block_is_left_byte_for_byte(self):
        signed = {"provider": "anthropic", "content": f"worked in {REPO}/src", "signature": "sig"}
        row = {"type": "compaction", "id": "k", "summary": f"worked in {REPO}/src", "preserveData": {"anthropicCompaction": signed}}
        got = json.loads(replay.rewritten_lines([row], REPO, self.NEW))
        self.assertEqual(got["preserveData"]["anthropicCompaction"], signed)
        self.assertEqual(got["summary"], f"worked in {self.NEW}/src")

    def test_sibling_directories_are_left_alone(self):
        for other in (f"{REPO}.wt-fix", f"{REPO}2", f"{REPO}-old/x", f"/other{REPO}"):
            self.assertEqual(replay.rewrite_paths(other, REPO, self.NEW), other)

    def test_home_spellings(self):
        home = str(Path.home())
        old = f"{home}/Developer/example-repo"
        out = replay.rewrite_paths("cd ~/Developer/example-repo && ls $HOME/Developer/example-repo/x", old, self.NEW)
        self.assertEqual(out, f"cd {self.NEW} && ls {self.NEW}/x")


def tool_call(call_id: str, name: str, **arguments) -> dict:
    return {"type": "toolCall", "id": call_id, "name": name, "arguments": arguments}


def session_after(command_calls: list[dict], reveal: str = "3dbc781 pin\n") -> list[dict]:
    """A session that shows HEAD on turn one, then runs ``command_calls`` before the second user message."""
    rows = session_with_git(reveal)
    rows.pop()  # the second user message
    parent = rows[-1]["id"]
    rows.append(assistant(2, parent, command_calls))
    return rows + [user(2, "a2", "second")]


class DeriveCommitTest(unittest.TestCase):
    def derive(self, rows):
        return replay.derive_commit(rows, 1, REPO)

    def refuses(self, rows):
        with self.assertRaises(replay.Unrebuildable):
            self.derive(rows)

    def test_log_output_names_the_commit(self):
        self.assertEqual(self.derive(session_with_git("3dbc781 chore: pin\n92bd9cf older\n")), "3dbc781")

    def test_no_evidence_is_unrebuildable(self):
        self.refuses(session_with_git("hello\n", command="ls"))

    def test_accepted_ways_to_show_head(self):
        for command in ("git rev-parse HEAD", "git rev-parse --short HEAD", "git log -1 --format=%h", "git log --oneline -n 5",
                        "git log --oneline --no-decorate -5 | head -3", f"cd {REPO} && git log --oneline -5",
                        "git log --format='%h %s' -3"):
            with self.subTest(command):
                self.assertEqual(self.derive(session_with_git("3dbc781 x\n", command=command)), "3dbc781")

    def test_rejected_ways_to_show_head(self):
        for command in ("git log --reverse --oneline", "git log --all --oneline -5", "git log --author=joe --oneline",
                        "git log --oneline -5 | grep fix", "git log --oneline main..origin/main",
                        "git status --short | head -20; git log --oneline -5", "git log --oneline -5 && git pull -q",
                        f"cd {REPO}.wt-x && git log --oneline -5", "git -C ../other log --oneline -5"):
            with self.subTest(command):
                self.refuses(session_with_git("3dbc781 x\n", command=command))

    def test_bash_cwd_argument_is_honoured(self):
        rows = session_with_git("3dbc781 x\n", command="git log --oneline -5")
        rows[3]["message"]["content"][1]["arguments"]["cwd"] = "/tmp/elsewhere"
        self.refuses(rows)
        rows[3]["message"]["content"][1]["arguments"]["cwd"] = f"{REPO}/sub"
        self.assertEqual(self.derive(rows), "3dbc781")

    def test_unknown_cwd_clears(self):
        for call in (tool_call("m", "bash", command="git commit -qm x", cwd="$SOMEWHERE"),
                     tool_call("m", "bash", command="cd $UNSET && git commit -qm x")):
            with self.subTest(call["arguments"]):
                self.refuses(session_after([call]))

    def test_head_moving_commands_clear(self):
        for command in ("git commit -q -m x", "git pull -q", "git checkout main", "gh pr merge 5 --squash",
                        f"git -C {REPO} reset --hard", f"cd {REPO} && git checkout -q x", "git -C ~/Developer/example-repo stash",
                        f"git -C ../example-repo merge x && echo {REPO}", "git -c core.x=1 commit -qm x"):
            with self.subTest(command):
                self.refuses(session_after([tool_call("m", "bash", command=command)]))

    def test_worktree_work_elsewhere_does_not_clear(self):
        command = ("cd ~/Developer/example-repo && M=../example-repo.wt-x && git worktree add -q -b b $M origin/main "
                   "&& cd $M && git commit -qm x && git push -q")
        self.assertEqual(self.derive(session_after([tool_call("m", "bash", command=command)])), "3dbc781")

    def test_heredoc_body_is_not_commands(self):
        command = f"cd {REPO}.wt-x && git commit -F - <<'EOF'\ncd {REPO} && git checkout x\nEOF"
        self.assertEqual(self.derive(session_after([tool_call("m", "bash", command=command)])), "3dbc781")

    def test_edit_header_inside_the_repository_clears(self):
        for path in (f"{REPO}/a.py", f"{REPO}/sub/../a.py"):
            with self.subTest(path):
                self.refuses(session_after([tool_call("e", "edit", input=f"[{path}#8F0E]\nCUT 1.=1")]))
        self.refuses(session_after([tool_call("e", "edit", input=f"[{REPO}.wt-x/b.py#1A2B]\nCUT 1\n[{REPO}/c.py#3C4D]\nCUT 1")]))
        self.refuses(session_after([tool_call("w", "write", path=f"{REPO}/a.md", content="x")]))
        self.refuses(session_after([tool_call("e", "edit", input="no header here")]))  # unreadable path

    def test_edit_header_outside_the_repository_is_fine(self):
        for path in (f"{REPO}.wt-x/a.py", "../elsewhere/a.py", "/tmp/a.py"):
            with self.subTest(path):
                self.assertEqual(self.derive(session_after([tool_call("e", "edit", input=f"[{path}#8F0E]\nCUT 1")])), "3dbc781")

    def test_relative_edit_path_is_resolved_against_the_session_directory(self):
        self.refuses(session_after([tool_call("e", "edit", input="[src/a.py#8F0E]\nCUT 1")]))

    def test_tools_that_can_run_commands_clear(self):
        for name in ("task", "eval", "exec", "mcp__tractable_take", "debug"):
            with self.subTest(name):
                self.refuses(session_after([tool_call("t", name, code="x")]))
        for name in ("read", "grep", "wait", "todo", "ask"):
            with self.subTest(name):
                self.assertEqual(self.derive(session_after([tool_call("t", name, path="x")])), "3dbc781")

    def test_later_evidence_sets_the_commit_again(self):
        rows = session_after([tool_call("m", "bash", command="git pull -q")])
        rows.pop()
        rows += [bash_result(3, "a2", "m", ""), assistant(3, "r3", [bash_call("c9", "git rev-parse --short HEAD")]),
                 bash_result(4, "a3", "c9", "9999999\n"), user(2, "r4", "second")]
        self.assertEqual(self.derive(rows), "9999999")

    def test_subdirectory_session(self):
        rows = session_with_git("3dbc781 x\n")
        rows[1] = dict(HEADER, cwd=f"{REPO}/sub")
        rows[4] = bash_result(1, "a1", "c1", "3dbc781 x\n", cwd=f"{REPO}/sub")
        self.assertEqual(replay.derive_commit(rows, 1, REPO), "3dbc781")


def run_git(cwd: Path, *args: str, date: str | None = None) -> str:
    env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1")
    if date:
        env.update(GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "init.defaultBranch=main", *args],
                          cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout.strip()


class LocateTest(unittest.TestCase):
    """A synthetic repository: main, feature-a (two commits), feature/b, and a pull-request ref for a deleted branch."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(self.tmp)]))
        self.cache = self.tmp / "cache"
        self.root = self.tmp / "app"
        self.cache.mkdir()
        self.root.mkdir()
        run_git(self.root, "init", "-q")
        run_git(self.cache, "init", "-q")
        c = lambda name, date: (run_git(self.cache, "commit", "-q", "--allow-empty", "-m", name, date=date),
                                run_git(self.cache, "rev-parse", "HEAD"))[1]
        self.main1 = c("main1", "2026-11-13T17:00:00Z")
        run_git(self.cache, "checkout", "-q", "-b", "feature-a")
        self.a1 = c("a1", "2026-11-13T18:01:00Z")
        self.a2 = c("a2", "2026-11-13T18:03:00Z")
        run_git(self.cache, "checkout", "-q", "-b", "feature/b", "main")
        self.b1 = c("b1", "2026-11-13T18:01:30Z")
        run_git(self.cache, "checkout", "-q", "-b", "gone", "main")
        self.g1 = c("g1", "2026-11-13T18:01:40Z")
        run_git(self.cache, "update-ref", "refs/pull/7/head", self.g1)
        run_git(self.cache, "checkout", "-q", "main")
        run_git(self.cache, "branch", "-D", "gone")

    def session(self, output: str, cwd: str | None = None, command: str = "git status") -> list[dict]:
        rows = [HEADER | {"cwd": str(self.root)}, user(1, "s0", "first"),
                assistant(1, "u1", [tool_call("c1", "bash", command=command)]),
                bash_result(1, "a1", "c1", output, cwd=cwd or str(self.root)), user(2, "r1", "second")]
        rows[-1]["timestamp"] = "2026-11-13T18:02:00.000Z"
        return rows

    def locate(self, rows, pr_heads=None):
        return replay.locate_commit(rows, 1, str(self.root), self.cache, pr_heads or {})

    def test_refresh_cache_fetches_pull_request_heads_where_locate_looks(self):
        remote = self.tmp / "remote"
        run_git(self.tmp, "clone", "-q", str(self.cache), str(remote))
        pr = run_git(remote, "rev-parse", "origin/feature-a")
        run_git(remote, "update-ref", "refs/pull/7/head", pr)
        mirror = self.tmp / "mirror.git"
        run_git(self.tmp, "clone", "-q", "--bare", str(remote), str(mirror))
        run_git(mirror, "update-ref", "refs/pull/7", pr)  # the layout an older cache used
        replay.refresh_cache(mirror)
        self.assertEqual(run_git(mirror, "rev-parse", "refs/pull/7/head"), pr)
        self.assertEqual(subprocess.run(["git", "rev-parse", "-q", "--verify", "refs/pull/7"], cwd=mirror).returncode, 1)
        rows = self.session("On branch pr-only\n")
        self.assertEqual(replay.locate_commit(rows, 1, str(self.root), mirror, {7: "pr-only"})["ref"], "refs/pull/7/head")

    def test_directory_changes_and_git_dash_c_hide_branch_output(self):
        for command in ("cd /tmp && git status", f"git -C {self.root}.wt-x status", "cd /tmp; git status"):
            with self.subTest(command):
                self.assertIsNone(self.locate(self.session("On branch feature-a\n", command=command))["candidate"])
        self.assertEqual(self.locate(self.session("On branch feature-a\n", command=f"cd {self.root} && git status"))["candidate"], self.a1)

    def test_sibling_worktree_output_is_not_branch_evidence(self):
        found = self.locate(self.session("On branch feature-a\n", cwd=f"{self.root}.wt-feature-b"))
        self.assertEqual(found["candidate"], self.b1)  # the directory name wins, not the output

    def test_branch_from_git_output_takes_the_last_commit_before_the_turn(self):
        found = self.locate(self.session("On branch feature-a\nnothing to commit\n"))
        self.assertEqual((found["candidate"], found["ref"], found["branch"]), (self.a1, "refs/heads/feature-a", "feature-a"))
        self.assertLessEqual(found["commit_time"], found["turn_time"].replace("+00:00", "Z"))

    def test_worktree_directory_name_names_the_branch(self):
        found = self.locate(self.session("ok\n", cwd=f"{self.root}.wt-feature-b"))
        self.assertEqual((found["candidate"], found["ref"]), (self.b1, "refs/heads/feature/b"))

    def test_deleted_branch_is_found_through_its_pull_request_head(self):
        found = self.locate(self.session("On branch gone\n"), pr_heads={7: "gone"})
        self.assertEqual((found["candidate"], found["ref"]), (self.g1, "refs/pull/7/head"))

    def test_checkout_dash_b_names_the_branch(self):
        found = self.locate(self.session("Switched\n", command="git checkout -b feature-a"))
        self.assertEqual(found["candidate"], self.a1)

    def test_different_answers_are_ambiguous(self):
        run_git(self.cache, "update-ref", "refs/pull/9/head", self.main1)
        found = self.locate(self.session("On branch feature-a\n"), pr_heads={9: "feature-a"})
        self.assertIsNone(found["candidate"])
        self.assertTrue(found["reason"].startswith("ambiguous"))

    def test_same_answer_from_branch_and_pull_request_is_not_ambiguous(self):
        run_git(self.cache, "update-ref", "refs/pull/9/head", self.a1)
        found = self.locate(self.session("On branch feature-a\n"), pr_heads={9: "feature-a"})
        self.assertEqual(found["candidate"], self.a1)

    def test_unknown_branch_and_no_evidence_give_nothing(self):
        self.assertIsNone(self.locate(self.session("On branch nowhere\n"))["candidate"])
        self.assertIsNone(self.locate(self.session("hello\n"))["candidate"])

    def test_output_from_another_repository_is_ignored(self):
        self.assertIsNone(self.locate(self.session("On branch feature-a\n", cwd=str(self.tmp / "other")))["candidate"])

    def test_branch_with_no_commit_before_the_turn_gives_nothing(self):
        rows = self.session("On branch feature-a\n")
        rows[-1]["timestamp"] = "2026-11-13T16:00:00.000Z"
        self.assertIsNone(self.locate(rows)["candidate"])


class RepoDropTest(unittest.TestCase):
    GUIDE = "# Guide\n\n## Keep\nkeep me\n\n## Remove\nrule\n\n### Sub\nsub rule\n\n## After\nlast\n"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(self.tmp)]))
        self.cache = self.tmp / "cache"
        self.cache.mkdir()
        run_git(self.cache, "init", "-q")
        (self.cache / "AGENTS.md").write_text(self.GUIDE)
        run_git(self.cache, "add", "AGENTS.md")
        run_git(self.cache, "commit", "-q", "-m", "guide", date="2026-11-13T17:00:00Z")
        self.commit = run_git(self.cache, "rev-parse", "HEAD")
        self.run_dir = self.tmp / "run"
        self.run_dir.mkdir()
        self.env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1")

    def build(self, drops):
        return replay.build_repo(self.run_dir, self.cache, self.commit, None, self.env, drops)

    def test_drop_is_folded_into_the_checked_out_commit(self):
        run_git(self.cache, "commit", "-q", "--amend", "--no-edit", "--author=Real Author <real@example.invalid>", date="2026-11-13T17:00:00Z")
        self.commit = run_git(self.cache, "rev-parse", "HEAD")
        before = run_git(self.cache, "log", "-1", "--format=%an|%ae|%aI|%cn|%ce|%cI|%s|%P")
        repo = self.build([["AGENTS.md", "Remove"]])
        text = (repo / "AGENTS.md").read_text()
        self.assertNotIn("Remove", text)
        self.assertNotIn("sub rule", text)
        self.assertIn("## After", text)
        self.assertEqual(run_git(repo, "status", "--porcelain"), "")
        self.assertNotEqual(run_git(repo, "rev-parse", "HEAD"), self.commit)
        self.assertEqual(run_git(repo, "log", "-1", "--format=%an|%ae|%aI|%cn|%ce|%cI|%s|%P"), before)  # nothing but the hash differs
        self.assertEqual(run_git(repo, "rev-list", "--count", "HEAD"), "1")  # no extra commit

    def test_local_branches_move_and_remote_tracking_refs_stay(self):
        repo = self.build([["AGENTS.md", "Remove"]])
        branch = run_git(repo, "branch", "--show-current") or None
        local = run_git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads").split()
        amended = run_git(repo, "rev-parse", "HEAD")
        for name in local:
            self.assertEqual(run_git(repo, "rev-parse", name), amended)
        self.assertEqual(run_git(repo, "rev-parse", "refs/remotes/origin/HEAD^{commit}"), self.commit)

    def test_no_drops_leaves_the_commit_checked_out(self):
        repo = self.build(None)
        self.assertEqual(run_git(repo, "rev-parse", "HEAD"), self.commit)

    def test_missing_duplicate_or_absent_file_stops_the_run(self):
        for drops in ([["AGENTS.md", "Nowhere"]], [["MISSING.md", "Remove"]]):
            with self.subTest(drops), self.assertRaises(SystemExit):
                self.build(drops)
            subprocess.run(["rm", "-rf", str(self.run_dir / "repo"), str(self.run_dir / "origin.git")])
        (self.cache / "AGENTS.md").write_text(self.GUIDE + "\n## Remove\nagain\n")
        run_git(self.cache, "commit", "-q", "-am", "dup", date="2026-11-13T17:01:00Z")
        self.commit = run_git(self.cache, "rev-parse", "HEAD")
        with self.assertRaises(SystemExit):
            self.build([["AGENTS.md", "Remove"]])


class ProfileTest(unittest.TestCase):
    def test_profile_hides_originals_and_protects_the_cache(self):
        text = replay.deny_profile("(version 1)\n(allow default)\n", Path(REPO), Path("/data/sessions/x/s.jsonl"), Path("/tmp/omp-ablation/cache"))
        for hidden in (REPO, "/data/sessions/x", str(Path.home() / ".ssh"), str(replay.SESSIONS_DIR)):
            self.assertIn(f'(subpath "{hidden}")', text)
        self.assertIn('(deny file-write*\n  (subpath "/tmp/omp-ablation/cache")', text)

    def test_pushes_to_github_are_blocked(self):
        self.assertEqual(replay.BLOCKED_PUSH, ["https://github.com/", "git@github.com:", "ssh://git@github.com/"])


class CleanupTest(unittest.TestCase):
    """The sandbox holds real session text and must go even when the run fails."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(self.tmp)]))
        (self.tmp / "orig").mkdir()
        subprocess.run(["git", "init", "-q", str(self.tmp / "orig")], check=True)
        (self.tmp / "root").mkdir()
        (self.tmp / "root" / "deny.sb").write_text("(version 1)\n(allow default)\n(deny file-read*\n  (subpath \"/x\")\n)\n")
        rows = session_with_git("3dbc781 pin\n")
        rows[1] = dict(HEADER, cwd=str(self.tmp / "orig"))
        rows[4] = bash_result(1, "a1", "c1", "3dbc781 pin\n", cwd=str(self.tmp / "orig"))
        self.session = self.tmp / "2026-11-13T18-00-00-000Z_0123456789abcdef.jsonl"
        self.session.write_text("".join(json.dumps(r) + "\n" for r in rows))
        self.ledger = run.Ledger(self.tmp / "ledger.json")
        self.arm = {"name": "none", "global": "none", "skills": "unused"}

    def replay(self, runner, **pin):
        def build(run_dir, cache, commit, text, env, drops=None):
            (run_dir / "repo").mkdir()
            run_git(run_dir / "repo", "init", "-q")
            run_git(run_dir / "repo", "commit", "-q", "--allow-empty", "-m", "x")
            return run_dir / "repo"
        patches = [mock.patch.object(replay, "SANDBOX_ROOT", self.tmp / "root"),
                   mock.patch.object(replay, "ensure_cache", return_value=self.tmp / ("gitcache" if pin else "cache")),
                   *([] if pin else [mock.patch.object(replay, "resolve_commit", return_value="f" * 40)]),
                   mock.patch.object(replay, "build_repo", side_effect=build),
                   mock.patch.object(replay, "skills_dir", return_value=self.tmp / "skills")]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        return replay.replay_one(self.session, 1, self.arm, self.tmp / "out", self.tmp / "cache", self.ledger,
                                 runner=runner, remote="https://example.invalid/r.git", **pin)

    def sandboxes(self):
        return [p.name for p in (self.tmp / "root").iterdir() if p.name != "deny.sb"]

    def test_sandbox_removed_when_the_session_fails(self):
        def runner(cmd, **kw):
            self.assertIn("--resume", cmd)
            self.assertEqual(len(self.sandboxes()), 1)  # it existed while running
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom")
        with self.assertRaises(RuntimeError):
            self.replay(runner)
        self.assertEqual(self.sandboxes(), [])
        self.assertFalse((self.tmp / "out" / "results").exists())

    def test_sandbox_removed_on_timeout(self):
        def runner(cmd, **kw):
            raise subprocess.TimeoutExpired(cmd, 1, output=b"")
        with self.assertRaises(RuntimeError):
            self.replay(runner)
        self.assertEqual(self.sandboxes(), [])

    def test_resumed_copy_is_cut_and_the_original_is_untouched(self):
        original = self.session.read_bytes()
        seen = {}

        def runner(cmd, **kw):
            copy = Path(cmd[cmd.index("--resume") + 1])
            seen["copy"] = copy.read_text()
            seen["prompt"] = cmd[-1]
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")
        with self.assertRaises(RuntimeError):
            self.replay(runner)
        self.assertEqual(self.session.read_bytes(), original)
        self.assertNotIn("second", seen["copy"])
        self.assertIn("first", seen["copy"])
        self.assertEqual(seen["prompt"], "second")
        self.assertNotIn(str(self.tmp / "orig"), seen["copy"])

    def synthetic_cache(self, commit_date: str) -> str:
        cache = self.tmp / "gitcache"
        cache.mkdir()
        run_git(cache, "init", "-q")
        run_git(cache, "commit", "-q", "--allow-empty", "-m", "c", date=commit_date)
        return run_git(cache, "rev-parse", "HEAD")

    def test_pinned_commit_newer_than_the_turn_is_refused(self):
        sha = self.synthetic_cache("2026-11-13T19:00:00Z")  # the turn is at 18:02
        with mock.patch.object(replay, "ensure_cache", return_value=self.tmp / "gitcache"), \
                mock.patch.object(replay, "SANDBOX_ROOT", self.tmp / "root"):
            with self.assertRaisesRegex(replay.Unrebuildable, "after the turn"):
                replay.replay_one(self.session, 1, self.arm, self.tmp / "out", self.tmp / "cache", self.ledger,
                                  remote="https://example.invalid/r.git", commit=sha, commit_evidence="because")
        self.assertTrue(list((self.tmp / "out" / "unrebuildable").glob("replay-*-1.json")))
        self.assertEqual(self.sandboxes(), [])

    def test_pin_must_be_hex_and_must_match_an_existing_result(self):
        for bad in ("main", "ABC1234", "abc12", "abc1234;rm"):
            with self.subTest(bad), self.assertRaises(ValueError):
                replay.replay_one(self.session, 1, self.arm, self.tmp / "out", self.tmp / "cache", self.ledger,
                                  commit=bad, commit_evidence="x")
        result = self.tmp / "out" / "results" / f"replay-{replay.session_label(self.session)}-1__none__0.json"
        result.parent.mkdir(parents=True)
        result.write_text(json.dumps({"replay": {"commit": "a" * 40, "commit_source": "pinned"}}))
        for kwargs in ({}, {"commit": "b" * 7, "commit_evidence": "x"}):
            with self.subTest(kwargs), self.assertRaises(RuntimeError):
                replay.replay_one(self.session, 1, self.arm, self.tmp / "out", self.tmp / "cache", self.ledger, **kwargs)
        replay.replay_one(self.session, 1, self.arm, self.tmp / "out", self.tmp / "cache", self.ledger,
                          commit="a" * 7, commit_evidence="x")

    def test_skill_drops_reach_skills_dir_and_repo_drops_are_recorded(self):
        events = [{"type": "message_end", "message": {"role": "assistant", "model": "claude-sonnet-5-5", "usage": {"cost": {"total": 0}},
                                                       "content": [{"type": "text", "text": "ok"}]}}, {"type": "agent_end"}]
        self.arm = dict(self.arm, skill_drops=[["x/SKILL.md", "Heading"]], repo_drops=[["AGENTS.md", "Heading"]])
        result = self.replay(lambda cmd, **kw: subprocess.CompletedProcess(
            cmd, 0, stdout="".join(json.dumps(e) + "\n" for e in events), stderr=""))
        self.assertEqual(result["replay"]["repo_drops"], [["AGENTS.md", "Heading"]])
        self.assertEqual(replay.skills_dir.call_args.args[3], [["x/SKILL.md", "Heading"]])

    def test_pin_needs_evidence(self):
        with self.assertRaises(ValueError):
            replay.replay_one(self.session, 1, self.arm, self.tmp / "out", self.tmp / "cache", self.ledger, commit="abc1234")

    def test_pinned_result_records_source_and_evidence(self):
        sha = self.synthetic_cache("2026-11-13T17:00:00Z")
        events = [{"type": "message_end", "message": {"role": "assistant", "model": "claude-sonnet-5-5", "usage": {"cost": {"total": 0.01}},
                                                       "content": [{"type": "text", "text": "ok"}]}}, {"type": "agent_end"}]

        def runner(cmd, **kw):
            return subprocess.CompletedProcess(cmd, 0, stdout="".join(json.dumps(e) + "\n" for e in events), stderr="")
        result = self.replay(runner, commit=sha, commit_evidence="branch X at 17:00")
        self.assertEqual((result["replay"]["commit_source"], result["replay"]["commit_evidence"]), ("pinned", "branch X at 17:00"))
        self.assertEqual(result["replay"]["commit"], sha)
        self.assertEqual(self.sandboxes(), [])

    def test_unrebuildable_turn_is_recorded_and_skipped(self):
        with self.assertRaises(replay.Unrebuildable):
            replay.replay_one(self.session, 0, self.arm, self.tmp / "out", self.tmp / "cache", self.ledger,
                              remote="https://example.invalid/r.git")
        self.assertTrue(list((self.tmp / "out" / "unrebuildable").glob("replay-*-0.json")))
        self.assertEqual(self.sandboxes(), [])


if __name__ == "__main__":
    unittest.main()
