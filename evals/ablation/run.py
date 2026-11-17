"""Ablation runner: the same task, with and without one unit of instruction text.

Each session is a headless ``omp`` run in a throwaway repository. An arm fixes
which global instruction text and which skills revision the agent sees; nothing
else differs. Checks are shell commands run against the sandbox afterwards.

Usage:
    run.py run --out DIR [--scenario ID ...] [--reps 30] [--jobs 6] [--smoke] [--harness omp|claude-code]
    run.py report --out DIR [--out DIR ...]
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
CATALOG = HERE.parents[1]
MODEL = "anthropic/claude-sonnet-5-5"
SANDBOX_ROOT = Path("/tmp/omp-ablation")
PREREG = HERE / "prereg"
DEFAULT_REPS = 30
SPEND_CEILING = 800.0  # USD on Claude providers, for the whole phase
DISABLED_PROVIDERS = ["agents", "claude", "codex", "gemini", "opencode", "github",
                      "claude-plugins", "omp-plugins", "agent-plugins", "cursor", "windsurf", "cline"]

sys.path.insert(0, str(HERE))
from scenarios import SCENARIOS as PILOT_SCENARIOS  # noqa: E402
from scenarios2 import SCENARIOS2  # noqa: E402
import judge  # noqa: E402
from stats import compare, fisher, rule_decision  # noqa: E402

SCENARIOS = PILOT_SCENARIOS + SCENARIOS2


class LedgerFull(RuntimeError):
    pass


class Ledger:
    """Spend across every run of a phase, shared by concurrent runner processes.

    Claude-provider cost counts against the ceiling; other providers (ChatGPT
    plan usage) are recorded but not capped.
    """

    def __init__(self, path: Path, ceiling: float = SPEND_CEILING):
        self.path, self.ceiling = path, ceiling

    @staticmethod
    def capped(model: str) -> bool:
        return model.startswith("anthropic/")

    def _update(self, change):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a+") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            fh.seek(0)
            raw = fh.read()
            data = json.loads(raw) if raw.strip() else {"capped_usd": 0.0, "uncapped_usd": 0.0, "turns": 0}
            result = change(data)
            fh.seek(0)
            fh.truncate()
            fh.write(json.dumps(data, indent=1))
            return result

    def admit(self, model: str) -> None:
        """Refuse a new session once capped spend has reached the ceiling."""
        spent = self._update(lambda d: d["capped_usd"])
        if self.capped(model) and spent >= self.ceiling:
            raise LedgerFull(f"spend ledger {self.path} at {spent:.2f} USD, ceiling {self.ceiling:.2f}")

    def add(self, model: str, cost: float) -> None:
        def change(d: dict) -> None:
            d["capped_usd" if self.capped(model) else "uncapped_usd"] += cost
            d["turns"] += 1
        self._update(change)


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def baseline(model: str, smoke: bool, harness: str = "omp") -> dict:
    """What a run folder's results depend on besides the arm; one folder holds one baseline."""
    version = HARNESSES[harness].version()
    fixtures = {p.name: file_hash(p) for p in sorted((HERE / "fixtures").glob("*.md"))}
    return {"harness": harness, "harness_version": version, "model": model, "smoke": smoke, "fixtures": fixtures}


def pin_baseline(out: Path, current: dict) -> None:
    path = out / "baseline.json"
    if path.exists():
        pinned = json.loads(path.read_text())
        changed = {k: (pinned.get(k), current.get(k)) for k in pinned.keys() | current.keys()
                   if pinned.get(k) != current.get(k)}
        if changed:
            raise SystemExit(f"{out} holds runs under another baseline {changed}; use a new --out")
        return
    if any((out / "results").glob("*.json")):
        raise SystemExit(f"{out} holds results with no recorded baseline; use a new --out")
    out.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(current, indent=1))


def checks_hash(scenario: dict) -> str:
    """Hash of what scores a session: the check scripts, which checks each rule's decision uses, and any
    judged checks. A scenario without judged checks keeps the hash it had before they existed."""
    scored = {"checks": scenario.get("checks", {}), "rules": scenario.get("rules", {})}
    if "judged" in scenario:
        scored["judged"] = scenario["judged"]
    return hashlib.sha256(json.dumps(scored, sort_keys=True).encode()).hexdigest()[:16]


def parse_events(stdout: str | bytes | None) -> list[dict]:
    if isinstance(stdout, bytes):
        stdout = stdout.decode(errors="replace")
    events = []
    for line in (stdout or "").splitlines():
        if line.startswith("{"):
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:  # a line cut off by a kill or timeout
                pass
    return events


def prereg_hash(scenario: dict, smoke: bool) -> str | None:
    """Hash of the scenario's pre-registration; scored runs of an experiment need one."""
    experiment = scenario.get("experiment")
    if not experiment:
        return None
    path = PREREG / f"{experiment}.md"
    if path.exists():
        return file_hash(path)
    if smoke:
        return None
    raise SystemExit(f"scenario {scenario['id']}: write {path} before scored runs, or use --smoke")


def git(*args: str, cwd: Path = CATALOG) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def drop_lines(text: str, spec: str) -> str:
    """Remove 1-based inclusive line ranges, e.g. ``17-24`` or ``5-6,91-92``."""
    lines = text.splitlines(keepends=True)
    gone: set[int] = set()
    for part in spec.split(","):
        lo, _, hi = part.partition("-")
        gone.update(range(int(lo), int(hi or lo) + 1))
    return "".join(line for n, line in enumerate(lines, 1) if n not in gone)


