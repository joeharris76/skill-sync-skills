"""Judged checks: a rubric plus an evidence script, answered by a judge model.

Some behaviour cannot be tested with a shell command (is every claim in a
status reply true, is a handoff complete). A scenario's ``judged`` field holds
such checks:

    "judged": {"status-accuracy": {"rubric": "...", "evidence": "<shell>"}}

The evidence script runs in the sandbox like a check and prints transcript
excerpts and repository facts. The judge model, from another provider than the
agents under test, reads the rubric and that text and answers pass or fail
with a one-line reason. It never sees the arm name, the sandbox path or the
arm's instruction text.

A judged verdict enters a session's checks only when the check is calibrated:
``calibration/<check>.json`` must show agreement of at least 0.90 with labels
made from the transcripts, on at least 15 passes and 15 fails, for the current
rubric and evidence script. Otherwise the check is recorded as unusable and
left out of the result.

Usage:
    judge.py collect <check> --out DIR [--out DIR ...]   gather unlabelled evidence from run folders
    judge.py calibrate <check> [--jobs 4] [--ledger FILE]  measure agreement with the labels
    judge.py regather [<check>] --out DIR [--out DIR ...]  rebuild a folder's evidence after a script change
    judge.py rejudge --out DIR [--out DIR ...] [--ledger FILE]  fill verdicts a judge error left missing
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import inspect
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CALIBRATION = HERE / "calibration"
JUDGE_MODEL = "openai-codex/gpt-6.1-sol"
JUDGE_CWD = Path("/tmp/omp-ablation/judge")
MIN_AGREEMENT = 0.90
MIN_PER_LABEL = 15
MAX_EVIDENCE = 24000  # characters; a longer excerpt is cut in the middle
MIN_SCRUB_LINE = 12   # shorter lines of the arm's text are too generic to remove

SYSTEM = (
    "You grade one piece of evidence against a rubric. Judge only what the evidence shows. "
    "Answer with a single JSON object and nothing else: "
    '{"verdict": "pass" or "fail", "reason": "<one short sentence>"}.'
)


class JudgeError(RuntimeError):
    pass


def text_hash(*parts: str) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(part.encode())
        h.update(b"\0")
    return h.hexdigest()


def script_hash(spec: dict) -> str:
    """Hash of the evidence script and of the scrubbing applied to its output."""
    return text_hash(spec["evidence"], inspect.getsource(scrub), str(MAX_EVIDENCE), str(MIN_SCRUB_LINE))[:16]


def rubric_hash(spec: dict) -> str:
    return text_hash(spec["rubric"])[:16]


def scrub(evidence: str, *, run: str = "", arm: str = "", global_text: str | None = None) -> str:
    """Remove everything that could identify the arm from evidence text.

    The agent never sees the arm name and the harness does not print it, so
    the name can only appear as part of a result or folder name such as
    ``scenario__arm__0``; that form is removed (a bare word like "full" or
    "none" is ordinary prose and stays). The sandbox path is random per run
    but the run directory name still appears in transcripts, so it goes too,
    also in its ``/private`` form on macOS. The arm's global instruction text
    is removed line by line wherever a transcript quotes it, and so is the
    name of the file it is loaded from.
    """
    if run:
        evidence = evidence.replace("/private" + run, "<run>").replace(run, "<run>")
        evidence = evidence.replace(Path(run).name, "<run>")
    if arm:
        evidence = re.sub(rf"(?<=[_/]){re.escape(arm)}(?=[_/])", "<arm>", evidence, flags=re.I)
    evidence = evidence.replace("GLOBAL.md", "")
    seen: set[str] = set()
    for line in (global_text or "").splitlines():
        line = line.strip()
        if len(line) >= MIN_SCRUB_LINE and line not in seen:
            seen.add(line)
            evidence = evidence.replace(line, "")
    if len(evidence) > MAX_EVIDENCE:
        half = MAX_EVIDENCE // 2
        evidence = evidence[:half] + "\n[... cut ...]\n" + evidence[-half:]
    return evidence


def prompt_for(rubric: str, evidence: str) -> str:
    return f"# Rubric\n\n{rubric.strip()}\n\n# Evidence\n\n{evidence.strip()}\n"


def cache_key(rubric: str, evidence: str, model: str = JUDGE_MODEL) -> str:
    """Everything that decides a verdict: the judge, its instructions, the rubric and the evidence."""
    return text_hash(model, SYSTEM, rubric, evidence)


def parse_verdict(text: str) -> dict:
    """The first JSON object in the answer, with a pass or fail verdict."""
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            obj, _ = decoder.raw_decode(text[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and str(obj.get("verdict", "")).lower() in ("pass", "fail"):
            return {"verdict": str(obj["verdict"]).lower(), "reason": " ".join(str(obj.get("reason", "")).split())}
    raise JudgeError(f"no pass/fail JSON in judge answer: {text[:200]!r}")


def ask_judge(rubric: str, evidence: str, model: str = JUDGE_MODEL, timeout: int = 600) -> tuple[dict, float]:
    """One judge session: no tools, no instruction files, no saved session. Returns (verdict, cost)."""
    if model.startswith("anthropic/"):
        raise JudgeError("the judge must come from another provider than the agents under test")
    JUDGE_CWD.mkdir(parents=True, exist_ok=True)
    cmd = ["omp", "-p", "--mode", "json", "--model", model, "--no-session", "--no-tools", "--no-skills",
           "--no-rules", "--no-context-files", "--no-extensions", "--no-lsp", "--no-title",
           "--cwd", str(JUDGE_CWD), "--system-prompt", SYSTEM, prompt_for(rubric, evidence)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    events = []
    for line in proc.stdout.splitlines():
        if line.startswith("{"):
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    answers = [e["message"] for e in events
               if e.get("type") == "message_end" and (e.get("message") or {}).get("role") == "assistant"]
    cost = sum(((m.get("usage") or {}).get("cost") or {}).get("total", 0) for m in answers)
    if proc.returncode != 0 or not any(e.get("type") == "agent_end" for e in events) or not answers:
        raise JudgeError(f"judge session failed (exit {proc.returncode}): {proc.stderr.strip()[-200:]}")
    wanted = model.split("/", 1)[-1]
    answered = {m.get("model") for m in answers}
    if answered - {wanted}:
        raise JudgeError(f"judge session answered by {sorted(answered, key=str)}, not {wanted}")
    text = "".join(c.get("text", "") for c in answers[-1].get("content", []) if c.get("type") == "text")
    return parse_verdict(text), cost


def judge(rubric: str, evidence: str, cache_dir: Path, ledger=None, model: str = JUDGE_MODEL) -> dict:
    """Verdict for one rubric and evidence text; the same pair is never judged twice by one judge."""
    path = cache_dir / f"{cache_key(rubric, evidence, model)}.json"
    if path.exists():
        return {**json.loads(path.read_text()), "cached": True}
    verdict, cost = ask_judge(rubric, evidence, model)
    if ledger is not None:
        ledger.add(model, cost)  # other providers are counted, not capped
    verdict = {**verdict, "model": model}
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{text_hash(str(path), str(cost))[:6]}.tmp")
    tmp.write_text(json.dumps(verdict, indent=1))
    tmp.replace(path)
    return {**verdict, "cached": False}


def agreement(labels: list[str], verdicts: list[str]) -> dict:
    """Agreement between the labels and the judge's verdicts, and the counts that gate use."""
    if len(labels) != len(verdicts):
        raise ValueError("labels and verdicts differ in length")
    n = len(labels)
    same = sum(a == b for a, b in zip(labels, verdicts))
    return {"n": n, "passes": labels.count("pass"), "fails": labels.count("fail"),
            "agreement": round(same / n, 4) if n else 0.0}


