"""Ablation runner: the same task, with and without one unit of instruction text.

Each session is a headless ``omp`` run in a throwaway repository. An arm fixes
which global instruction text and which skills revision the agent sees; nothing
else differs. Checks are shell commands run against the sandbox afterwards.

Usage:
    run.py run --out DIR [--scenario ID ...] [--reps 5] [--jobs 6]
    run.py report --out DIR
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
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
DISABLED_PROVIDERS = ["agents", "claude", "codex", "gemini", "opencode", "github",
                      "claude-plugins", "omp-plugins", "agent-plugins", "cursor", "windsurf", "cline"]

sys.path.insert(0, str(HERE))
from scenarios import SCENARIOS  # noqa: E402


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


def global_text(spec: str) -> str | None:
    """Arm text for the global file: full | none | old | minus:<heading> | only:<heading> | lines:<ranges>."""
    if spec == "none":
        return None
    if spec == "old":
        return (HERE / "fixtures" / "global-before-cleanup.md").read_text()
    # A snapshot, not the live file: line-range arms and past results stay valid when the file changes.
    full = (HERE / "fixtures" / "global-under-test.md").read_text()
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


def skills_dir(rev: str, cache: Path) -> Path:
    """Export the catalog's skills at one revision, once."""
    dest = cache / "skills" / rev
    if not dest.exists():
        dest.mkdir(parents=True)
        archive = subprocess.run(["git", "archive", rev, "skills"], cwd=CATALOG, check=True, capture_output=True)
        subprocess.run(["tar", "-x", "-C", str(dest)], input=archive.stdout, check=True)
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
    hidden = ["Developer", ".agents", ".claude", ".codex", ".gemini", ".tractable", ".skill-sync-deployment",
              "Documents", "Desktop"]
    (SANDBOX_ROOT / "deny.sb").write_text(
        "(version 1)\n(allow default)\n(deny file-read* file-write*\n"
        + "".join(f'  (subpath "{home / name}")\n' for name in hidden) + ")\n")


def run_one(scenario: dict, arm: dict, rep: int, out: Path, cache: Path, model: str = MODEL) -> dict:
    result_path = out / "results" / f"{scenario['id']}__{arm['name']}__{rep}.json"
    if result_path.exists():
        return json.loads(result_path.read_text())
    run = SANDBOX_ROOT / uuid.uuid4().hex[:12]  # the path must not reveal the arm
    repo = run / "repo"
    repo.mkdir(parents=True)
    (run / "gh").mkdir()
    (run / "gitconfig").write_text(
        "[user]\n\tname = Joe Harris\n\temail = joeharris76@gmail.com\n[init]\n\tdefaultBranch = main\n"
        "[advice]\n\tdetachedHead = false\n"
        + (f'[hook "reject-agent-identity"]\n\tevent = pre-commit\n\tcommand = {SANDBOX_ROOT}/hooks/reject-agent-identity\n'
           if arm.get("identity_hook") else ""))
    env = dict(os.environ, RUN=str(run), GIT_CONFIG_GLOBAL=str(run / "gitconfig"), GIT_CONFIG_NOSYSTEM="1",
               PATH=f"{SANDBOX_ROOT / 'shims'}:{os.environ['PATH']}", GH_SHIM_LOG=str(run / "gh.log"),
               GH_CANNED=str(run / "gh"), GH_TOKEN="sandbox", GH_CONFIG_DIR=str(run / "ghcfg"),
               CMDS=str(run / "cmds.txt"), FINAL=str(run / "final.txt"), HARNESS=str(HERE), CACHE=str(cache))
    setup = (HERE / scenario.get("base_setup", "base_setup.sh")).read_text() + "\n" + scenario.get("setup", "")
    subprocess.run(["bash", "-euo", "pipefail", "-c", setup], cwd=repo, env=env, check=True, capture_output=True)
    for path, heading in arm.get("repo_drop_sections", []):  # ablate a repository's own instruction file
        target = repo / path
        target.write_text(drop_section(target.read_text(), heading))
        git("commit", "-q", "-am", "docs: update agent guide", cwd=repo)
        git("push", "-q", "origin", "HEAD", cwd=repo)
    text = global_text(arm["global"])
    for old, new in arm.get("edits", []):  # a reworded rule, to test before changing the real file
        if text is None or old not in text:
            raise SystemExit(f"arm {arm['name']}: text to replace not found")
        text = text.replace(old, new)
    if text is not None:
        (repo / "GLOBAL.md").write_text(text)
        with (repo / ".git" / "info" / "exclude").open("a") as fh:
            fh.write("GLOBAL.md\n")
    base = git("rev-parse", "HEAD", cwd=repo).strip()
    (run / "base").write_text(base)
    overlay = run / "overlay.yml"
    overlay.write_text(
        "contextFiles:\n  extra:\n    - GLOBAL.md\ndisabledProviders:\n"
        + "".join(f"  - {p}\n" for p in DISABLED_PROVIDERS)
        + f"skills:\n  customDirectories:\n    - {skills_dir(arm['skills'], cache)}\n")
    cmd = ["sandbox-exec", "-f", str(SANDBOX_ROOT / "deny.sb"),
           "omp", "-p", "--mode", "json", "--model", model, "--config", str(overlay), "--cwd", str(repo),
           "--no-session", "--no-title", "--auto-approve", "--max-time", "900", "--max-cost", "3", scenario["prompt"]]
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=1200)
    (run / "out.jsonl").write_text(proc.stdout)
    events = [json.loads(line) for line in proc.stdout.splitlines() if line.startswith("{")]
    (run / "cmds.txt").write_text(bash_commands(events))
    (run / "final.txt").write_text(final_text(events))
    kept = out / "transcripts" / result_path.stem
    kept.mkdir(parents=True, exist_ok=True)
    for name in ("out.jsonl", "cmds.txt", "final.txt"):
        shutil.copy(run / name, kept / name)
    env["BASE"] = base
    checks = {}
    for name, script in scenario["checks"].items():
        checks[name] = subprocess.run(["bash", "-c", script], cwd=repo, env=env, capture_output=True).returncode == 0
    metrics = {}
    for name, script in scenario.get("metrics", {}).items():
        raw = subprocess.run(["bash", "-c", script], cwd=repo, env=env, capture_output=True, text=True).stdout.strip()
        metrics[name] = float(raw) if re.fullmatch(r"-?\d+(\.\d+)?", raw) else None
    cost = sum(((ev.get("message") or {}).get("usage") or {}).get("cost", {}).get("total", 0)
               for ev in events if ev.get("type") == "message_end")
    result = {"scenario": scenario["id"], "arm": arm["name"], "rep": rep, "model": model, "run": str(run),
              "exit": proc.returncode,
              "checks": checks, "metrics": metrics, "cost": round(cost, 4),
              "tool_calls": sum(ev.get("type") == "tool_execution_start" for ev in events),
              "skills_read": sorted(set(re.findall(r"skill://([\w-]+)", proc.stdout)))}
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result, indent=1))
    return result