def drop_section(text: str, heading: str) -> str:
    """Remove one ``## heading`` section, up to the next ``## `` or end of file."""
    out, skipping, found = [], False, False
    for line in text.splitlines(keepends=True):
        if line.startswith("## "):
            skipping = line[3:].strip() == heading
            found = found or skipping
        if not skipping:
            out.append(line)
    if not found:
        raise SystemExit(f"no section named {heading!r}")
    return "".join(out)


def global_text(spec: str, fixture: str = "global-under-test.md") -> str | None:
    """Arm text for the global file: full | none | old | minus:<heading> | only:<heading> | lines:<ranges>.

    ``fixture`` is the snapshot ``full`` stands for; the pilot used global-under-test.md.
    """
    if spec == "none":
        return None
    if spec == "old":
        return (HERE / "fixtures" / "global-before-cleanup.md").read_text()
    # A snapshot, not the live file: line-range arms and past results stay valid when the file changes.
    full = (HERE / "fixtures" / fixture).read_text()
    if spec == "full":
        return full
    kind, _, arg = spec.partition(":")
    if kind == "minus":
        return drop_section(full, arg)
    if kind == "only":
        headings = [line[3:].strip() for line in full.splitlines() if line.startswith("## ")]
        for heading in headings:
            if heading != arg:
                full = drop_section(full, heading)
        if arg not in headings:
            raise SystemExit(f"no section named {arg!r}")
        return full
    if kind == "lines":
        return drop_lines(full, arg)
    raise SystemExit(f"unknown global arm {spec!r}")


def skills_dir(rev: str, cache: Path, descriptions: dict[str, str] | None = None) -> Path:
    """Export the catalog's skills at one revision, once; optionally with reworded descriptions."""
    descriptions = descriptions or {}
    tag = hashlib.sha256(json.dumps(descriptions, sort_keys=True).encode()).hexdigest()[:8] if descriptions else ""
    dest = cache / "skills" / (rev + tag)
    if not dest.exists():
        staging = cache / "skills" / f".{rev}{tag}.{uuid.uuid4().hex[:8]}"
        staging.mkdir(parents=True)
        archive = subprocess.run(["git", "archive", rev, "skills"], cwd=CATALOG, check=True, capture_output=True)
        subprocess.run(["tar", "-x", "-C", str(staging)], input=archive.stdout, check=True)
        for skill, text in descriptions.items():
            path = staging / "skills" / skill / "SKILL.md"
            path.write_text(re.sub(r"^description:.*$", lambda _: f"description: {json.dumps(text)}",
                                   path.read_text(), count=1, flags=re.M))
        staging.rename(dest)
    return dest / "skills"


def bash_commands(events: list[dict]) -> str:
    cmds = []
    for ev in events:
        if ev.get("type") == "tool_execution_start":
            args = ev.get("args") or {}
            cmds.append(f"[{ev.get('toolName')}] " + (args.get("command") or json.dumps(args))[:4000])
    return "\n".join(cmds) + "\n"


def final_text(events: list[dict]) -> str:
    texts = []
    for ev in events:
        msg = ev.get("message") or {}
        if ev.get("type") == "message_end" and msg.get("role") == "assistant":
            text = "".join(c.get("text", "") for c in msg.get("content", []) if c.get("type") == "text")
            if text.strip():
                texts.append(text)
    return texts[-1] if texts else ""


def session_env(run: Path, cache: Path) -> dict:
    """The environment a session's setup and checks run in; ``judge.py`` rebuilds it for evidence."""
    return dict(os.environ, RUN=str(run), GIT_CONFIG_GLOBAL=str(run / "gitconfig"), GIT_CONFIG_NOSYSTEM="1",
                PATH=f"{SANDBOX_ROOT / 'shims'}:{os.environ['PATH']}", GH_SHIM_LOG=str(run / "gh.log"),
                GH_CANNED=str(run / "gh"), GH_TOKEN="sandbox", GH_CONFIG_DIR=str(run / "ghcfg"),
                CMDS=str(run / "cmds.txt"), FINAL=str(run / "final.txt"), HARNESS=str(HERE), CACHE=str(cache))


def prepare_sandbox_root() -> None:
    """Copy the shims out of the checkout and write the profile that hides the user's own files.

    Sessions must not read other copies of the skills or instruction files on
    this machine; without the profile an agent that cannot resolve a skill
    reference searches the disk and finds one.
    """
    SANDBOX_ROOT.mkdir(parents=True, exist_ok=True)
    shutil.copytree(HERE / "shims", SANDBOX_ROOT / "shims", dirs_exist_ok=True)
    shutil.copytree(CATALOG / "deployment" / "global" / "hooks", SANDBOX_ROOT / "hooks", dirs_exist_ok=True)
    home = Path.home()
    hidden = ["Developer", ".agents", ".claude", ".claude.json", ".codex", ".gemini", ".tractable",
              ".skill-sync-deployment", "Documents", "Desktop"]
    # No session may run `security`: Claude Code's login token sits in the keychain. The keychain
    # service itself stays reachable, since other agents may use it.
    (SANDBOX_ROOT / "deny.sb").write_text(
        "(version 1)\n(allow default)\n(deny file-read* file-write*\n"
        + "".join(f'  (subpath "{home / name}")\n' for name in hidden) + ")\n"
        '(deny process-exec (literal "/usr/bin/security"))\n')