def gate(stats: dict) -> tuple[bool, str]:
    """Whether a calibration result allows the check to be used, and why not."""
    problems = []
    if stats["passes"] < MIN_PER_LABEL or stats["fails"] < MIN_PER_LABEL:
        problems.append(f"needs at least {MIN_PER_LABEL} passes and {MIN_PER_LABEL} fails, "
                        f"has {stats['passes']} and {stats['fails']}")
    if stats["agreement"] < MIN_AGREEMENT:
        problems.append(f"agreement {stats['agreement']:.2f} is below {MIN_AGREEMENT:.2f}")
    return (not problems, "; ".join(problems))


def labels_hash(rows: list[dict]) -> str:
    """Hash of every row's evidence and label, so the labels a summary was measured on can be checked."""
    return text_hash(*(f"{text_hash(r['evidence'])} {r['label']}" for r in rows))


def rebuild_stats(check: str, spec: dict, calibration: Path = CALIBRATION) -> tuple[dict | None, str, str]:
    """Agreement recomputed from the stored labels and cached verdicts: (stats, labels hash, why not)."""
    rows = read_rows(calibration / f"{check}.jsonl")
    if not rows:
        return None, "", "no labelled rows"
    if any(r.get("label") not in ("pass", "fail") or r.get("script") != script_hash(spec) for r in rows):
        return None, "", "rows are unlabelled or were gathered with another evidence script"
    verdicts = []
    for r in rows:
        path = calibration / "verdicts" / f"{cache_key(spec['rubric'], r['evidence'])}.json"
        cached = json.loads(path.read_text()) if path.exists() else None
        if not cached or cached.get("model") != JUDGE_MODEL:
            return None, "", "a calibration verdict is missing or from another judge"
        verdicts.append(cached["verdict"])
    return agreement([r["label"] for r in rows], verdicts), labels_hash(rows), ""


