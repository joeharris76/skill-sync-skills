#!/usr/bin/env python3
"""Scan every tracked catalog skill with SkillSpector and fail on new findings.

Static analysis only (``--no-llm``): no credentials, no model calls. Each
skill is scanned on its own because SkillSpector refuses ``--baseline`` on a
recursive multi-skill scan.

Accepted findings live in ``.skillspector/baselines/<skill>.yaml``, one file
per skill that has any. The reasons are explained in
``docs/skillspector-triage.md``. The scan fails when:

- a skill reports a finding its baseline does not cover;
- a baseline entry no longer suppresses anything, so stale entries cannot
  pile up and hide a later finding;
- a baseline suppresses by rule instead of by fingerprint, keeps the
  scanner's auto-generated reason, or names a skill that is not tracked;
- a scan fails or does not inspect every file;
- the installed SkillSpector is not the pinned version.

Usage:
  python3 scripts/skillspector_scan.py            # scan all tracked skills
  python3 scripts/skillspector_scan.py code todo  # scan the named skills
  python3 scripts/skillspector_scan.py --print-commit

``SKILLSPECTOR_BIN`` overrides the executable (default: ``skillspector`` on
PATH). Standard library only.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# The scanner pin. CI installs exactly this commit with its own lockfile; bump
# both values together and regenerate the baselines (README, "Security scan").
PINNED_COMMIT = "9dc82fe473329b2b742aa5097dcfe7ae55f51b01"
PINNED_VERSION = "2.12.0"

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"
BASELINES_DIR = ROOT / ".skillspector" / "baselines"

FINGERPRINT_RE = re.compile(r"^- hash:", re.MULTILINE)
EMPTY_RULES_RE = re.compile(r"^rules: \[\]$", re.MULTILINE)
RULES_KEY_RE = re.compile(r"^rules\s*:", re.MULTILINE)
DEFAULT_REASON = "auto-generated baseline"


def tracked_skills() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "skills/*/SKILL.md"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout
    return sorted({line.split("/")[1] for line in out.splitlines() if line})


def scanner() -> str:
    binary = os.environ.get("SKILLSPECTOR_BIN") or shutil.which("skillspector")
    if not binary:
        sys.exit("error: skillspector not found; see README.md, 'Security scan'")
    reported = subprocess.run([binary, "--version"], capture_output=True, text=True).stdout
    if f"v{PINNED_VERSION}" not in reported.split():
        sys.exit(f"error: SkillSpector v{PINNED_VERSION} is pinned, but {binary} reports {reported.strip()!r}")
    return binary


def baseline_problems(baseline: Path) -> list[str]:
    text = baseline.read_text(encoding="utf-8")
    problems = []
    # A second top-level `rules:` key would win in a YAML loader, so require
    # exactly one, and that one empty.
    if len(RULES_KEY_RE.findall(text)) != 1 or not EMPTY_RULES_RE.search(text):
        problems.append("baseline must have exactly one `rules: []`; suppress by fingerprint only")
    if DEFAULT_REASON in text:
        problems.append("baseline entry keeps the auto-generated reason; write the real one")
    if not FINGERPRINT_RE.search(text):
        problems.append("baseline has no entries; delete the file")
    return problems


def scan(binary: str, skill: str, workdir: Path) -> list[str]:
    """Return the problems found for one skill (empty when it is clean)."""
    report = workdir / f"{skill}.json"
    baseline = BASELINES_DIR / f"{skill}.yaml"
    command = [
        binary, "scan", str(SKILLS_DIR / skill),
        "--no-llm", "--format", "json", "--output", str(report),
    ]
    problems: list[str] = []
    expected_suppressed = 0
    if baseline.is_file():
        problems += baseline_problems(baseline)
        command += ["--baseline", str(baseline)]
        expected_suppressed = len(FINGERPRINT_RE.findall(baseline.read_text(encoding="utf-8")))
    result = subprocess.run(command, capture_output=True, text=True)
    # Exit 1 means a high risk score; the report is still written and lists
    # the findings. Any other failure, or no report, is a scanner error.
    if result.returncode not in (0, 1) or not report.is_file():
        tail = (result.stdout + result.stderr).strip().splitlines()[-5:]
        return problems + [f"scan failed (exit {result.returncode}): " + " | ".join(tail)]
    data = json.loads(report.read_text(encoding="utf-8"))
    completeness = data.get("analysis_completeness", {})
    if data.get("execution_successful") is not True or completeness.get("coverage_percent") != 100.0:
        problems.append(f"scan incomplete: coverage {completeness.get('coverage_percent')}%")
    for issue in data.get("issues", []):
        location = issue.get("location", {})
        problems.append(
            f"{issue.get('severity')} {issue.get('id')} {issue.get('pattern')}: "
            f"{location.get('file')}:{location.get('start_line')} ({issue.get('finding')!r})"
        )
    suppressed = data.get("suppressed_count", 0)
    if suppressed != expected_suppressed:
        problems.append(
            f"baseline lists {expected_suppressed} finding(s) but the scan suppressed {suppressed}; "
            "regenerate the baseline"
        )
    return problems


def main(argv: list[str]) -> int:
    if argv == ["--print-commit"]:
        print(PINNED_COMMIT)
        return 0
    known = tracked_skills()
    skills = argv or known
    unknown = sorted(set(skills) - set(known))
    if unknown:
        sys.exit(f"error: not a tracked skill: {', '.join(unknown)}")
    if not skills:
        sys.exit("error: no tracked skills found under skills/")
    orphans = sorted(p.stem for p in BASELINES_DIR.glob("*") if p.suffix != ".yaml" or p.stem not in known)
    if orphans:
        sys.exit(f"error: baseline without a tracked skill: {', '.join(orphans)}")
    binary = scanner()
    failed = 0
    with tempfile.TemporaryDirectory() as tmp:
        for skill in skills:
            problems = scan(binary, skill, Path(tmp))
            failed += bool(problems)
            print(f"{'FAIL' if problems else 'ok  '} {skill}")
            for problem in problems:
                print(f"       {problem}")
    print(f"\n{len(known)} tracked, {len(skills)} scanned, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