MAX_TURN_BUDGET = 3.0  # USD per turn, passed as --max-budget-usd and charged when a turn reports nothing


def turn_cost(events: list[dict]) -> float:
    return sum(((ev.get("message") or {}).get("usage") or {}).get("cost", {}).get("total", 0)
               for ev in events if ev.get("type") == "message_end")


class Omp:
    """One session driven through ``omp -p --mode json``."""

    name = "omp"
    cwd = None  # omp is given --cwd instead

    def __init__(self, run: Path, repo: Path):
        self.run, self.repo = run, repo
        self._sessions = 0

    @staticmethod
    def version() -> str:
        return subprocess.run(["omp", "--version"], capture_output=True, text=True, check=True).stdout.strip()

    @staticmethod
    def check_model(model: str) -> None:
        pass

    def prepare(self, arm: dict, cache: Path, text: str | None) -> None:
        if text is not None:
            (self.repo / "GLOBAL.md").write_text(text)
            with (self.repo / ".git" / "info" / "exclude").open("a") as fh:
                fh.write("GLOBAL.md\n")
        overlay = self.run / "overlay.yml"
        overlay.write_text(
            "contextFiles:\n  extra:\n    - GLOBAL.md\ndisabledProviders:\n"
            + "".join(f"  - {p}\n" for p in DISABLED_PROVIDERS)
            + f"skills:\n  customDirectories:\n    - {skills_dir(arm['skills'], cache, arm.get('descriptions'))}\n"
            # The user's config falls back to another model on a provider error; a session must not. An empty
            # fallbackChains map merges into the user's chains rather than replacing them, so switch fallback off.
            + "retry:\n  modelFallback: false\n  usageAwareFallback: false\n")

    def command(self, prompt: str, turn: int, turns: int, model: str, fresh: bool = False) -> list[str]:
        """``fresh`` starts a new session (another agent taking over); later turns continue the newest one."""
        if fresh:
            self._sessions += 1
        session = (["--no-session"] if turns == 1
                   else ["--session-dir", str(self.run / f"sessions{self._sessions}")] + ([] if fresh else ["--continue"]))
        return ["sandbox-exec", "-f", str(SANDBOX_ROOT / "deny.sb"),
                "omp", "-p", "--mode", "json", "--model", model, "--config", str(self.run / "overlay.yml"),
                "--cwd", str(self.repo), *session, "--no-title", "--auto-approve", "--max-time", "900",
                "--max-cost", "3", prompt]

    def env(self, env: dict) -> dict:
        return env

    @staticmethod
    def redact(stdout):
        return stdout

    charge = staticmethod(turn_cost)

    @staticmethod
    def cleanup() -> None:
        pass

    @staticmethod
    def finished(events: list[dict]) -> bool:
        return any(ev.get("type") == "agent_end" for ev in events)

    @staticmethod
    def failure_detail(events: list[dict]) -> str:
        return ""

    @staticmethod
    def answered(events: list[dict]) -> set:
        return {(ev.get("message") or {}).get("model") for ev in events
                if ev.get("type") == "message_end" and (ev.get("message") or {}).get("role") == "assistant"}

    @staticmethod
    def check_isolation(events: list[dict]) -> None:
        pass

    turn_cost = staticmethod(turn_cost)
    final_text = staticmethod(final_text)
    bash_commands = staticmethod(bash_commands)

    @staticmethod
    def tool_calls(events: list[dict]) -> int:
        return sum(ev.get("type") == "tool_execution_start" for ev in events)

    @staticmethod
    def skills_read(events: list[dict], stdout: list[str]) -> list[str]:
        return sorted(set(re.findall(r"skill://([\w-]+)", "".join(stdout))))

    @staticmethod
    def audit(events: list[dict]) -> dict:
        return {}