def usable(check: str, spec: dict, calibration: Path = CALIBRATION) -> tuple[bool, str]:
    """Whether a judged check may enter results.

    The summary must be for this judge, rubric and evidence script. The
    numbers are rebuilt from the stored labels and verdicts, never read from
    the summary, so an edited summary cannot unlock a check.
    """
    path = calibration / f"{check}.json"
    if not path.exists():
        return False, "not calibrated"
    summary = json.loads(path.read_text())
    if summary.get("judge") != JUDGE_MODEL:
        return False, f"calibrated with another judge ({summary.get('judge')})"
    if summary.get("rubric") != rubric_hash(spec) or summary.get("script") != script_hash(spec):
        return False, "calibration is for another rubric or evidence script"
    stats, labels, why = rebuild_stats(check, spec, calibration)
    if stats is None:
        return False, why
    if summary.get("labels_sha256") != labels:
        return False, "labels changed since calibration"
    return gate(stats)


def gather_evidence(spec: dict, repo: Path, env: dict, run: str, arm: str, global_text: str | None) -> str:
    proc = subprocess.run(["bash", "-c", spec["evidence"]], cwd=repo, env=env, capture_output=True, text=True)
    return scrub(proc.stdout + proc.stderr, run=run, arm=arm, global_text=global_text)


def run_judged(scenario: dict, arm_name: str, stem: str, repo: Path, env: dict, run: Path,
               global_text: str | None, out: Path, cache_dir: Path, ledger=None,
               calibration: Path = CALIBRATION) -> tuple[dict, dict, dict, dict]:
    """Judged checks for one finished session: (verdicts for checks, details, unusable, missing).

    Evidence is always written to ``<out>/evidence`` so it can be labelled or
    judged later. The judge is asked only about calibrated checks. A check
    that is not calibrated is ``unusable``; one whose judge call failed is
    ``missing`` with the error. Neither enters the checks, and ``rejudge``
    fills the missing ones.
    """
    checks: dict[str, bool] = {}
    details: dict[str, dict] = {}
    unusable: dict[str, str] = {}
    missing: dict[str, str] = {}
    for name, spec in scenario.get("judged", {}).items():
        evidence = gather_evidence(spec, repo, env, str(run), arm_name, global_text)
        (out / "evidence").mkdir(parents=True, exist_ok=True)
        (out / "evidence" / f"{stem}__{name}.txt").write_text(evidence)
        ok, why = usable(name, spec, calibration)
        if not ok:
            unusable[name] = why
            continue
        try:
            verdict = judge(spec["rubric"], evidence, cache_dir, ledger)
        except (JudgeError, subprocess.TimeoutExpired) as exc:
            missing[name] = f"judge error: {str(exc)[:200]}"
            continue
        checks[name] = verdict["verdict"] == "pass"
        details[name] = {"verdict": verdict["verdict"], "reason": verdict["reason"]}
    return checks, details, unusable, missing


