"""Loading-map probe: which instruction sources reach the model, per harness and role.

Each session plants a unique marker string in every instruction source, then asks
the main model (and the subagents it spawns) to quote any marker present in its
instructions or system context without using tools to look for files. A source
"reaches" a role when the exact marker is quoted back.

Usage (from the catalog root):

    uv run --no-project python evals/ablation/loading-map/probe.py run --out /tmp/loading-map-probe/out [--reps 3] [--config omp-isolated|omp-claude-provider|omp-all-providers|omp-user-file|claude-code]
    uv run --no-project python evals/ablation/loading-map/probe.py report --out /tmp/loading-map-probe/out
    uv run --no-project python evals/ablation/loading-map/probe.py shadow --out /tmp/loading-map-probe/shadow

Configurations:

- omp-isolated: the ablation runner's setup (all discovery providers off; the global
  file via contextFiles.extra; the skill via skills.customDirectories). Repository
  AGENTS.md loads through omp's built-in provider; CLAUDE.md does not load.
- omp-claude-provider: the same, with the "claude" discovery provider enabled, so
  repository CLAUDE.md and .claude/skills load as they do for a user who has not
  disabled it. (The sandbox profile still hides the user's own ~/.claude.)
- omp-all-providers: no provider disabled (what an unconfigured omp does); only the user's home
  directories are hidden by the sandbox profile.
- omp-user-file: like omp-all-providers, but the global marker sits in a stand-in home's
  ~/.agents/AGENTS.md (found by discovery, as the deployed file is) instead of contextFiles.extra.
- claude-code: `claude -p --setting-sources project --strict-mcp-config`, the global
  file via --append-system-prompt-file.

Sessions run in a throwaway git repository under /tmp with no remote, inside
`sandbox-exec` so the user's real instruction files and skills cannot be read.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path("/tmp/loading-map-probe")
MODEL_OMP = "anthropic/claude-sonnet-5-5"
MODEL_CC = "sonnet"
DISABLED = ["agents", "claude", "codex", "gemini", "opencode", "github",
            "claude-plugins", "omp-plugins", "agent-plugins", "cursor", "windsurf", "cline"]
CONFIGS = ["omp-isolated", "omp-claude-provider", "omp-all-providers", "omp-user-file", "claude-code"]

# Marker per source. The brief markers are written by the parent into the subagent's task text.
MARKERS = {
    "global": "MARK-GLOBAL-7Q2",
    "repo-agents": "MARK-REPOAGENTS-4K8",
    "repo-claude": "MARK-REPOCLAUDE-2M5",
    "repo-dot-claude": "MARK-DOTCLAUDE-5H6",
    "skill-description": "MARK-SKILLDESC-9X3",
    "skill-body": "MARK-SKILLBODY-6T1",
    "brief": "MARK-BRIEFTASK-7R4",  # reviewer brief uses MARK-BRIEFREV-3W9
    "control": "MARK-CONTROL-0Z0",
}
BRIEF_REVIEW = "MARK-BRIEFREV-3W9"
ALL_MARKERS = list(MARKERS.values()) + [BRIEF_REVIEW]
SOURCES = ["global", "repo-agents", "repo-claude", "repo-dot-claude", "skill-description", "skill-body", "brief", "control"]
ROLES = ["main", "task", "reviewer"]
PATTERN = re.compile(r"MARK-[A-Z]+-[0-9A-Z]{3}")

QUOTE_RULE = ("Do not use any tool to look for or read files, run commands, or load skills. Answer only from the "
              "text already in front of you: your system prompt, project or user instructions, any listed skills, "
              "and the message that assigned you this work. Quote verbatim every string that begins with the "
              "four capital letters M, A, R, K followed by a hyphen, an uppercase word, a hyphen and three more "
              "characters. Quote each one exactly as written. If there are none, write NONE.")


def prompt(harness: str) -> str:
    tool = "`task` tool" if harness.startswith("omp") else "Agent tool"
    task_agent = "agent `task`" if harness.startswith("omp") else "subagent type general-purpose"
    review_agent = "agent `reviewer`" if harness.startswith("omp") else "subagent type general-purpose"
    return (
        "This is an instruction-loading probe. " + QUOTE_RULE + "\n\n"
        "Part 1. Write the heading MAIN: and then your own list of such strings (one per line).\n\n"
        f"Part 2. Use the {tool} to spawn one subagent ({task_agent}) whose task text is exactly: "
        f"\"Marker probe. {MARKERS['brief']} is the label of this brief. {QUOTE_RULE} Reply with only the list.\"\n\n"
        f"Part 3. Use the {tool} to spawn one subagent ({review_agent}) whose task text is exactly: "
        f"\"Review probe: you are reviewing nothing; just answer this. {BRIEF_REVIEW} is the label of this brief. "
        f"{QUOTE_RULE} Reply with only the list.\"\n\n"
        "Spawn the subagents one at a time, with no tools given to them beyond what they already have, and do "
        "not do any other work. Part 4. Finish with the headings TASK: and REVIEWER: followed by each "
        "subagent's reply copied verbatim.")


def make_sandbox(config: str) -> tuple[Path, Path, dict]:
    run = ROOT / "runs" / uuid.uuid4().hex[:12]
    repo = run / "repo"
    repo.mkdir(parents=True)
    ctl = ROOT / "control"
    ctl.mkdir(parents=True, exist_ok=True)
    (ctl / "CONTROL.md").write_text(f"This file is never loaded by any harness. {MARKERS['control']}\n")
    (run / "gitconfig").write_text("[user]\n\tname = probe\n\temail = probe@example.invalid\n[init]\n\tdefaultBranch = main\n")
    env = dict(os.environ, GIT_CONFIG_GLOBAL=str(run / "gitconfig"), GIT_CONFIG_NOSYSTEM="1")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, env=env, check=True)
    (repo / "README.md").write_text("# probe\n")
    (repo / "AGENTS.md").write_text(f"# Repository guide\n\nProject rule. {MARKERS['repo-agents']}\n")
    (repo / "CLAUDE.md").write_text(f"# Claude guide\n\nProject rule. {MARKERS['repo-claude']}\n")
    (repo / ".claude").mkdir(exist_ok=True)
    (repo / ".claude" / "CLAUDE.md").write_text(f"# Dot-claude guide\n\nProject rule. {MARKERS['repo-dot-claude']}\n")
    skill = (f"---\nname: probe-skill\ndescription: Use when asked about probe widgets. {MARKERS['skill-description']}\n---\n\n"
             f"# Probe skill\n\nBody text. {MARKERS['skill-body']}\n")
    if config == "claude-code":
        (repo / ".claude" / "skills" / "probe-skill").mkdir(parents=True)
        (repo / ".claude" / "skills" / "probe-skill" / "SKILL.md").write_text(skill)
    else:
        (run / "skills" / "probe-skill").mkdir(parents=True)
        (run / "skills" / "probe-skill" / "SKILL.md").write_text(skill)
    (run / "GLOBAL.md").write_text(f"# Global instructions\n\nGlobal rule. {MARKERS['global']}\n")
    subprocess.run("git add -A && git commit -q -m init", shell=True, cwd=repo, env=env, check=True)
    home = Path.home()
    hidden = ["Developer", ".agents", ".codex", ".gemini", ".tractable", ".skill-sync-deployment", "Documents", "Desktop"]
    rules = "".join(f'  (subpath "{home / n}")\n' for n in hidden)
    if config == "claude-code":  # Claude Code needs ~/.claude for credentials; hide only its instruction sources
        rules += f'  (literal "{home / ".claude" / "CLAUDE.md"}")\n'
        rules += "".join(f'  (subpath "{home / ".claude" / n}")\n' for n in ["skills", "rules", "agents", "plugins", "projects"])
    else:
        rules += f'  (subpath "{home / ".claude"}")\n'
    (run / "deny.sb").write_text("(version 1)\n(allow default)\n(deny file-read* file-write*\n" + rules + ")\n")
    return run, repo, env


def run_session(config: str, rep: int, out: Path) -> dict:
    path = out / f"{config}__{rep}.json"
    if path.exists():
        return json.loads(path.read_text())
    run, repo, env = make_sandbox(config)
    prefix = ["sandbox-exec", "-f", str(run / "deny.sb")]
    if config == "claude-code":
        cmd = prefix + ["claude", "-p", "--model", MODEL_CC, "--setting-sources", "project", "--strict-mcp-config",
                        "--append-system-prompt-file", str(run / "GLOBAL.md"), "--tools", "Agent,Skill",
                        "--output-format", "stream-json", "--verbose", "--max-budget-usd", "1", prompt(config)]
    else:
        disabled = {"omp-isolated": DISABLED, "omp-user-file": [],
                    "omp-claude-provider": [p for p in DISABLED if p != "claude"],
                    "omp-all-providers": []}[config]
        shutil.copy(run / "GLOBAL.md", repo / "GLOBAL.md")  # extra files resolve relative to the cwd, as in run.py
        with (repo / ".git" / "info" / "exclude").open("a") as fh:
            fh.write("GLOBAL.md\n")
        if config == "omp-user-file":
            # The deployed global file is ~/.agents/AGENTS.md, found by discovery rather than listed in
            # contextFiles.extra. Use a stand-in home with the marker there and the real ~/.omp for credentials.
            home = run / "home"
            (home / ".agents").mkdir(parents=True)
            shutil.copy(run / "GLOBAL.md", home / ".agents" / "AGENTS.md")
            (home / ".omp").symlink_to(Path.home() / ".omp")
            env["HOME"] = str(home)
        extra = "" if config == "omp-user-file" else "contextFiles:\n  extra:\n    - GLOBAL.md\n"
        (run / "overlay.yml").write_text(
            extra + "disabledProviders:\n"
            + ("".join(f"  - {p}\n" for p in disabled) if disabled else "  []\n")
            + f"skills:\n  customDirectories:\n    - {run / 'skills'}\n"
            + "retry:\n  fallbackChains: {}\n  usageAwareFallback: false\n")
        cmd = prefix + ["omp", "-p", "--mode", "json", "--model", MODEL_OMP, "--config", str(run / "overlay.yml"),
                        "--cwd", str(repo), "--no-session", "--no-title", "--auto-approve", "--max-time", "300",
                        "--max-cost", "1", prompt(config)]
    proc = subprocess.run(cmd, cwd=repo, env=env, capture_output=True, text=True, timeout=600)
    (out / "raw").mkdir(exist_ok=True)
    (out / "raw" / f"{config}__{rep}.jsonl").write_text(proc.stdout)
    events = [json.loads(line) for line in proc.stdout.splitlines() if line.startswith("{")]
    res = extract_omp(events) if config != "claude-code" else extract_cc(events)
    res.update(config=config, rep=rep, exit=proc.returncode, stderr=proc.stderr.strip()[-300:])
    if proc.returncode != 0 and not res["roles"]["main"]["text"]:
        raise RuntimeError(f"session failed: {res['stderr']}")
    path.write_text(json.dumps(res, indent=1))
    return res


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    return "".join(c.get("text", "") for c in content or [] if isinstance(c, dict))


def split_final(final: str) -> dict:
    """Split the main model's final answer into MAIN / TASK / REVIEWER parts (used for the main role)."""
    parts = re.split(r"^\W*(MAIN|TASK|REVIEWER)\W*:?\W*$", final, flags=re.M)
    got = {"MAIN": "", "TASK": "", "REVIEWER": ""}
    for i in range(1, len(parts) - 1, 2):
        got[parts[i]] += parts[i + 1]
    return got