def claude_oauth_token() -> str:
    """The login token Claude Code needs, taken at run time.

    Claude Code keeps its login in the macOS keychain under a name that depends on
    its config directory, so a sandbox config directory cannot see it; the same
    token passed in the environment authenticates without exposing any of the
    user's ``~/.claude`` files. ``CLAUDE_CODE_OAUTH_TOKEN`` in the caller's
    environment (from ``claude setup-token``) takes precedence.
    """
    token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    if token:
        return token
    raw = subprocess.run(["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
                         capture_output=True, text=True)
    try:
        return json.loads(raw.stdout)["claudeAiOauth"]["accessToken"]
    except (json.JSONDecodeError, KeyError, TypeError):
        raise SystemExit("no Claude Code login found: run `claude auth login` or set CLAUDE_CODE_OAUTH_TOKEN") from None


def claude_blocks(events: list[dict], main_only: bool = False):
    """Content blocks of assistant events as (message id, block); ``main_only`` skips subagent messages."""
    for ev in events:
        if ev.get("type") != "assistant" or (main_only and ev.get("parent_tool_use_id")):
            continue
        msg = ev.get("message") or {}
        for block in msg.get("content") or []:
            yield msg.get("id"), block


class ClaudeCode:
    """One session driven through ``claude -p --output-format stream-json``.

    The arm's global text is the config directory's ``CLAUDE.md``, which is
    where a deployed global instruction file lives (user memory, not the system
    prompt), so the text carries the same authority as in real use. The arm's
    skills sit in the repository's ``.claude/skills``, excluded from git.
    ``user`` in ``--setting-sources`` means that sandbox directory, which holds
    nothing but the ``CLAUDE.md``; ``local`` settings stay out. With
    ``--setting-sources project`` alone Claude Code ignores user memory.
    """

    name = "claude-code"

    def __init__(self, run: Path, repo: Path):
        self.run, self.repo = run, repo
        self.cwd = repo
        self.session = str(uuid.uuid4())
        self._token = None
        self._total = 0.0

    @staticmethod
    def version() -> str:
        return subprocess.run(["claude", "--version"], capture_output=True, text=True, check=True).stdout.strip()

    @staticmethod
    def check_model(model: str) -> None:
        if not model.startswith("anthropic/"):
            raise SystemExit(f"claude-code runs Anthropic models only, not {model}")

    def prepare(self, arm: dict, cache: Path, text: str | None) -> None:
        config = self.run / "cfg"
        config.mkdir()
        if text is not None:
            (config / "CLAUDE.md").write_text(text)
        shutil.copytree(skills_dir(arm["skills"], cache, arm.get("descriptions")), self.repo / ".claude" / "skills")
        excluded = [".claude/"]
        if (self.repo / "AGENTS.md").exists() and not (self.repo / "CLAUDE.md").exists():
            # omp reads the repository's AGENTS.md itself; Claude Code reads CLAUDE.md, so point it there.
            (self.repo / "CLAUDE.md").write_text("@AGENTS.md\n")
            excluded.append("CLAUDE.md")
        with (self.repo / ".git" / "info" / "exclude").open("a") as fh:
            fh.write("".join(f"{p}\n" for p in excluded))

    def command(self, prompt: str, turn: int, turns: int, model: str, fresh: bool = False) -> list[str]:
        """``fresh`` starts a new session (another agent taking over); later turns resume the newest one."""
        if fresh and turn:
            self.session, self._total = str(uuid.uuid4()), 0.0
            # Another agent taking over starts cold: nothing the first session saved may reach it.
            shutil.rmtree(self.run / "cfg" / "projects", ignore_errors=True)
        session = ["--session-id", self.session] if fresh else ["--resume", self.session]
        return ["sandbox-exec", "-f", str(SANDBOX_ROOT / "deny.sb"),
                "claude", "-p", "--model", model.split("/", 1)[-1], "--output-format", "stream-json", "--verbose",
                "--setting-sources", "user,project", "--strict-mcp-config",
                "--dangerously-skip-permissions",  # only ever inside the deny profile above
                "--max-budget-usd", str(MAX_TURN_BUDGET), *session, prompt]

    def env(self, env: dict) -> dict:
        self._token = claude_oauth_token()
        kept = {k: v for k, v in env.items() if not k.startswith(("CLAUDE", "ANTHROPIC"))}
        return {**kept, "CLAUDE_CONFIG_DIR": str(self.run / "cfg"), "CLAUDE_CODE_OAUTH_TOKEN": self._token,
                "DISABLE_AUTOUPDATER": "1", "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"}

    def redact(self, text: str | bytes | None) -> str:
        """Remove the login token from output before it is parsed, saved or quoted in an error."""
        if isinstance(text, bytes):
            text = text.decode(errors="replace")
        text = text or ""
        return text.replace(self._token, "[redacted]") if self._token else text

    @staticmethod
    def finished(events: list[dict]) -> bool:
        return any(ev.get("type") == "result" and not ev.get("is_error") and ev.get("subtype") == "success"
                   for ev in events)

    @staticmethod
    def failure_detail(events: list[dict]) -> str:
        results = [ev for ev in events if ev.get("type") == "result"]
        return f"{results[-1].get('subtype')}: {results[-1].get('result', '')}" if results else "no result event"

    @staticmethod
    def answered(events: list[dict]) -> set:
        models = {ev["model"] for ev in events if ev.get("type") == "system" and ev.get("subtype") == "init"}
        for ev in events:
            if ev.get("type") == "assistant":
                models.add((ev.get("message") or {}).get("model"))
            elif ev.get("type") == "result":
                models.update((ev.get("modelUsage") or {}).keys())
        return models - {"<synthetic>"}  # Claude Code's marker for messages it wrote itself

    @staticmethod
    def init_events(events: list[dict]) -> list[dict]:
        return [ev for ev in events if ev.get("type") == "system" and ev.get("subtype") == "init"]

    @classmethod
    def check_isolation(cls, events: list[dict]) -> None:
        """Refuse a session that loaded anything outside the sandbox: user plugins or MCP servers."""
        for init in cls.init_events(events):
            outside = [p for p in init.get("plugins") or [] if p.get("path") != "builtin"]
            if outside or init.get("mcp_servers"):
                raise RuntimeError(f"session loaded plugins {outside} or MCP servers {init.get('mcp_servers')}")

    @staticmethod
    def turn_cost(events: list[dict]) -> float:
        """Cost so far. Claude Code restores the saved total on --resume, so within one session each result is
        cumulative (take the largest); a fresh session starts again from zero, so sessions add up."""
        totals: dict = {}
        for ev in events:
            if ev.get("type") == "result":
                sid = ev.get("session_id")
                totals[sid] = max(totals.get(sid, 0.0), ev.get("total_cost_usd") or 0.0)
        return sum(totals.values())

    def charge(self, events: list[dict]) -> float:
        """What this turn added to the session total; a turn that never reported is charged the budget cap."""
        if not any(ev.get("type") == "result" for ev in events):
            return MAX_TURN_BUDGET
        total = self.turn_cost(events)
        delta, self._total = max(total - self._total, 0.0), max(total, self._total)
        return delta

    def cleanup(self) -> None:
        """Drop Claude Code's own session logs, which hold the full transcript."""
        shutil.rmtree(self.run / "cfg" / "projects", ignore_errors=True)

    @staticmethod
    def final_text(events: list[dict]) -> str:
        texts: dict[str, str] = {}
        for msg_id, block in claude_blocks(events, main_only=True):
            if block.get("type") == "text":
                texts[msg_id] = texts.get(msg_id, "") + block.get("text", "")
        texts = {k: v for k, v in texts.items() if v.strip()}
        return list(texts.values())[-1] if texts else ""

    @staticmethod
    def tool_uses(events: list[dict]) -> list[dict]:
        return [block for _, block in claude_blocks(events) if block.get("type") == "tool_use"]

    @classmethod
    def bash_commands(cls, events: list[dict]) -> str:
        """One line per tool call, ``[tool] command``, as for omp; a loaded skill is ``[skill] skill://<name>``."""
        cmds = []
        for block in cls.tool_uses(events):
            args = block.get("input") or {}
            name = (block.get("name") or "").lower()
            if name == "skill":
                cmds.append(f"[skill] skill://{args.get('skill')}")
            else:
                cmds.append(f"[{name}] " + (args.get("command") or json.dumps(args))[:4000])
        return "\n".join(cmds) + "\n"

    @classmethod
    def tool_calls(cls, events: list[dict]) -> int:
        return len(cls.tool_uses(events))

    @classmethod
    def skills_read(cls, events: list[dict], stdout: list[str]) -> list[str]:
        return sorted({b["input"]["skill"] for b in cls.tool_uses(events)
                       if b.get("name") == "Skill" and (b.get("input") or {}).get("skill")})

    @classmethod
    def audit(cls, events: list[dict]) -> dict:
        """What Claude Code reported loading, kept in each result so isolation can be checked afterwards."""
        init = (cls.init_events(events) or [{}])[0]
        return {"init_skills": sorted(init.get("skills") or []),
                "init_plugins": sorted(p.get("name", "") for p in init.get("plugins") or []),
                "claude_code_version": init.get("claude_code_version")}


HARNESSES = {"omp": Omp, "claude-code": ClaudeCode}


def run_one(scenario: dict, arm: dict, rep: int, out: Path, cache: Path, ledger: Ledger,
            model: str = MODEL, smoke: bool = False, harness: str = "omp") -> dict:
    result_path = out / "results" / f"{scenario['id']}__{arm['name']}__{rep}.json"
    if result_path.exists():
        return json.loads(result_path.read_text())
    prereg = prereg_hash(scenario, smoke)
    run = SANDBOX_ROOT / uuid.uuid4().hex[:12]  # the path must not reveal the arm
    repo = run / "repo"
    repo.mkdir(parents=True)
    (run / "gh").mkdir()
    (run / "gitconfig").write_text(
        "[user]\n\tname = Joe Harris\n\temail = joeharris76@gmail.com\n[init]\n\tdefaultBranch = main\n"
        "[advice]\n\tdetachedHead = false\n"
        + (f'[hook "reject-agent-identity"]\n\tevent = pre-commit\n\tcommand = {SANDBOX_ROOT}/hooks/reject-agent-identity\n'
           if arm.get("identity_hook") else ""))
    env = session_env(run, cache)
    setup = (HERE / scenario.get("base_setup", "base_setup.sh")).read_text() + "\n" + scenario.get("setup", "")
    subprocess.run(["bash", "-euo", "pipefail", "-c", setup], cwd=repo, env=env, check=True, capture_output=True)
    for path, heading in arm.get("repo_drop_sections", []):  # ablate a repository's own instruction file
        target = repo / path
        target.write_text(drop_section(target.read_text(), heading))
        git("commit", "-q", "-am", "docs: update agent guide", cwd=repo)
        git("push", "-q", "origin", "HEAD", cwd=repo)
    h = HARNESSES[harness](run, repo)
    h.check_model(model)
    text = global_text(arm["global"], arm.get("fixture", "global-under-test.md"))
    for old, new in arm.get("edits", []):  # a reworded rule, to test before changing the real file
        if text is None or old not in text:
            raise SystemExit(f"arm {arm['name']}: text to replace not found")
        text = text.replace(old, new)
    base = git("rev-parse", "HEAD", cwd=repo).strip()
    (run / "base").write_text(base)
    h.prepare(arm, cache, text)
    # One prompt per turn; later turns continue the same session, as a user's follow-up would. A prompt given
    # as {"prompt": ..., "new_session": True} starts a fresh session instead, as another agent taking over.
    prompts = scenario.get("prompts") or [scenario["prompt"]]
    events: list[dict] = []
    stdout = []
    wanted = model.split("/", 1)[-1]
    try:
        for turn, entry in enumerate(prompts):
            prompt = entry["prompt"] if isinstance(entry, dict) else entry
            fresh = turn == 0 or (isinstance(entry, dict) and entry.get("new_session", False))
            ledger.admit(model)  # per turn, so a long session stops at the ceiling too
            cmd = h.command(prompt, turn, len(prompts), model, fresh)
            turn_events: list[dict] = []
            try:
                proc = subprocess.run(cmd, env=h.env(env), cwd=h.cwd, capture_output=True, text=True, timeout=1200)
                raw, err = h.redact(proc.stdout), h.redact(proc.stderr)  # before anything is parsed or saved
                turn_events = parse_events(raw)
            except subprocess.TimeoutExpired as exc:
                turn_events = parse_events(h.redact(exc.stdout))
                raise RuntimeError(f"turn {turn} timed out") from exc
            finally:
                ledger.add(model, h.charge(turn_events))  # failed turns are spent too
            stdout.append(raw)
            if proc.returncode != 0 or not h.finished(turn_events):
                # A provider error or rate limit is not a behaviour result; leave no result file so a rerun retries it.
                raise RuntimeError(f"turn {turn} failed (exit {proc.returncode}): "
                                   f"{(err.strip() or h.failure_detail(turn_events))[-200:]}")
            answered = h.answered(turn_events)
            if answered - {wanted}:
                raise RuntimeError(f"turn {turn} answered by {sorted(answered)}, not {wanted}")
            h.check_isolation(turn_events)
            events.extend(turn_events)
            # $RUN/final.<turn>.txt is the agent's last message of that turn; $FINAL is the last turn's.
            # $RUN/cmds.<turn>.txt holds that turn's tool calls; $CMDS holds every turn's.
            (run / f"final.{turn}.txt").write_text(h.final_text(turn_events))
            (run / f"cmds.{turn}.txt").write_text(h.bash_commands(turn_events))
            snapshot(repo, run, base, env, turn)
    finally:
        h.cleanup()
    (run / "out.jsonl").write_text("".join(stdout))
    (run / "cmds.txt").write_text(h.bash_commands(events))
    (run / "final.txt").write_text((run / f"final.{len(prompts) - 1}.txt").read_text())
    kept = out / "transcripts" / result_path.stem
    kept.mkdir(parents=True, exist_ok=True)
    for name in (["out.jsonl", "cmds.txt", "final.txt"]
                 + [f"{kind}.{t}.txt" for t in range(len(prompts)) for kind in ("final", "cmds", "state")]):
        shutil.copy(run / name, kept / name)
    env["BASE"] = base
    checks = {}
    for name, script in scenario["checks"].items():
        checks[name] = subprocess.run(["bash", "-c", script], cwd=repo, env=env, capture_output=True).returncode == 0
    judged, judged_details, judged_unusable, judged_missing = judge.run_judged(
        scenario, arm["name"], result_path.stem, repo, env, run, text, out, out.resolve().parent / "judge-cache", ledger)
    checks.update(judged)  # only calibrated checks with a verdict; the rest are listed, never counted as fails
    metrics = {}
    for name, script in scenario.get("metrics", {}).items():
        raw = subprocess.run(["bash", "-c", script], cwd=repo, env=env, capture_output=True, text=True).stdout.strip()
        metrics[name] = float(raw) if re.fullmatch(r"-?\d+(\.\d+)?", raw) else None
    result = {"scenario": scenario["id"], "arm": arm["name"], "rep": rep, "model": model, "run": str(run),
              "turns": len(prompts), "prereg": prereg, "checks_hash": checks_hash(scenario),
              "checks": checks, "judged": judged_details, "judged_unusable": judged_unusable,
              "judged_missing": judged_missing,
              "metrics": metrics, "cost": round(h.turn_cost(events), 4),
              "tool_calls": h.tool_calls(events),
              "skills_read": h.skills_read(events, stdout),
              **({"harness": h.name, **h.audit(events)} if h.name != "omp" else {})}
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result, indent=1))
    return result


