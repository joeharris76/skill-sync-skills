"""Replay one real user turn of a recorded omp session under an arm.

The session file is copied into a throwaway sandbox, cut just before the chosen
user message, and its recorded working directory and absolute paths are
rewritten to a rebuilt copy of the repository. omp then resumes the copy with
the user's next prompt under the arm's instruction text and skills. Nothing
under the user's clone, ``~/.omp`` or the original session file is written.

Usage:
    replay.py list --session FILE
    replay.py locate --session FILE [--turn N]
    replay.py run --out DIR --session FILE --turn N [--turn M ...]
                  [--global SPEC] [--skills REV] [--check-file FILE] [--smoke]
                  [--commit SHA --commit-evidence TEXT]

Turns are numbered from 0 over the session's user messages. Claude Code and
Codex sessions are not supported: ``omp --from-claude`` opens an interactive
picker and exits when there is no terminal, so it cannot import a file in a
headless run. Convert such a session to an omp session file first.

How the commit is found (never guessed): the session's recorded bash calls are
read in order, keeping only commands that ran in the session's own directory.
A command that prints the checked-out commit (``git rev-parse HEAD``,
``git log -1 --format=%h``, ``git commit`` output ``[branch abc1234]``, the
``Updating a..b`` line of a fast-forward pull) sets the commit. A command that
moves HEAD without printing it (checkout, switch, reset, merge, rebase,
cherry-pick, pull, a quiet commit) clears it. An edit or write tool call inside
the repository after the commit also clears it, because the working tree then
held changes no commit has. If a commit is still set when the turn starts, it
must exist in the local cache of the GitHub remote and be no newer than the
turn; otherwise the turn is counted as unrebuildable and skipped. Edits made by
shell commands are not detected, and work the session never committed is lost;
a replay therefore tests the committed state, not the exact working tree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run import (DISABLED_PROVIDERS, MODEL, SANDBOX_ROOT, Ledger, baseline, bash_commands,  # noqa: E402
                 drop_heading, file_hash, final_text, global_text, parse_events, pin_baseline,
                 prepare_sandbox_root, skills_dir, turn_cost)
from scenarios2 import PHASE2_FIXTURE, PHASE2_SKILLS  # noqa: E402

HOME = Path.home()
SESSIONS_DIR = HOME / ".omp" / "agent" / "sessions"
MAX_REPLAY_COST = 2.0  # USD a replayed turn may spend on top of the session's recorded cost


class Unrebuildable(Exception):
    """The repository state at the turn cannot be determined or found."""


# --- reading a session ------------------------------------------------------


def read_session(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def message_text(entry: dict) -> str:
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return content
    return "".join(b.get("text", "") for b in content or [] if isinstance(b, dict) and b.get("type") == "text")


def user_turn_indexes(rows: list[dict]) -> list[int]:
    """Row index of each real user message, in order."""
    return [i for i, r in enumerate(rows) if r.get("type") == "message" and (r.get("message") or {}).get("role") == "user"]


def truncate(rows: list[dict], turn: int) -> list[dict]:
    """The rows that precede user message ``turn``: its ancestors in the entry tree, plus rows with no id.

    A linear session keeps exactly the rows before the message; if the session
    branched, side branches are dropped.
    """
    turns = user_turn_indexes(rows)
    if not 0 <= turn < len(turns):
        raise IndexError(f"turn {turn} out of range: session has {len(turns)} user messages")
    target = rows[turns[turn]]
    by_id = {r["id"]: r for r in rows if "id" in r}
    chain: set[str] = set()
    cur = by_id.get(target.get("parentId"))
    while cur is not None and cur["id"] not in chain:
        chain.add(cur["id"])
        cur = by_id.get(cur.get("parentId"))
    return [r for r in rows[:turns[turn]] if "id" not in r or r["id"] in chain or r.get("type") == "session"]


def recorded_cost(rows: list[dict]) -> float:
    """USD already spent in the kept rows; omp counts it against ``--max-cost`` when the session resumes."""
    def cost(usage: dict | None) -> float:
        return float(((usage or {}).get("cost") or {}).get("total", 0))
    return sum(cost((r.get("message") or {}).get("usage")) + cost(r.get("usage") if r.get("type") == "model_usage" else None)
               for r in rows)


def pin_model(rows: list[dict], model: str) -> list[dict]:
    """Point the session's recorded active-model switches (default, temporary, fallback) at ``model``.

    The history keeps its text; only the record of which model the session was
    using changes, so the resumed turn does not continue on a model the session
    had switched to. Role entries (review, plan, ...) are left as recorded.
    """
    return [dict(r, model=model) if r.get("type") == "model_change" and r.get("role") in (None, "temporary", "fallback") else r
            for r in rows]


def rewrite_paths(text: str, old: str, new: str) -> str:
    """Replace ``old`` (and its ``~`` and ``$HOME`` spellings) with ``new`` wherever it is a whole path prefix.

    ``/a/repo`` matches ``/a/repo`` and ``/a/repo/x`` but not a sibling such as
    ``/a/repo.wt-fix`` or ``/a/repo2``. Applied to decoded text (see ``rewritten_lines``),
    where a newline or tab before a path is a real character, not an escape.
    """
    forms = [old]
    home = str(HOME)
    if old.startswith(home + "/"):
        tail = old[len(home):]
        forms += ["~" + tail, "$HOME" + tail]
    pattern = "|".join(re.escape(f) for f in forms)
    return re.sub(rf"(?<![\w.\-/~$])(?:{pattern})(?![\w.\-])", lambda _: new, text)


def rewrite_strings(value, old: str, new: str):
    """Rewrite every string inside a parsed JSON value (not the keys): the cwd field, tool arguments and recorded output alike."""
    if isinstance(value, str):
        return rewrite_paths(value, old, new)
    if isinstance(value, list):
        return [rewrite_strings(v, old, new) for v in value]
    if isinstance(value, dict):
        # A compaction block is signed over its content: changing one byte (a rewritten path) makes the API
        # reject the whole history with a 400, and omp then falls back to another model.
        return {k: v if k == "anthropicCompaction" else rewrite_strings(v, old, new) for k, v in value.items()}
    return value


def rewritten_lines(rows: list[dict], old: str | list[str], new: str) -> str:
    """The rows as JSON lines with each spelling in ``old`` of the repository path replaced by ``new``."""
    olds = [old] if isinstance(old, str) else old
    for spelling in olds:
        rows = [rewrite_strings(r, spelling, new) for r in rows]
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)


# --- finding the commit -----------------------------------------------------

# Tools that cannot change the repository; every other tool that is not a file edit clears the commit,
# because it may run commands (task, eval, exec, MCP servers, ...).
SAFE_TOOLS = {"read", "grep", "glob", "find", "web_search", "todo", "ask", "wait"}
FILE_TOOLS = {"edit", "write", "ast_edit"}
GIT_SUBCOMMANDS = (r"checkout|switch|reset|merge|rebase|cherry-pick|pull|am|revert|commit|stash|restore|clean|apply|rm|mv"
                   r"|update-ref|symbolic-ref")
MOVES_HEAD = re.compile(rf"\bgit\b(?:\s+(?:-[Cc]\s+\S+|--\S+))*\s+(?:{GIT_SUBCOMMANDS})\b|\bgh\s+pr\s+(?:merge|checkout)\b")
# Output that starts with the checked-out commit: ``git rev-parse [--short] HEAD`` or a ``git log`` limited by a
# count, ``--oneline``, ``--format`` and ``--no-decorate`` only (a range, ``--all`` or ``--author`` would list
# other commits first), optionally piped to ``head``; nothing else.
REVEALS = re.compile(
    r"""^(?:cd\s+(?P<cd>"[^"]+"|'[^']+'|\S+)\s*&&\s*)?git\s+"""
    r"""(?:rev-parse\s+(?:--short\s+)?HEAD|log(?:\s+(?:-\d+|-n\s*\d+|--oneline|--no-decorate"""
    r"""|--format=(?:'[^']*'|"[^"]*"|\S+)))*)(?:\s*\|\s*head(?:\s+-n?\s*\d+)?)?\s*$""")