def pre_text(assistant: list[dict]) -> str:
    """Text of assistant messages up to and including the first one that calls a tool."""
    out = []
    for m in assistant:
        out.append(text_of(m.get("content")))
        if any(isinstance(c, dict) and c.get("type") in ("toolCall", "tool_use") for c in m.get("content") or []):
            break
    return "\n".join(out)


def extract_omp(events: list[dict]) -> dict:
    assistant = [ev["message"] for ev in events if ev.get("type") == "message_end"
                 and (ev.get("message") or {}).get("role") == "assistant"]
    final = next((text_of(m.get("content")) for m in reversed(assistant) if text_of(m.get("content")).strip()), "")
    cost = sum((m.get("usage") or {}).get("cost", {}).get("total", 0) for m in assistant)
    # omp's task tool is asynchronous: its own result only says "Spawned". The subagent's output arrives in a
    # later `wait` (or poll) result as <task-result agent="..."><output>...</output></task-result>.
    by_agent: dict[str, str] = {}
    for ev in events:
        if ev.get("type") == "tool_execution_end":
            blob = text_of((ev.get("result") or {}).get("content"))
            for agent, body in re.findall(r'<task-result [^>]*agent="([\w-]+)"[^>]*>(.*?)</task-result>', blob, flags=re.S):
                out = re.search(r"<output>(.*?)</output>", body, flags=re.S)
                by_agent[agent] = by_agent.get(agent, "") + (out.group(1) if out else body)
    subs = [by_agent.get("task", ""), by_agent.get("reviewer", "")]
    sub_costs: dict[str, float] = {}
    sub_models: dict[str, str] = {}

    def walk(node) -> None:
        if isinstance(node, dict):
            if isinstance(node.get("id"), str) and isinstance(node.get("cost"), (int, float)):
                sub_costs[node["id"]] = max(sub_costs.get(node["id"], 0.0), float(node["cost"]))
                if node.get("resolvedModel"):
                    sub_models[node["id"]] = node["resolvedModel"]
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for ev in events:
        if ev.get("type") in ("tool_execution_update", "tool_execution_end") and ev.get("toolName") in ("task", "wait"):
            walk(ev)
    sub_cost = sum(sub_costs.values())
    tool_names = [ev.get("toolName") for ev in events if ev.get("type") == "tool_execution_start"]
    return {"final": final, "cost_main": round(cost, 4), "cost_sub_reported": round(sub_cost, 4),
            "sub_models": sub_models, "tools": tool_names, "task_results": subs, "roles": roles_from(final, subs, pre_text(assistant))}