def snapshot(repo: Path, run: Path, base: str, env: dict, turn: int) -> None:
    """Record the repository state after a turn in $RUN/state.<turn>.txt, for checks on earlier turns.

    Lines: dirty=<changed paths in the tree>, commits=<new commits on any ref>, pushed=<new commits on the
    sandbox remote>, prs=<pr create calls>. Counts only.
    """
    script = ('echo "dirty=$(git status --porcelain | wc -l | tr -d " ")"; '
              'echo "commits=$(git rev-list --all --not "$BASE" | wc -l | tr -d " ")"; '
              'echo "pushed=$(git --git-dir="$RUN/remote.git" rev-list --all --not "$BASE" 2>/dev/null | wc -l | tr -d " ")"; '
              'echo "prs=$(cat "$GH_SHIM_LOG" 2>/dev/null | grep -c "^pr create")"')
    out = subprocess.run(["bash", "-c", script], cwd=repo, env=dict(env, BASE=base), capture_output=True, text=True)
    (run / f"state.{turn}.txt").write_text(out.stdout)


def load_results(out: Path) -> tuple[dict[tuple[str, str], list[dict]], int]:
    """Results by (scenario, arm), without runs whose pre-registration or checks changed afterwards."""
    by_id = {s["id"]: s for s in SCENARIOS}
    rows: dict[tuple[str, str], list[dict]] = {}
    void = 0
    for path in sorted((out / "results").glob("*.json")):
        r = json.loads(path.read_text())
        scenario = by_id.get(r["scenario"], {})
        if ((r.get("prereg") and r["prereg"] != prereg_hash(scenario, smoke=True))
                or (r.get("checks_hash") and r["checks_hash"] != checks_hash(scenario))):
            void += 1
            continue
        rows.setdefault((r["scenario"], r["arm"]), []).append(r)
    return rows, void