def scenario_spec(check: str) -> dict:
    """The judged spec for a check name; scenarios that share a check must share its spec."""
    sys.path.insert(0, str(HERE))
    from scenarios2 import SCENARIOS2
    specs = [sc["judged"][check] for sc in SCENARIOS2 if check in sc.get("judged", {})]
    if not specs or any(spec != specs[0] for spec in specs):
        raise SystemExit(f"{check}: needs at least one scenario, and every scenario with it must share one spec")
    return specs[0]


def read_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def collect(check: str, outs: list[Path], calibration: Path = CALIBRATION) -> int:
    """Add evidence from run folders as rows without a label; identical evidence is kept once."""
    spec = scenario_spec(check)
    path = calibration / f"{check}.jsonl"
    rows = read_rows(path)
    have = {r["evidence"] for r in rows}
    added = 0
    for out in outs:
        for file in sorted((out / "evidence").glob(f"*__{check}.txt")):
            evidence = file.read_text()
            if evidence not in have:
                have.add(evidence)
                rows.append({"evidence": evidence, "label": None, "reason": "", "script": script_hash(spec)})
                added += 1
    write_rows(path, rows)
    return added


def calibrate(check: str, jobs: int = 4, ledger=None, calibration: Path = CALIBRATION) -> dict:
    spec = scenario_spec(check)
    rows = read_rows(calibration / f"{check}.jsonl")
    if not rows:
        raise SystemExit(f"no labelled evidence in {calibration / (check + '.jsonl')}")
    bad = [i for i, r in enumerate(rows) if r.get("label") not in ("pass", "fail") or not r.get("reason")]
    if bad:
        raise SystemExit(f"rows without a label and reason: {bad[:10]}")
    stale = [i for i, r in enumerate(rows) if r.get("script") != script_hash(spec)]
    if stale:
        raise SystemExit(f"rows gathered with another evidence script, relabel them: {stale[:10]}")
    verdicts_dir = calibration / "verdicts"
    with cf.ThreadPoolExecutor(jobs) as pool:
        results = list(pool.map(lambda r: judge(spec["rubric"], r["evidence"], verdicts_dir, ledger), rows))
    stats = agreement([r["label"] for r in rows], [v["verdict"] for v in results])
    ok, why = gate(stats)
    disagreements = [i for i, (r, v) in enumerate(zip(rows, results)) if r["label"] != v["verdict"]]
    summary = {"check": check, **stats, "usable": ok, "reason": why or "meets the gate",
               "rubric": rubric_hash(spec), "script": script_hash(spec), "judge": JUDGE_MODEL,
               "labels_sha256": labels_hash(rows),
               "labelled_by": "a Claude model, from each transcript and the repository state",
               "disagreements": [{"row": i, "label": rows[i]["label"], "label_reason": rows[i]["reason"],
                                  "judge_reason": results[i]["reason"]} for i in disagreements]}
    (calibration / f"{check}.json").write_text(json.dumps(summary, indent=1) + "\n")
    return summary