def extract_cc(events: list[dict]) -> dict:
    final, cost, subs, tools, pre, seen_tool = "", 0.0, [], [], "", False
    for ev in events:
        if ev.get("type") == "result":
            final, cost = ev.get("result") or "", ev.get("total_cost_usd") or 0.0
        msg = ev.get("message") or {}
        for c in msg.get("content", []) if isinstance(msg.get("content"), list) else []:
            if c.get("type") == "text" and msg.get("role") == "assistant" and not seen_tool:
                pre += c.get("text", "") + "\n"
            if c.get("type") == "tool_use":
                seen_tool = True
                tools.append(c.get("name"))
            if c.get("type") == "tool_result":
                subs.append(text_of(c.get("content")))
    return {"final": final, "cost_main": round(cost, 4), "cost_sub_reported": 0.0, "tools": tools,
            "task_results": subs, "roles": roles_from(final, subs, pre)}


def roles_from(final: str, subs: list[str], pre: str) -> dict:
    """Main = assistant text written before the first subagent spawn plus the MAIN: block of the final answer.
    Subagents = the tool results, in spawn order (task, reviewer)."""
    main = pre + "\n" + split_final(final)["MAIN"]
    roles = {"main": {"text": main}, "task": {"text": subs[0] if len(subs) > 0 else ""},
             "reviewer": {"text": subs[1] if len(subs) > 1 else ""}}
    for r in roles.values():
        r["markers"] = sorted(set(PATTERN.findall(r["text"])))
    return {"roles": roles}["roles"]