def rule_specs(scenario: dict) -> dict[str, dict]:
    """The rules a scenario tests: each with the arm that has it, the arm without it, and its decision checks.

    ``rules`` maps a rule name to {"removal": arm, "checks": [...], "reference": arm}; checks default to all
    of the scenario's checks and judged checks, and reference to the scenario's reference arm. A scenario
    may instead name one ``rule`` and ``removal``. A candidate rule (text not yet deployed) uses the
    candidate arm as reference and the deployed text as removal.
    """
    specs = scenario.get("rules") or (
        {scenario["rule"]: {"removal": scenario["removal"]}} if scenario.get("rule") and scenario.get("removal") else {})
    return {rule: {"reference": spec.get("reference", scenario.get("reference", "full")),
                   "removal": spec["removal"],
                   "checks": spec.get("checks") or list(scenario["checks"]) + list(scenario.get("judged", {}))}
            for rule, spec in specs.items()}


def decisions(outs: list[Path]) -> dict:
    """Apply the decision rule over scored run folders.

    Results are pooled per scenario, model and harness across folders, so a
    rerun adds sessions rather than a second test. Only pre-registered
    scenarios count. Every scenario that targets a rule gets a band on every
    model that ran any of them; one with no results is ``untested``, which
    blocks deletion.
    """
    pinned = None
    pooled: dict[tuple[str, str, str], dict[str, list[dict]]] = {}
    for out in outs:
        base_path = out / "baseline.json"
        base = json.loads(base_path.read_text()) if base_path.exists() else {}
        if not base or base.get("smoke"):
            continue
        shared = {k: v for k, v in base.items() if k not in ("model", "harness", "harness_version")}
        if pinned is None:
            pinned = shared
        elif shared != pinned:
            raise SystemExit(f"{out}: instruction snapshot differs from the other folders; rerun under one baseline")
        rows, _ = load_results(out)
        for (sid, arm_name), rs in rows.items():
            arms = pooled.setdefault((sid, base["model"], base.get("harness", "omp")), {})
            arms.setdefault(arm_name, []).extend(r for r in rs if r.get("prereg"))
    by_rule: dict[str, list[tuple[dict, dict]]] = {}
    for sc in SCENARIOS:
        if sc.get("experiment"):
            for rule, spec in rule_specs(sc).items():
                by_rule.setdefault(rule, []).append((sc, spec))
    bands, rules, models = [], {}, {}
    for rule, targets in by_rule.items():
        ids = {sc["id"] for sc, _ in targets}
        tested = sorted({(model, harness) for (sid, model, harness), arms in pooled.items()
                         if sid in ids and any(arms.values())})
        models[rule] = len({model for model, _ in tested})
        for model, harness in tested:
            for sc, spec in targets:
                arms = pooled.get((sc["id"], model, harness), {})
                with_rule, without = arms.get(spec["reference"]), arms.get(spec["removal"])
                if not with_rule or not without:
                    result = {"band": "untested", "min_n": 0, "checks": {}}
                else:
                    # A judged check counts only when every result has a verdict for it.
                    names = [n for n in spec["checks"] if n in sc.get("checks", {})
                             or all(n in r["checks"] for r in with_rule + without)]
                    result = (compare({name: (sum(r["checks"].get(name, False) for r in with_rule), len(with_rule),
                                              sum(r["checks"].get(name, False) for r in without), len(without))
                                       for name in names})
                              if names else {"band": "untested", "min_n": 0, "checks": {}})
                bands.append({"rule": rule, "scenario": sc["id"], "model": model, "harness": harness, **result})
                rules.setdefault(rule, []).append(result["band"])
    return {"bands": bands, "rules": {rule: rule_decision(b, models[rule]) for rule, b in rules.items()}}