def regather(out: Path, only: str | None = None) -> int:
    """Rebuild the evidence files of a run folder (those of one check, if named) from the sessions' sandbox directories.

    For when an evidence script changes after sessions have run: the sessions
    stay as they are and only the text shown to a judge is produced again.
    """
    import os

    sys.path.insert(0, str(HERE))
    import run

    by_id = {s["id"]: s for s in run.SCENARIOS}
    rebuilt = 0
    for path in sorted((out / "results").glob("*.json")):
        result = json.loads(path.read_text())
        scenario = by_id.get(result["scenario"], {})
        if not scenario.get("judged"):
            continue
        arm = next((a for a in scenario["arms"] if a["name"] == result["arm"]), None)
        if arm is None:  # the arm was removed from the scenario since this session ran
            continue
        text = run.global_text(arm["global"], arm.get("fixture", "global-under-test.md"))
        for old, new in arm.get("edits", []):
            text = (text or "").replace(old, new)
        directory = Path(result["run"])
        env = run.session_env(directory, run.SANDBOX_ROOT / "cache")
        env["BASE"] = (directory / "base").read_text()
        for name, spec in scenario["judged"].items():
            if only and name != only:
                continue
            evidence = gather_evidence(spec, directory / "repo", env, str(directory), arm["name"], text)
            (out / "evidence").mkdir(parents=True, exist_ok=True)
            (out / "evidence" / f"{path.stem}__{name}.txt").write_text(evidence)
            rebuilt += 1
    return rebuilt


def rejudge(out: Path, ledger=None, calibration: Path = CALIBRATION) -> tuple[int, int]:
    """Fill verdicts a judge error left missing, from the evidence saved with each session.

    Returns (filled, still missing). A result keeps everything else it had.
    """
    sys.path.insert(0, str(HERE))
    import run

    by_id = {s["id"]: s for s in run.SCENARIOS}
    filled = missing = 0
    for path in sorted((out / "results").glob("*.json")):
        result = json.loads(path.read_text())
        gaps = result.get("judged_missing") or {}
        if not gaps:
            continue
        for name in list(gaps):
            spec = by_id[result["scenario"]]["judged"][name]
            ok, why = usable(name, spec, calibration)
            evidence_file = out / "evidence" / f"{path.stem}__{name}.txt"
            if not ok or not evidence_file.exists():
                missing += 1
                continue
            try:
                verdict = judge(spec["rubric"], evidence_file.read_text(), out.resolve().parent / "judge-cache", ledger)
            except (JudgeError, subprocess.TimeoutExpired) as exc:
                gaps[name] = f"judge error: {str(exc)[:200]}"
                missing += 1
                continue
            result["checks"][name] = verdict["verdict"] == "pass"
            result.setdefault("judged", {})[name] = {"verdict": verdict["verdict"], "reason": verdict["reason"]}
            del gaps[name]
            filled += 1
        result["judged_missing"] = gaps
        path.write_text(json.dumps(result, indent=1))
    return filled, missing


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["collect", "calibrate", "regather", "rejudge"])
    ap.add_argument("check", nargs="?", help="judged check name; for regather, limits it to that check")
    ap.add_argument("--out", type=Path, action="append", default=[])
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--ledger", type=Path, help="spend ledger to record judge calls in")
    args = ap.parse_args()
    if args.action == "regather":
        if not args.out:
            raise SystemExit("regather needs --out")
        print(f"rebuilt {sum(regather(out, args.check) for out in args.out)} evidence files")
        return
    if args.action == "rejudge":
        if not args.out:
            raise SystemExit("rejudge needs --out")
        sys.path.insert(0, str(HERE))
        ledger = None
        if args.ledger:
            from run import Ledger
            ledger = Ledger(args.ledger)
        for out in args.out:
            filled, left = rejudge(out, ledger)
            print(f"{out}: filled {filled}, still missing {left}")
        return
    if not args.check:
        raise SystemExit(f"{args.action} needs a check name")
    if args.action == "collect":
        if not args.out:
            raise SystemExit("collect needs --out")
        print(f"added {collect(args.check, args.out)} rows")
        return
    sys.path.insert(0, str(HERE))
    ledger = None
    if args.ledger:
        from run import Ledger
        ledger = Ledger(args.ledger)
    summary = calibrate(args.check, args.jobs, ledger)
    print(json.dumps({k: v for k, v in summary.items() if k != "disagreements"}, indent=1))
    for d in summary["disagreements"]:
        print(f"row {d['row']}: label {d['label']} ({d['label_reason']}) / judge ({d['judge_reason']})")


if __name__ == "__main__":
    main()