def received(markers: list[str], role: str, source: str) -> bool:
    want = BRIEF_REVIEW if (source == "brief" and role == "reviewer") else MARKERS[source]
    return want in markers


def report(out: Path) -> None:
    files = sorted(out.glob("*.json"))
    by_cfg: dict[str, list[dict]] = {}
    for f in files:
        d = json.loads(f.read_text())
        raw = out / "raw" / f"{f.stem}.jsonl"
        if raw.exists():  # re-read the transcript so extractor fixes apply to saved sessions
            events = [json.loads(x) for x in raw.read_text().splitlines() if x.startswith("{")]
            d.update(extract_omp(events) if d["config"] != "claude-code" else extract_cc(events))
        by_cfg.setdefault(d["config"], []).append(d)
    total = 0.0
    for cfg in CONFIGS:
        runs = by_cfg.get(cfg, [])
        if not runs:
            continue
        print(f"\n### {cfg} ({len(runs)} sessions)\n")
        print("| source | " + " | ".join(ROLES) + " |\n|---|" + "---|" * len(ROLES))
        for src in SOURCES:
            cells = []
            for role in ROLES:
                if src == "brief" and role == "main":
                    cells.append("n/a")
                    continue
                n = sum(received(r["roles"][role]["markers"], role, src) for r in runs)
                cells.append(f"{'received' if n * 3 >= 2 * len(runs) and n >= 2 else 'not received'} {n}/{len(runs)}")
            print(f"| {src} | " + " | ".join(cells) + " |")
        cost = sum(r["cost_main"] + r["cost_sub_reported"] for r in runs)
        total += cost
        print(f"\ncost (reported in the JSON output; omp includes subagents): ${cost:.3f}")
        models = sorted({m for r in runs for m in r.get("sub_models", {}).values()})
        if models:
            print("omp subagent models:", ", ".join(models))
        stray = {m for r in runs for role in ROLES for m in r["roles"][role]["markers"] if m not in ALL_MARKERS}
        print("unexpected strings quoted:", sorted(stray) or "none")
    print(f"\ntotal cost: ${total:.3f}")