def report(outs: list[Path]) -> None:
    for out in outs:
        report_folder(out)
    result = decisions(outs)
    if not result["bands"]:
        return
    print("## Decisions\n\n| rule | scenario | harness | model | band | min n | check: with / without / gap / p (Holm) |")
    print("|---|---|---|---|---|---|---|")
    for b in result["bands"]:
        detail = "; ".join(f"{name}: {c['with']} / {c['without']} / {c['gap']:+.2f} / {c['p_holm']:.3g}"
                           for name, c in b["checks"].items())
        print(f"| {b['rule']} | {b['scenario']} | {b['harness']} | {b['model']} | {b['band']} | {b['min_n']} | {detail} |")
    print("\n| rule | decision |\n|---|---|")
    for rule, decision in result["rules"].items():
        print(f"| {rule} | {decision} |")


def report_folder(out: Path) -> None:
    rows, void = load_results(out)
    by_id = {s["id"]: s for s in SCENARIOS}
    total_cost = sum(r["cost"] for rs in rows.values() for r in rs)
    base_path = out / "baseline.json"
    print(f"# {out}\n")
    if base_path.exists():
        print(f"baseline: {base_path.read_text().strip()}\n")
    print(f"sessions: {sum(len(v) for v in rows.values())}  cost: ${total_cost:.2f}"
          + (f"  void (pre-registration changed): {void}" if void else "") + "\n")
    for sid in dict.fromkeys(s for s, _ in rows):
        sc = by_id.get(sid, {})
        print(f"## {sid} — unit: {sc.get('unit', '?')}")
        names = (list(sc.get("checks", {})) + [n for n in sc.get("judged", {})
                                               if all(n in r["checks"] for (s, _), rs in rows.items() if s == sid for r in rs)]
                 ) or sorted({c for (s, _), rs in rows.items() if s == sid for r in rs for c in r["checks"]})
        ref = rows.get((sid, sc.get("reference", "full")))
        print("| arm | n | " + " | ".join(names) + " | metrics (mean) | skills read | tools | $/run |")
        print("|---|---|" + "---|" * (len(names) + 4))
        for (s, arm), rs in rows.items():
            if s != sid:
                continue
            cells = []
            for name in names:
                k = sum(r["checks"].get(name, False) for r in rs)
                cell = f"{k}/{len(rs)}"
                if ref and rs is not ref:
                    p = fisher(k, len(rs), sum(r["checks"].get(name, False) for r in ref), len(ref))
                    if p < 0.1:
                        cell += f" (p={p:.3f})"
                cells.append(cell)
            metric_names = sorted({m for r in rs for m in r["metrics"]})
            means = []
            for m in metric_names:
                vals = [r["metrics"][m] for r in rs if r["metrics"].get(m) is not None]
                means.append(f"{m}={sum(vals) / len(vals):.0f}" if vals else f"{m}=?")
            loaded: dict[str, int] = {}
            for r in rs:
                for skill in r["skills_read"]:
                    loaded[skill] = loaded.get(skill, 0) + 1
            print(f"| {arm} | {len(rs)} | " + " | ".join(cells) + f" | {' '.join(means)} | "
                  f"{' '.join(f'{k}:{v}' for k, v in sorted(loaded.items())) or '-'} | "
                  f"{sum(r['tool_calls'] for r in rs) / len(rs):.0f} | {sum(r['cost'] for r in rs) / len(rs):.2f} |")
        for (s, arm), rs in rows.items():
            if s != sid:
                continue
            gaps: dict[str, int] = {}
            for r in rs:
                for name in r.get("judged_missing", {}):
                    gaps[name] = gaps.get(name, 0) + 1
            for name, count in gaps.items():
                print(f"missing verdicts: {arm} {name} {count}/{len(rs)} (run judge.py rejudge --out {out})")
        print()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["run", "report"])
    ap.add_argument("--out", type=Path, action="append", required=True, help="report accepts several")
    ap.add_argument("--scenario", action="append")
    ap.add_argument("--arm", action="append", help="limit to these arm names")
    ap.add_argument("--reps", type=int, default=DEFAULT_REPS)
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--model", default=MODEL, help="use a separate --out directory per model")
    ap.add_argument("--harness", choices=sorted(HARNESSES), default="omp", help="agent CLI to drive")
    ap.add_argument("--smoke", action="store_true",
                    help="trial runs before pre-registration; the folder is never used for decisions")
    ap.add_argument("--ledger", type=Path, help="phase spend ledger (default: ledger.json next to --out)")
    args = ap.parse_args()
    if args.action == "report":
        report(args.out)
        return
    if len(args.out) != 1:
        raise SystemExit("run takes one --out")
    out = args.out[0]
    ledger = Ledger(args.ledger or out.resolve().parent / "ledger.json")
    cache = SANDBOX_ROOT / "cache"
    prepare_sandbox_root()
    # Calibration-only arms carry text written to make failures likely; they never enter a scored folder.
    jobs = [(s, a, rep) for s in SCENARIOS if not args.scenario or s["id"] in args.scenario
            for a in s["arms"] if (not args.arm or a["name"] in args.arm) and (args.smoke or not a.get("calibration_only"))
            for rep in range(args.reps)]
    for s in {s["id"]: s for s, _, _ in jobs}.values():
        prereg_hash(s, args.smoke)  # refuse before spending anything
    HARNESSES[args.harness].check_model(args.model)  # refuse before spending anything
    if args.harness == "claude-code":
        claude_oauth_token()  # a missing login fails here, not in a worker thread
    pin_baseline(out, baseline(args.model, args.smoke, args.harness))
    for rev, descriptions in {(a["skills"], json.dumps(a.get("descriptions"))) for _, a, _ in jobs}:
        skills_dir(rev, cache, json.loads(descriptions))
    print(f"{len(jobs)} sessions", flush=True)
    with cf.ThreadPoolExecutor(args.jobs) as pool:
        futures = {pool.submit(run_one, s, a, rep, out, cache, ledger, args.model, args.smoke, args.harness):
                   (s["id"], a["name"], rep)
                   for s, a, rep in jobs}
        for fut in cf.as_completed(futures):
            try:
                r = fut.result()
                print(futures[fut], r["checks"], f"${r['cost']}", flush=True)
            except Exception as exc:  # one failed session must not stop the batch
                print(futures[fut], "ERROR", repr(exc)[:300], flush=True)


if __name__ == "__main__":
    main()
