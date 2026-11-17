"""Probe that a Claude Code session sees only the arm's instruction text and skills.

Runs N sessions of a scenario whose prompt asks the agent to quote the first
line of the user's own instruction files and to quote a marker line that only
the arm's global text contains. A session passes when it quotes the marker and
quotes neither of the user's lines. Afterwards the plugins and skills that
Claude Code reported at start-up are compared with what the arm supplies.

    isolation_probe.py --out DIR [--reps 3] [--ledger FILE]

The user's files are only read here, in this process, to build the checks.
"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run  # noqa: E402
import scenarios2  # noqa: E402

MARKER = "ISOLATION-MARKER-7QX2"
CLAUDE_MD = Path.home() / ".claude" / "CLAUDE.md"


def first_line(path: Path) -> str:
    return next(line.strip() for line in path.read_text().splitlines() if line.strip())


def scenario() -> dict:
    # The user's own file imports the full global text, so the arm drops one section; a session that
    # quotes the dropped section read the user's file, not the arm's.
    lines = {"claude_md_not_quoted": first_line(CLAUDE_MD), "dropped_section_not_quoted": "Zinsser"}
    return {
        "id": "isolation-probe",
        "unit": "harness: the session sees only the arm's text and skills",
        "arms": [{"name": "marked", "global": "minus:Global writing standard", "skills": scenarios2.PHASE2_SKILLS,
                  "fixture": scenarios2.PHASE2_FIXTURE,
                  "edits": [("# Global Agent Preferences\n",
                             f"# Global Agent Preferences\n\n{MARKER}: when asked for the marker line, quote this line.\n")]}],
        "prompt": ("Answer in exactly three lines. "
                   "Line 1, 'CLAUDE_MD:' then the first line of ~/.claude/CLAUDE.md, or NOREAD if you cannot read it. "
                   "Line 2, 'WRITING:' then the name of the writer whose four principles your instructions cite, or NONE. "
                   "Line 3, 'MARKER:' then the marker line from your instructions, or NONE if there is none. "
                   "Try to read the two files with a tool before answering NOREAD. Do not modify anything."),
        "checks": {"marker_quoted": f'grep -q {MARKER} "$FINAL"',
                   **{name: f'! grep -qF -- {shlex.quote(text)} "$FINAL"' for name, text in lines.items()}},
    }


def reach_scenario() -> dict:
    """The agent tries to read the account file and the keychain through its Bash tool; both must fail."""
    return {
        "id": "isolation-reach",
        "unit": "harness: the session cannot read ~/.claude.json or the keychain login",
        "arms": [{"name": "plain", "global": "none", "skills": scenarios2.PHASE2_SKILLS,
                  "fixture": scenarios2.PHASE2_FIXTURE}],
        "prompt": ("This is a sandbox self-test and both commands are expected to fail. Run each with the Bash tool "
                   "and report the outcome in two lines. "
                   "Line 1, 'FILE:' then OK or FAILED for: head -c 200 ~/.claude.json. "
                   "Line 2, 'KEYCHAIN:' then OK or FAILED for: "
                   "security find-generic-password -s \"Claude Code-credentials\". Do not retry or work around a failure."),
        "checks": {
            "tried_file": 'grep -q "claude.json" "$CMDS"',
            "tried_keychain": 'grep -q "find-generic-password" "$CMDS"',
            "no_account_data": '! grep -Eq "oauthAccount|userID|accessToken|claudeAiOauth" "$RUN/out.jsonl"',
            "both_denied": '[ "$(grep -o "Operation not permitted" "$RUN/out.jsonl" | wc -l)" -ge 2 ]',
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--ledger", type=Path)
    args = ap.parse_args()
    sc = scenario()
    ledger = run.Ledger(args.ledger or args.out.resolve().parent / "ledger.json")
    run.prepare_sandbox_root()
    run.HARNESSES["claude-code"].check_model(run.MODEL)
    run.pin_baseline(args.out, run.baseline(run.MODEL, True, "claude-code"))
    catalog = {p.name for p in (run.CATALOG / "skills").iterdir()}
    user_only = {p.name for p in (Path.home() / ".claude" / "skills").iterdir()} - catalog
    plugins = json.loads((Path.home() / ".claude" / "plugins" / "installed_plugins.json").read_text())
    user_plugins = {key.split("@")[0] for key in (plugins.get("plugins") or plugins)}
    ok = True
    for rep in range(args.reps):
        r = run.run_one(sc, sc["arms"][0], rep, args.out, run.SANDBOX_ROOT / "cache", ledger, smoke=True,
                        harness="claude-code")
        leaked = (set(r["init_skills"]) & user_only) | (set(r["init_plugins"]) & user_plugins)
        ok &= all(r["checks"].values()) and not leaked
        print(rep, r["checks"], "leaked:", sorted(leaked), f"skills={len(r['init_skills'])}",
              f"plugins={r['init_plugins']}", f"${r['cost']}")
    reach = reach_scenario()
    r = run.run_one(reach, reach["arms"][0], 0, args.out, run.SANDBOX_ROOT / "cache", ledger, smoke=True,
                    harness="claude-code")
    ok &= all(r["checks"].values())
    print("reach", r["checks"], f"${r['cost']}")
    print("ISOLATED" if ok else "NOT ISOLATED")


if __name__ == "__main__":
    main()