def fisher(a_pass: int, a_n: int, b_pass: int, b_n: int) -> float:
    """Two-sided Fisher exact p-value for two pass counts."""
    from math import comb
    total_pass, total = a_pass + b_pass, a_n + b_n
    def prob(k: int) -> float:
        return comb(a_n, k) * comb(b_n, total_pass - k) / comb(total, total_pass)
    observed = prob(a_pass)
    lo, hi = max(0, total_pass - b_n), min(a_n, total_pass)
    return min(1.0, sum(prob(k) for k in range(lo, hi + 1) if prob(k) <= observed + 1e-12))


def report(out: Path) -> None:
    rows: dict[tuple[str, str], list[dict]] = {}
    for path in sorted((out / "results").glob("*.json")):
        r = json.loads(path.read_text())
        rows.setdefault((r["scenario"], r["arm"]), []).append(r)
    by_id = {s["id"]: s for s in SCENARIOS}
    total_cost = sum(r["cost"] for rs in rows.values() for r in rs)
    print(f"sessions: {sum(len(v) for v in rows.values())}  cost: ${total_cost:.2f}\n")
    for sid in dict.fromkeys(s for s, _ in rows):
        sc = by_id.get(sid, {})
        print(f"## {sid} — unit: {sc.get('unit', '?')}")
        names = list(sc.get("checks", {})) or sorted({c for (s, _), rs in rows.items() if s == sid for r in rs for c in r["checks"]})
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
        print()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["run", "report"])
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--scenario", action="append")
    ap.add_argument("--arm", action="append", help="limit to these arm names")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--model", default=MODEL, help="use a separate --out directory per model")
    args = ap.parse_args()
    if args.action == "report":
        report(args.out)
        return
    cache = SANDBOX_ROOT / "cache"
    prepare_sandbox_root()
    jobs = [(s, a, rep) for s in SCENARIOS if not args.scenario or s["id"] in args.scenario
            for a in s["arms"] if not args.arm or a["name"] in args.arm for rep in range(args.reps)]
    for rev in {a["skills"] for _, a, _ in jobs}:
        skills_dir(rev, cache)
    print(f"{len(jobs)} sessions", flush=True)
    with cf.ThreadPoolExecutor(args.jobs) as pool:
        futures = {pool.submit(run_one, s, a, rep, args.out, cache, args.model): (s["id"], a["name"], rep)
                   for s, a, rep in jobs}
        for fut in cf.as_completed(futures):
            try:
                r = fut.result()
                print(futures[fut], r["checks"], f"${r['cost']}", flush=True)
            except Exception as exc:  # one failed session must not stop the batch
                print(futures[fut], "ERROR", repr(exc)[:300], flush=True)


if __name__ == "__main__":
    main()