HASH_LINE = re.compile(r"^([0-9a-f]{7,40})(?:\s|$)", re.M)
HEREDOC = re.compile(r"(<<-?\s*['\"]?(\w+)['\"]?[^\n]*\n).*?\n[ \t]*\2[ \t]*(?=\n|$)", re.S)
EDIT_HEADER = re.compile(r"^\[([^\]\n]+?)(?:#[0-9A-Za-z]{4})?\]", re.M)


def _norm(path: str) -> str:
    """Absolute path with ``~`` and symlinks (``/tmp`` on macOS) resolved, so spellings of one place compare equal."""
    return os.path.realpath(os.path.expanduser(path.strip("\"'").replace("$HOME", str(HOME))))


def inside(path: str | None, root: str) -> bool:
    return path is not None and (path == root or path.startswith(root + "/"))


def recorded_root(cwd: str, root: str) -> str:
    """The repository top level as the session spelled it (its cwd without the subdirectory below the top level)."""
    rel = os.path.relpath(_norm(cwd), root)
    return cwd if rel == "." else cwd.removesuffix("/" + rel)


def repo_forms(root: str, spelled: str = "") -> list[str]:
    forms = [root] + ([spelled] if spelled and spelled != root else [])
    if root.startswith(str(HOME) + "/"):
        forms += ["~" + root[len(str(HOME)):], "$HOME" + root[len(str(HOME)):]]
    if spelled.startswith(str(HOME) + "/"):
        forms += ["~" + spelled[len(str(HOME)):], "$HOME" + spelled[len(str(HOME)):]]
    return forms


def resolve_path(arg: str, cwd: str | None, variables: dict[str, str | None]) -> str | None:
    """Absolute form of a shell word, or None when it depends on something not known statically."""
    arg = arg.strip("\"'")
    unknown = False

    def sub(m):
        nonlocal unknown
        name = m.group(1) or m.group(2)
        if name == "HOME":
            return str(HOME)
        value = variables.get(name)
        unknown = unknown or value is None
        return value or ""
    arg = re.sub(r"\$(?:\{(\w+)\}|(\w+))", sub, arg)
    if unknown or re.search(r"[$`*?(]", arg):
        return None
    arg = os.path.expanduser(arg)
    if not os.path.isabs(arg):
        if cwd is None:
            return None
        arg = os.path.join(cwd, arg)
    return os.path.realpath(arg)