SHADOW_VARIANTS = {  # which project instruction files exist -> files written
    "agents-only": ["AGENTS.md"],
    "root-claude-only": ["CLAUDE.md"],
    "dot-claude-only": [".claude/CLAUDE.md"],
    "agents+root-claude": ["AGENTS.md", "CLAUDE.md"],
    "agents+dot-claude": ["AGENTS.md", ".claude/CLAUDE.md"],
}
SHADOW_MARK = {"AGENTS.md": "MARK-REPOAGENTS-4K8", "CLAUDE.md": "MARK-REPOCLAUDE-2M5", ".claude/CLAUDE.md": "MARK-DOTCLAUDE-5H6"}


def shadow(out: Path, reps: int) -> None:
    """Main-session only: which project instruction file omp loads when several exist (all providers enabled)."""
    out.mkdir(parents=True, exist_ok=True)
    path = out / "shadow.json"
    results = json.loads(path.read_text()) if path.exists() else {}
    for name, files in SHADOW_VARIANTS.items():
        for rep in range(len(results.get(name, [])), reps):
            run, repo, env = make_sandbox("omp-all-providers")
            for f in ("AGENTS.md", "CLAUDE.md", ".claude/CLAUDE.md", "GLOBAL.md"):
                (repo / f).unlink(missing_ok=True)
            for f in files:
                (repo / f).parent.mkdir(exist_ok=True)
                (repo / f).write_text(f"Project rule. {SHADOW_MARK[f]}\n")
            (run / "ov.yml").write_text("disabledProviders: []\n")
            cmd = ["sandbox-exec", "-f", str(run / "deny.sb"), "omp", "-p", "--mode", "json", "--model", MODEL_OMP,
                   "--config", str(run / "ov.yml"), "--cwd", str(repo), "--no-session", "--no-title", "--max-cost", "1",
                   "Without using tools, quote verbatim every string that begins with the capital letters M, A, R, K "
                   "and a hyphen in your instructions. Reply with only the list, or NONE."]
            proc = subprocess.run(cmd, cwd=repo, env=env, capture_output=True, text=True, timeout=300)
            events = [json.loads(x) for x in proc.stdout.splitlines() if x.startswith("{")]
            msgs = [e["message"] for e in events if e.get("type") == "message_end" and e["message"].get("role") == "assistant"]
            text = text_of(msgs[-1].get("content")) if msgs else ""
            cost = sum((m.get("usage") or {}).get("cost", {}).get("total", 0) for m in msgs)
            results.setdefault(name, []).append({"markers": sorted(set(PATTERN.findall(text))), "cost": cost})
            path.write_text(json.dumps(results, indent=1))
    print("\n| files present | loaded (3-session counts) |\n|---|---|")
    for name, files in SHADOW_VARIANTS.items():
        rs = results.get(name, [])
        cells = [f"{f} {sum(SHADOW_MARK[f] in r['markers'] for r in rs)}/{len(rs)}" for f in files]
        print(f"| {name} | {'; '.join(cells)} |")
    print(f"\nshadow cost: ${sum(r['cost'] for v in results.values() for r in v):.3f}")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--out", required=True)
    r.add_argument("--reps", type=int, default=3)
    r.add_argument("--config", choices=CONFIGS)
    r.add_argument("--jobs", type=int, default=3)
    sh = sub.add_parser("shadow")
    sh.add_argument("--out", required=True)
    sh.add_argument("--reps", type=int, default=3)
    p = sub.add_parser("report")
    p.add_argument("--out", required=True)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.cmd == "shadow":
        shadow(out, a.reps)
        return
    if a.cmd == "report":
        report(out)
        return
    jobs = [(c, i) for c in ([a.config] if a.config else CONFIGS) for i in range(1, a.reps + 1)]
    with ThreadPoolExecutor(a.jobs) as pool:
        futs = {pool.submit(run_session, c, i, out): (c, i) for c, i in jobs}
        for fut in as_completed(futs):
            try:
                res = fut.result()
                print(futs[fut], "ok", {k: v["markers"] for k, v in res["roles"].items()}, flush=True)
            except Exception as exc:  # noqa: BLE001
                print(futs[fut], "ERROR", repr(exc)[:300], flush=True)


if __name__ == "__main__":
    main()