def bash_touches_repo(command: str, cwd: str | None, root: str, spelled: str = "") -> bool:
    """Whether a HEAD-moving command in this bash call could have acted on the repository.

    Walks the command piece by piece, following ``cd`` and simple variable
    assignments. A moving command counts if it ran inside the repository, ran
    where the directory cannot be told, or names the repository anywhere.
    """
    command = HEREDOC.sub(r"\1", command)
    variables: dict[str, str | None] = {}
    for piece in re.split(r"&&|\|\||;|\n|\|", command):
        piece = piece.strip().removeprefix("export ").strip()
        assign = re.fullmatch(r"(\w+)=(\S*)", piece)
        if assign:
            variables[assign.group(1)] = resolve_path(assign.group(2), cwd, variables)
            continue
        change = re.fullmatch(r"(?:cd|pushd)(?:\s+(\S+))?", piece)
        if change:
            cwd = resolve_path(change.group(1) or "~", cwd, variables)
            continue
        if not MOVES_HEAD.search(piece):
            continue
        where = cwd
        aimed = re.search(r"\bgit\s+(?:-c\s+\S+\s+)*-C\s+(\S+)", piece)
        if aimed:
            where = resolve_path(aimed.group(1), cwd, variables)
        if where is None or inside(where, root) or any(f in piece for f in repo_forms(root, spelled)):
            return True
    return False


def revealed_commit(command: str, output: str, cwd: str | None, root: str) -> str | None:
    """Commit printed by a command that shows HEAD (see REVEALS) and ran in the repository."""
    m = REVEALS.match(HEREDOC.sub(r"\1", command).strip())
    if not m:
        return None
    where = resolve_path(m.group("cd"), cwd, {}) if m.group("cd") else cwd
    if not inside(where, root):
        return None
    first = HASH_LINE.search(output)
    return first.group(1) if first else None


def edited_paths(call: dict, cwd: str) -> list[str] | None:
    """Absolute paths a file-tool call touches; None when they cannot be read from the arguments."""
    args = call.get("arguments") or {}
    raw = [args[k] for k in ("path", "file_path") if isinstance(args.get(k), str)]
    raw += EDIT_HEADER.findall(args["input"]) if isinstance(args.get("input"), str) else []
    raw += [p for p in args.get("paths") or [] if isinstance(p, str)]
    paths = [resolve_path(p, cwd, {}) for p in raw]
    return None if not paths or None in paths else paths


def derive_commit(rows: list[dict], turn: int, root: str | None = None) -> str:
    """Commit the repository was on just before user message ``turn``; raises Unrebuildable.

    ``root`` is the repository top level (default: the session's cwd). Anything
    that may have moved HEAD or changed the working tree without printing the
    commit clears it, so the turn is skipped rather than guessed.
    """
    turns = user_turn_indexes(rows)
    header = next((r for r in rows if r.get("type") == "session"), None)
    if header is None:
        raise Unrebuildable("no session header")
    session_cwd = _norm(header["cwd"])
    root = _norm(root or session_cwd)
    spelled = recorded_root(header["cwd"], root)
    calls: dict[str, dict] = {}
    commit: str | None = None
    why = "no git output that names the checked-out commit"
    for r in rows[:turns[turn]]:
        msg = r.get("message") or {}
        if msg.get("role") == "assistant":
            for block in msg.get("content") or []:
                if not (isinstance(block, dict) and block.get("type") == "toolCall"):
                    continue
                calls[block["id"]] = block
                name = block.get("name")
                args = block.get("arguments") or {}
                if name in SAFE_TOOLS:
                    continue
                if name in FILE_TOOLS:
                    paths = edited_paths(block, session_cwd)
                    if paths is None or any(inside(p, root) for p in paths):
                        commit, why = None, "files in the repository were edited (or the edit's path is unreadable)"
                elif name == "bash":
                    cwd = resolve_path(args["cwd"], session_cwd, {}) if args.get("cwd") else session_cwd
                    if bash_touches_repo(args.get("command", ""), cwd, root, spelled):
                        commit, why = None, "a command that can move HEAD ran in or named the repository"
                else:
                    commit, why = None, f"tool {name!r} can run commands"
        elif msg.get("role") == "toolResult" and msg.get("toolName") == "bash":
            args = (calls.get(msg.get("toolCallId")) or {}).get("arguments") or {}
            cwd = (resolve_path(args["cwd"], session_cwd, {}) if args.get("cwd")
                   else (_norm((msg.get("details") or {}).get("cwd") or session_cwd)))
            shown = revealed_commit(args.get("command", ""), message_text(r), cwd, root)
            if shown:
                commit, why = shown, ""
    if not commit:
        raise Unrebuildable(why)
    return commit


# --- rebuilding the repository ----------------------------------------------


def git_out(*args: str, cwd: Path | None = None, env: dict | None = None) -> str:
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout


def ensure_cache(remote: str) -> Path:
    """Bare cache of the GitHub remote under the sandbox root; created once and refreshed on demand."""
    name = re.sub(r"[^\w.-]+", "_", remote.split("://")[-1].removesuffix(".git"))
    cache = SANDBOX_ROOT / "cache" / f"{name}-{hashlib.sha256(remote.encode()).hexdigest()[:6]}.git"
    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        staging = cache.with_name(f".{cache.name}.{uuid.uuid4().hex[:8]}")
        git_out("clone", "--bare", "-q", remote, str(staging))
        staging.rename(cache)
    return cache


def refresh_cache(cache: Path) -> None:
    """Fetch every branch and pull request head (``refs/pull/N/head``) of the remote into the cache."""
    for ref in git_out("for-each-ref", "--format=%(refname)", "refs/pull", cwd=cache).split():
        if re.fullmatch(r"refs/pull/\d+", ref):  # an older cache stored heads as refs/pull/N, which blocks refs/pull/N/head
            git_out("update-ref", "-d", ref, cwd=cache)
    git_out("fetch", "-q", "origin", "+refs/heads/*:refs/heads/*", "+refs/pull/*/head:refs/pull/*/head", cwd=cache)


def resolve_commit(cache: Path, short: str, not_after: datetime) -> str:
    """Full hash of ``short`` in the cache, fetching once if it is missing; it must not postdate the turn."""
    def lookup() -> str | None:
        done = subprocess.run(["git", "rev-parse", "--verify", "-q", f"{short}^{{commit}}"], cwd=cache,
                              capture_output=True, text=True)
        return done.stdout.strip() or None
    full = lookup()
    if full is None:
        refresh_cache(cache)
        full = lookup()
    if full is None:
        raise Unrebuildable(f"commit {short} not in the remote's branches or pull requests")
    stamp = datetime.fromisoformat(git_out("show", "-s", "--format=%cI", full, cwd=cache).strip())
    if stamp > not_after:
        raise Unrebuildable(f"commit {short} is dated {stamp.isoformat()}, after the turn")
    return full


def drop_once(text: str, heading: str) -> str:
    """``drop_heading``, but the heading must appear exactly once (any level), or SystemExit."""
    count = len(re.findall(rf"^#+ {re.escape(heading)}\s*$", text, flags=re.M))
    if count != 1:
        raise SystemExit(f"heading {heading!r} appears {count} times; a drop needs exactly one")
    return drop_heading(text, heading)


def build_repo(run: Path, cache: Path, commit: str, global_file: str | None, env: dict,
               drops: list[list[str]] | None = None) -> Path:
    """Clone the cache into the run folder, with a private origin so a push cannot reach the cache.

    ``drops`` ([path in the repository, heading]) removes a heading and its subsections from a file of
    the checkout and folds that into the checked-out commit (``--amend``, with the original author,
    committer, dates and message), so history looks the same in every arm except the hash and the
    session starts with a clean ``git status``. Local branches that pointed at the original commit
    move to the amended one; remote-tracking refs are left alone.
    """
    origin = run / "origin.git"
    git_out("clone", "--bare", "--no-hardlinks", "-q", str(cache), str(origin), env=env)
    repo = run / "repo"
    git_out("clone", "-q", str(origin), str(repo), env=env)
    git_out("checkout", "-q", "--detach", commit, cwd=repo, env=env)
    for path, heading in drops or []:
        target = repo / path
        if not target.is_file():
            raise SystemExit(f"repo drop: {path} is not in commit {commit[:7]}")
        target.write_text(drop_once(target.read_text(), heading))
    if drops:
        fields = git_out("show", "-s", "--format=%an%n%ae%n%aI%n%cn%n%ce%n%cI", cwd=repo, env=env).splitlines()
        names = ["AUTHOR_NAME", "AUTHOR_EMAIL", "AUTHOR_DATE", "COMMITTER_NAME", "COMMITTER_EMAIL", "COMMITTER_DATE"]
        amend_env = dict(env, **{f"GIT_{n}": v for n, v in zip(names, fields)})
        original = git_out("rev-parse", "HEAD", cwd=repo, env=env).strip()
        git_out("commit", "-q", "--amend", "--no-edit", "-a", cwd=repo, env=amend_env)
        amended = git_out("rev-parse", "HEAD", cwd=repo, env=env).strip()
        for ref in git_out("for-each-ref", "--points-at", original, "--format=%(refname)", "refs/heads", cwd=repo, env=env).split():
            git_out("update-ref", ref, amended, cwd=repo, env=env)
    if global_file is not None:
        (repo / "GLOBAL.md").write_text(global_file)
        with (repo / ".git" / "info" / "exclude").open("a") as fh:
            fh.write("GLOBAL.md\n")
    return repo


# --- proposing a commit (never applied) ---------------------------------------

NEW_BRANCH = re.compile(r"\bgit\b[^\n;&|]*?(?:\bcheckout\s+-[bB]|\bswitch\s+-[cC]|\bworktree\s+add\b[^\n;&|]*?\s-[bB])\s+(['\"]?[\w./-]+)")
STATUS_BRANCH = re.compile(r"^## (\S+?)(?:\.\.\.\S+)?(?: \[.*\])?$", re.M)
BRANCH_OUTPUT = [re.compile(r"^On branch (\S+)", re.M), STATUS_BRANCH,
                 re.compile(r"^\[([^\]\s]+)(?: \(root-commit\))? [0-9a-f]{7,40}\]", re.M)]
LEADING_CD = re.compile(r"^\s*cd\s+(\"[^\"]+\"|'[^']+'|\S+)\s*(?:&&|;)")


def branch_evidence(rows: list[dict], turn: int, root: str) -> tuple[str, str, str] | None:
    """The last branch the session's own output names before the turn: (kind, name, how).

    ``kind`` is ``branch`` for a branch name (``On branch``, ``git status -sb``,
    ``git branch --show-current``, a commit summary line, ``checkout -b``,
    ``worktree add -b``) and ``worktree`` for a ``<repo>.wt-<name>`` directory
    the session worked in, whose name is a slug of the branch. Only commands
    that ran in the repository or one of its worktrees count.
    """
    header = next(r for r in rows if r.get("type") == "session")
    session_cwd = _norm(header["cwd"])
    root = _norm(root)
    calls: dict[str, dict] = {}
    found: tuple[str, str, str] | None = None
    for r in rows[:user_turn_indexes(rows)[turn]]:
        msg = r.get("message") or {}
        if msg.get("role") == "assistant":
            for block in msg.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "toolCall":
                    calls[block["id"]] = block
        elif msg.get("role") == "toolResult" and msg.get("toolName") == "bash":
            args = (calls.get(msg.get("toolCallId")) or {}).get("arguments") or {}
            command, output = args.get("command", ""), message_text(r)
            cwd = (resolve_path(args["cwd"], session_cwd, {}) if args.get("cwd")
                   else _norm((msg.get("details") or {}).get("cwd") or session_cwd))
            lead = LEADING_CD.match(command)
            if re.search(r"\bcd\s|\bpushd\b|\bgit\s+(?:-c\s+\S+\s+)*-C\s", command[lead.end():] if lead else command):
                continue  # the directory changes after the start, so where the output came from is unknown
            where = resolve_path(lead.group(1), cwd, {}) if lead else cwd
            if where is None:
                continue
            if where.startswith(root + ".wt-"):
                # The directory name is evidence; branch output from a sibling worktree is not (only the
                # session's own worktree, which is ``root`` itself, is read below).
                found = ("worktree", where[len(root) + 4:].split("/")[0], f"worktree directory {os.path.basename(where)}")
                continue
            if not inside(where, root):
                continue
            for m in NEW_BRANCH.finditer(command):
                found = ("branch", m.group(1).strip("'\""), "created by " + m.group(0)[:60])
            if re.search(r"\bbranch\s+--show-current\b", command):
                first = output.strip().splitlines()[0] if output.strip() else ""
                if re.fullmatch(r"[\w./-]+", first):
                    found = ("branch", first, "git branch --show-current")
            for pattern in BRANCH_OUTPUT:
                if pattern is STATUS_BRANCH and not re.search(r"\bgit\s+status\b[^|;&\n]*(?:\s-\w*b|--branch)", command):
                    continue  # a "## heading" line is only a branch line in ``git status -sb``
                names = pattern.findall(output)
                if names:
                    found = ("branch", names[-1], "named in git output")
    return found


_PR_HEADS: dict[str, dict[int, str]] = {}


def pr_head_names(remote: str) -> dict[int, str]:
    """Head branch name of every pull request of a GitHub remote (the refs/pull refs do not carry it)."""
    if remote not in _PR_HEADS:
        repo = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?$", remote)
        if not repo:
            raise Unrebuildable(f"{remote} is not a GitHub remote")
        listing = subprocess.run(["gh", "pr", "list", "--repo", repo.group(1), "--state", "all", "--limit", "2000",
                                  "--json", "number,headRefName"], capture_output=True, text=True, check=True).stdout
        _PR_HEADS[remote] = {p["number"]: p["headRefName"] for p in json.loads(listing)}
    return _PR_HEADS[remote]


def locate_commit(rows: list[dict], turn: int, root: str, cache: Path, pr_heads: dict[int, str]) -> dict:
    """Propose the commit for a turn from the branch the session was on; a proposal, never used by itself.

    The candidate is the last commit, by committer date at or before the turn,
    on the branch (``refs/heads``) and on every pull request head whose branch
    name matches. When those refs give different commits, or none exists, no
    candidate is returned.
    """
    when = datetime.fromisoformat(rows[user_turn_indexes(rows)[turn]]["timestamp"].replace("Z", "+00:00"))
    result = {"candidate": None, "turn_time": when.isoformat()}
    evidence = branch_evidence(rows, turn, root)
    if evidence is None:
        return {**result, "reason": "the session names no branch before the turn"}
    kind, name, how = evidence
    result.update(branch=name, evidence=how)

    def matches(branch: str) -> bool:
        return branch == name if kind == "branch" else name in (branch.replace("/", "-"), branch.split("/", 1)[-1])
    refs = [f"refs/heads/{b}" for b in git_out("for-each-ref", "--format=%(refname:short)", "refs/heads", cwd=cache).split()
            if matches(b)]
    refs += [f"refs/pull/{n}/head" for n, head in sorted(pr_heads.items()) if matches(head)]
    answers: dict[str, str] = {}
    for ref in refs:
        done = subprocess.run(["git", "rev-list", "-1", f"--before={int(when.timestamp())}", ref], cwd=cache,
                              capture_output=True, text=True)
        if done.returncode == 0 and done.stdout.strip():
            answers.setdefault(done.stdout.strip(), ref)
    if not answers:
        return {**result, "reason": f"no commit on {sorted(refs) or 'any ref'} is dated at or before the turn"}
    if len(answers) > 1:
        return {**result, "reason": "ambiguous: " + ", ".join(f"{ref} -> {c[:9]}" for c, ref in answers.items())}
    (commit, ref), = answers.items()
    stamp = git_out("show", "-s", "--format=%cI", commit, cwd=cache).strip()
    return {**result, "candidate": commit, "ref": ref, "commit_time": stamp}


def locate_turns(session: Path, turns: list[int] | None = None, remote: str | None = None,
                 pr_heads: dict[int, str] | None = None, cache: Path | None = None) -> list[dict]:
    """``locate_commit`` for the given turns (default all); the cache is refreshed once."""
    rows = read_session(session)
    header = next(r for r in rows if r.get("type") == "session")
    root = repository_root(header["cwd"])
    if cache is None:
        remote = remote or git_out("config", "--get", "remote.origin.url", cwd=root).strip()
        cache = ensure_cache(remote)
        refresh_cache(cache)
        pr_heads = pr_head_names(remote) if pr_heads is None else pr_heads
    results = []
    for n in turns if turns is not None else range(len(user_turn_indexes(rows))):
        try:
            results.append({"turn": n, **locate_commit(rows, n, str(root), cache, pr_heads or {})})
        except Unrebuildable as exc:
            results.append({"turn": n, "candidate": None, "reason": str(exc)})
    return results


# --- isolation proof --------------------------------------------------------


def fingerprint(repo: Path, session: Path) -> dict:
    """Facts about the user's originals that a replay must leave unchanged."""
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")  # a status must not refresh the user's index
    status = subprocess.run(["git", "status", "--porcelain"], cwd=repo, env=env, capture_output=True, text=True).stdout
    tracked = subprocess.run(["git", "ls-files", "-z"], cwd=repo, env=env, capture_output=True).stdout.split(b"\0")
    stamps = hashlib.sha256()
    for name in sorted(t for t in tracked if t):
        try:
            stamps.update(name + b"\0" + str(os.stat(repo / name.decode()).st_mtime_ns).encode() + b"\n")
        except OSError:
            stamps.update(name + b"\0missing\n")
    return {"status": hashlib.sha256(status.encode()).hexdigest()[:16], "status_lines": len(status.splitlines()),
            "mtimes": stamps.hexdigest()[:16], "session": file_hash(session)}


# --- running one replay -----------------------------------------------------


def repository_root(cwd: str) -> Path:
    """Top level of the repository holding the session's recorded directory."""
    return Path(git_out("rev-parse", "--show-toplevel", cwd=Path(cwd)).strip())


BLOCKED_PUSH = ["https://github.com/", "git@github.com:", "ssh://git@github.com/"]


def deny_profile(base: str, repo: Path, session: Path, cache_root: Path) -> str:
    """The shared profile plus what a replay must not see or change.

    Hidden: the original repository, the folder holding the original session
    (the real session store holds the later turns), and ``~/.ssh``. Not
    writable: the bare cache the repository is rebuilt from.
    """
    hidden = {repo, session.resolve().parent, SESSIONS_DIR, HOME / ".ssh"}
    return (base.rstrip() + "\n(deny file-read* file-write*\n"
            + "".join(f'  (subpath "{p}")\n' for p in sorted(map(str, hidden)))
            + f')\n(deny file-write*\n  (subpath "{cache_root}")\n)\n')


def session_label(session: Path) -> str:
    return session.stem.split("_")[-1][:8]


def replay_one(session: Path, turn: int, arm: dict, out: Path, cache_root: Path, ledger: Ledger,
               checks: dict[str, str] | None = None, model: str = MODEL, rep: int = 0,
               runner=subprocess.run, remote: str | None = None, commit: str | None = None,
               commit_evidence: str | None = None) -> dict:
    """Replay user message ``turn`` of ``session`` under ``arm``; returns the result, which is also saved.

    ``commit`` pins the repository state (with the reason in ``commit_evidence``)
    instead of deriving it from the session; the result records which was used.
    Raises Unrebuildable (after recording it) when the repository state cannot
    be established, RuntimeError when the model run fails or another model
    answers. The sandbox, which holds real session text, is always removed.
    """
    if bool(commit) != bool(commit_evidence):
        raise ValueError("a pinned commit needs commit_evidence, and evidence needs a commit")
    if commit and not re.fullmatch(r"[0-9a-f]{7,40}", commit):
        raise ValueError(f"--commit must be 7 to 40 lowercase hex digits, not {commit!r}")
    checks = checks or {}
    sid = f"replay-{session_label(session)}-{turn}"
    result_path = out / "results" / f"{sid}__{arm['name']}__{rep}.json"
    if result_path.exists():
        done = json.loads(result_path.read_text())["replay"]
        if (done["commit_source"] == "pinned") != bool(commit) or (commit and not done["commit"].startswith(commit)):
            raise RuntimeError(f"{result_path} was made with a different commit ({done['commit_source']} {done['commit'][:9]}); use a new --out")
        return json.loads(result_path.read_text())
    rows = read_session(session)
    header = next(r for r in rows if r.get("type") == "session")
    turn_rows = user_turn_indexes(rows)
    target = rows[turn_rows[turn]]
    prompt = message_text(target)
    if not prompt.strip() or any(isinstance(b, dict) and b.get("type") != "text"
                                 for b in (target["message"]["content"] if isinstance(target["message"]["content"], list) else [])):
        raise Unrebuildable("the prompt is empty or holds non-text content")
    run = SANDBOX_ROOT / uuid.uuid4().hex[:12]
    try:
        try:
            original_repo = repository_root(header["cwd"])
            before = fingerprint(original_repo, session)
            short = commit or derive_commit(rows, turn, str(original_repo))
            remote = remote or git_out("config", "--get", "remote.origin.url", cwd=original_repo).strip()
            cache = ensure_cache(remote)
            when = datetime.fromisoformat(target["timestamp"].replace("Z", "+00:00"))
            commit_full = resolve_commit(cache, short, when)
        except (Unrebuildable, subprocess.CalledProcessError, FileNotFoundError, KeyError) as exc:
            reason = str(exc) if isinstance(exc, Unrebuildable) else f"{type(exc).__name__}: {exc}"[:200]
            folder = out / "unrebuildable"
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"{sid}.json").write_text(json.dumps({"scenario": sid, "reason": reason}, indent=1))
            raise Unrebuildable(reason) from exc
        ledger.admit(model)
        run.mkdir(parents=True)
        (run / "gh").mkdir()
        (run / "gitconfig").write_text("[user]\n\tname = Joe Harris\n\temail = joeharris76@gmail.com\n"
                                       "[init]\n\tdefaultBranch = main\n[advice]\n\tdetachedHead = false\n"
                                       + '[url "invalid://blocked/"]\n'  # a push to the real remote cannot resolve
                                       + "".join(f"\tpushInsteadOf = {u}\n" for u in BLOCKED_PUSH))
        env = dict(os.environ, RUN=str(run), GIT_CONFIG_GLOBAL=str(run / "gitconfig"), GIT_CONFIG_NOSYSTEM="1",
                   PATH=f"{SANDBOX_ROOT / 'shims'}:{os.environ['PATH']}", GH_SHIM_LOG=str(run / "gh.log"),
                   GH_CANNED=str(run / "gh"), GH_TOKEN="sandbox", GH_CONFIG_DIR=str(run / "ghcfg"),
                   CMDS=str(run / "cmds.txt"), FINAL=str(run / "final.txt"), HARNESS=str(HERE), CACHE=str(cache_root))
        env.pop("SSH_AUTH_SOCK", None)
        text = global_text(arm["global"], arm.get("fixture", PHASE2_FIXTURE))
        for old, new in arm.get("edits", []):
            if text is None or old not in text:
                raise SystemExit(f"arm {arm['name']}: text to replace not found")
            text = text.replace(old, new)
        repo = build_repo(run, cache, commit_full, text, env, arm.get("repo_drops"))
        base = git_out("rev-parse", "HEAD", cwd=repo, env=env).strip()  # the checked-out commit, or its amended form when the arm drops text
        (run / "base").write_text(base)
        sessions = run / "sessions"
        sessions.mkdir()
        copy = sessions / session.name
        kept_rows = pin_model(truncate(rows, turn), model)
        recorded = os.path.relpath(_norm(header["cwd"]), original_repo)  # same subdirectory as recorded
        spelled = recorded_root(header["cwd"], str(original_repo))
        copy.write_text(rewritten_lines(kept_rows, [spelled, str(original_repo)], str(repo)))
        workdir = repo / recorded
        if not workdir.is_dir():
            raise Unrebuildable(f"the recorded directory {recorded} is not in commit {commit_full[:7]}")
        overlay = run / "overlay.yml"
        overlay.write_text(
            "contextFiles:\n  extra:\n    - GLOBAL.md\ndisabledProviders:\n"
            + "".join(f"  - {p}\n" for p in DISABLED_PROVIDERS)
            + f"skills:\n  customDirectories:\n    - {skills_dir(arm['skills'], cache_root, arm.get('descriptions'), arm.get('skill_drops'))}\n"
            + "retry:\n  fallbackChains: {}\n  usageAwareFallback: false\n")
        profile = run / "deny.sb"
        profile.write_text(deny_profile((SANDBOX_ROOT / "deny.sb").read_text(), original_repo, session, cache_root))
        cmd = ["sandbox-exec", "-f", str(profile), "omp", "--resume", str(copy), "-p", "--mode", "json",
               "--model", model, "--config", str(overlay), "--cwd", str(workdir), "--session-dir", str(sessions),
               "--no-title", "--auto-approve", "--max-time", "900", "--max-cost", f"{recorded_cost(kept_rows) + MAX_REPLAY_COST:.2f}", prompt]
        events: list[dict] = []
        stdout = ""
        try:
            proc = runner(cmd, env=env, capture_output=True, text=True, timeout=1200)
            stdout = proc.stdout
            events = parse_events(stdout)
        except subprocess.TimeoutExpired as exc:
            events = parse_events(exc.stdout)
            raise RuntimeError("replayed turn timed out") from exc
        finally:
            ledger.add(model, turn_cost(events))  # a failed turn is spent too
        if proc.returncode != 0 or not any(ev.get("type") == "agent_end" for ev in events):
            raise RuntimeError(f"replayed turn failed (exit {proc.returncode}, ${turn_cost(events):.2f}): {proc.stderr.strip()[-200:]} {stdout[-300:]}")
        wanted = model.split("/", 1)[-1]
        answered = {(ev.get("message") or {}).get("model") for ev in events
                    if ev.get("type") == "message_end" and (ev.get("message") or {}).get("role") == "assistant"}
        if answered - {wanted}:
            raise RuntimeError(f"replayed turn answered by {sorted(answered)}, not {wanted}")
        (run / "final.0.txt").write_text(final_text(events))
        (run / "final.txt").write_text(final_text(events))
        (run / "cmds.txt").write_text(bash_commands(events))
        kept = out / "transcripts" / result_path.stem
        kept.mkdir(parents=True, exist_ok=True)
        for name in ("cmds.txt", "final.txt", "final.0.txt"):
            shutil.copy(run / name, kept / name)
        env["BASE"] = base
        passed = {name: subprocess.run(["bash", "-c", script], cwd=repo, env=env, capture_output=True).returncode == 0
                  for name, script in checks.items()}
        after = fingerprint(original_repo, session)
        result = {"scenario": sid, "arm": arm["name"], "rep": rep, "model": model, "run": run.name, "turns": 1,
                  "prereg": None, "checks_digest": hashlib.sha256(json.dumps(checks, sort_keys=True).encode()).hexdigest()[:16],
                  "checks": passed, "metrics": {}, "cost": round(turn_cost(events), 4),
                  "tool_calls": sum(ev.get("type") == "tool_execution_start" for ev in events),
                  "skills_read": sorted(set(re.findall(r"skill://([\w-]+)", stdout))),
                  "replay": {"session": session.name, "turn": turn, "commit": commit_full, "remote": remote,
                             "commit_source": "pinned" if commit else "derived", "base": base,
                             "repo_drops": arm.get("repo_drops"),
                             "commit_evidence": commit_evidence or f"{short} shown by git rev-parse or git log in the session",
                             "rows_kept": len(kept_rows), "isolation": {"before": before, "after": after,
                                                                               "unchanged": before == after}}}
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(result, indent=1))
        return result
    finally:
        shutil.rmtree(run, ignore_errors=True)


# --- command line -----------------------------------------------------------


def list_turns(session: Path) -> None:
    rows = read_session(session)
    root = str(repository_root(next(r for r in rows if r.get("type") == "session")["cwd"]))
    for n, i in enumerate(user_turn_indexes(rows)):
        try:
            state = derive_commit(rows, n, root)
        except Unrebuildable as exc:
            state = f"unrebuildable: {exc}"
        print(f"{n:3d}  {rows[i]['timestamp']}  {state:40.40}  {message_text(rows[i])[:80]!r}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["list", "locate", "run"])
    ap.add_argument("--session", type=Path, required=True)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--turn", type=int, action="append")
    ap.add_argument("--global", dest="global_spec", default="full", help="global text arm (see README)")
    ap.add_argument("--arm-name")
    ap.add_argument("--arm-json", help="extra arm fields as JSON, e.g. edits or identity_hook")
    ap.add_argument("--skills", default=PHASE2_SKILLS, help="catalog revision for the arm's skills")
    ap.add_argument("--fixture", default=PHASE2_FIXTURE)
    ap.add_argument("--check", action="append", default=[], help="name=shell script, run in the sandbox repository")
    ap.add_argument("--check-file", type=Path, help="JSON object of name: shell script")
    ap.add_argument("--rep", type=int, default=0)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--remote", help="override the repository's origin URL")
    ap.add_argument("--commit", help="pin the repository state to this commit instead of deriving it from the session")
    ap.add_argument("--commit-evidence", help="why this commit is the state at the turn (recorded in the result)")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--ledger", type=Path)
    args = ap.parse_args()
    if args.action == "locate":
        for found in locate_turns(args.session, args.turn, args.remote):
            print(json.dumps(found))
        return
    if args.action == "list":
        list_turns(args.session)
        return
    if not args.out or not args.turn:
        raise SystemExit("run needs --out and at least one --turn")
    if bool(args.commit) != bool(args.commit_evidence):
        raise SystemExit("--commit and --commit-evidence go together")
    if args.commit and len(args.turn) != 1:
        raise SystemExit("a pinned commit applies to one turn")
    checks = json.loads(args.check_file.read_text()) if args.check_file else {}
    checks.update(c.split("=", 1) for c in args.check)
    arm = {"name": args.arm_name or args.global_spec, "global": args.global_spec, "skills": args.skills,
           "fixture": args.fixture, **json.loads(args.arm_json or "{}")}
    out = args.out
    ledger = Ledger(args.ledger or out.resolve().parent / "ledger.json")
    prepare_sandbox_root()
    pin_baseline(out, baseline(args.model, args.smoke))
    skipped = ran = 0
    for turn in args.turn:
        try:
            r = replay_one(args.session, turn, arm, out, SANDBOX_ROOT / "cache", ledger, checks, args.model,
                           args.rep, remote=args.remote,
                           commit=args.commit, commit_evidence=args.commit_evidence)
            ran += 1
            print(turn, r["checks"], f"${r['cost']}", "isolation unchanged:", r["replay"]["isolation"]["unchanged"], flush=True)
        except Unrebuildable as exc:
            skipped += 1
            print(turn, "UNREBUILDABLE", exc, flush=True)
        except Exception as exc:  # one failed turn must not stop the others
            print(turn, "ERROR", repr(exc)[:300], flush=True)
    print(f"replayed {ran}, unrebuildable {skipped}")


if __name__ == "__main__":
    main()
