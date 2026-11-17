"""Phase 3 trigger evaluation: does a deployed skill load without being asked?

180 one-turn scenarios, 20 per in-scope skill, run in one arm (`full`: the deployed global file and skills,
pinned below). No prompt names the skill or tells the agent to read one. The measure is whether the agent read
the skill (`skills_read` in the result), per prompt type:

  explicit    names an activity the skill's description lists
  implicit    the task needs the skill but does not name its activity
  contextual  the repository state makes the skill relevant; the prompt is short
  near-miss   looks related, but the skill should NOT load

Loading is a metric, not a pass/fail rule, so scenarios carry no checks. The `read_by_path` metric is a second
count of the same thing from the tool calls in the transcript (a read of skill://<name> or of the skill's file
path), so a skill read by file path is not missed by `skills_read`, which matches only `skill://` text.

Prereg: prereg/phase3-trigger.md. Prompts are paraphrased from real triggers; they hold no private text.
"""

from __future__ import annotations

from scenarios2 import (HANDOFF_SETUP, LEGACY_COPY, LEGACY_TEST, REORDER_SETUP, TRACKER_BOOTSTRAP, seed_items)

TRIGGER_SKILLS = "a0c0d4b31b892557735732f367647d39132e2c9c"  # global skills pin for phase 3
TRIGGER_FIXTURE = "global-phase3.md"  # byte copy of deployment/global/AGENTS.md at that commit
ARM = {"name": "full", "global": "full", "skills": TRIGGER_SKILLS, "fixture": TRIGGER_FIXTURE}

SKILLS = ["change-framework", "review-protocol", "investigation-framework", "agent-execution",
          "session-takeover", "todo", "code", "test", "docs"]
KINDS = {"explicit": 6, "implicit": 6, "contextual": 4, "near-miss": 4}

# --- sandbox setups (each runs after base_setup.sh, in the sandbox repository) ----------------------------------

# Two unmerged local branches, both pushed.
BRANCHES = r"""
git checkout -qb feature/low-stock
cat > inventory/report.py <<'EOF'
# Low-stock report.


def low_stock_report(items: list[dict], threshold: int = 5) -> list[str]:
    return [f"{i['name']}: {i['count']}" for i in items if i["count"] <= threshold]
EOF
git add -A && git commit -qm "feat: low-stock report" && git push -q -u origin feature/low-stock
git checkout -q main
git checkout -qb feature/csv-export
cat >> inventory/export.py <<'EOF'


def export_csv(items: list[dict], dest) -> None:
    # Write a header row name,count and one row per item.
    lines = ["name,count"] + [f"{i['name']},{i['count']}" for i in items]
    dest.write_text("\n".join(lines) + "\n")
EOF
git add -A && git commit -qm "feat: export_csv" && git push -q -u origin feature/csv-export
git checkout -q main
"""

# A half-done change left in the working tree on a task branch.
DIRTY = r"""
git checkout -qb work/csv-export
cat >> inventory/export.py <<'EOF'


def export_csv(items: list[dict], dest) -> None:
    raise NotImplementedError
EOF
echo "scratch: ask Sam about the supplier invoice" > notes-scratch.txt
"""

# An interrupted session: a branch with one commit, a handoff file, and an unfinished edit.
INTERRUPTED = HANDOFF_SETUP + r"""
git checkout -qb work/csv-export
cat >> inventory/export.py <<'EOF'


def export_csv(items: list[dict], dest) -> None:
    lines = ["name,count"] + [f"{i['name']},{i['count']}" for i in items]
    dest.write_text("\n".join(lines) + "\n")
EOF
git add -A && git commit -qm "feat: export_csv" && git push -q -u origin work/csv-export
cat > HANDOFF.md <<'EOF'
# Handoff: CSV export for the accountant (session label csv-export-spike)

Goal: the accountant gets CSV instead of JSON.
Done: export_csv in inventory/export.py (committed on work/csv-export).
Open: tests for export_csv; point scripts/accountant.sh at it; README update.
Verify: uv run --no-project -q python -m unittest discover -s tests
The run stopped when the previous agent hit its usage limit.
EOF
echo "# draft: also add a CSV section to the README" > README-draft.txt
"""

# A plan and the decisions already taken.
PLAN = r"""
cat > PLAN.md <<'EOF'
# Plan: reorder automation

1. Read counts from the JSON store.
2. Compute restock_plan against a target of 40 units.
3. Email the plan to the shop owner every Monday.
4. Keep the discount at 10% for orders over 100 units.
EOF
cat > DECISIONS.md <<'EOF'
# Decisions

- 2026-10-02: the JSON file stays the system of record; no database.
- 2026-10-09: the discount for bulk orders applies from 100 units, not above 100.
- 2026-10-16: no email; the plan is printed by a script.
EOF
git add -A && git commit -qm "docs: add plan and decisions" && git push -q origin main
"""

# A reviewer's comments on the reorder module.
REVIEW_COMMENTS = REORDER_SETUP + r"""
cat > REVIEW.md <<'EOF'
# Review comments on the reorder module

1. restock_plan changes the list it is given.
2. order_cost applies the bulk discount one unit too late.
3. low_stock misses items whose count equals the threshold.
EOF
git add -A && git commit -qm "docs: record review comments" && git push -q origin main
"""

# Claims in a notes file that the code may not support, and a failing CI log.
NOTES = r"""
cat > NOTES.md <<'EOF'
# Notes

The store is safe to call from several threads at once. The nightly export always runs after the store is
written, so it never sees a partial file. Counts never go negative.
EOF
cat > ci.log <<'EOF'
FAIL: test_total_rounds_to_cents (tests.test_calc.CalcTest)
AssertionError: 19.99 != 20.0
Ran 3 tests in 0.002s  FAILED (failures=1)
EOF
git add -A && git commit -qm "docs: add notes and last CI log" && git push -q origin main
"""

# Two overlapping usage notes, plus a stale statement in the README.
DOCS = r"""
mkdir -p docs
cat > docs/usage.md <<'EOF'
# Using inventory

Call set_count(path, name, count) to store a count. Call find_item(items, name) to look one up.
The JSON file is the system of record. Run bench.py to time find_item; the budget is 50 ms.
Run bench.py before every release. Run bench.py before every release.
EOF
cat > docs/usage-draft.md <<'EOF'
# Using inventory (draft)

Use set_count to store a count and find_item to look up an item. Exports: export_json writes a JSON array.
The JSON file is the system of record.
EOF
cat >> README.md <<'EOF'

## Exports

The accountant receives CSV files written by export_csv.
EOF
git add -A && git commit -qm "docs: add usage notes" && git push -q origin main
"""

# Untracked documentation and an untracked test, to commit.
UNCOMMITTED_DOCS = r"""
mkdir -p docs
cat > docs/exports.md <<'EOF'
# Exports

export_json writes name and count for every item as a JSON array.
EOF
"""
UNCOMMITTED_TEST = r"""
cat > tests/test_export_json.py <<'EOF'
import json
import tempfile
import unittest
from pathlib import Path

from inventory.export import export_json


class ExportJsonTest(unittest.TestCase):
    def test_writes_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "out.json"
            export_json([{"name": "A", "count": 2}], dest)
            self.assertEqual(json.loads(dest.read_text()), [{"name": "A", "count": 2}])


if __name__ == "__main__":
    unittest.main()
EOF
"""

# A slow test, so a full run takes a long while.
SLOW_TEST = r"""
cat > tests/test_slow_export.py <<'EOF'
import time
import unittest


class SlowExportTest(unittest.TestCase):
    def test_export_large_file(self):
        time.sleep(25)


if __name__ == "__main__":
    unittest.main()
EOF
git add -A && git commit -qm "test: add large export test" && git push -q origin main
"""

# Three independent chores listed for an agent.
CHORES = r"""
cat > TASKS.md <<'EOF'
# Open chores (independent of each other)

- inventory/calc.py: add docstrings to every function that lacks one.
- inventory/store.py: add type hints to load and save.
- inventory/export.py: add a module-level __all__.
EOF
git add -A && git commit -qm "docs: list chores" && git push -q origin main
"""

# A sandbox tracker with a ready queue.
TRACKER = TRACKER_BOOTSTRAP + seed_items([
    {"id": "round-total-price", "priority": "high",
     "title": "total_price truncates instead of rounding to cents",
     "description": "inventory/calc.py total_price uses int(total * 100) / 100. 19.999 becomes 19.99; it must be 20.0.",
     "acceptance": ["tests/test_calc.py passes, including test_total_rounds_to_cents"]},
    {"id": "csv-export", "priority": "medium", "title": "Add CSV export next to the JSON export",
     "description": "inventory/export.py has export_json. Add export_csv(items, dest) next to it.",
     "acceptance": ["export_csv writes a name,count header and one row per item"]},
    {"id": "readme-bench-note", "priority": "low", "title": "Explain in the README how to run bench.py",
     "acceptance": ["README shows the command"]}])

ROADMAP = r"""
cat >> README.md <<'EOF'

## Roadmap

- The accountant still receives JSON only. A CSV export is missing.
- Nothing warns when an item count drops below 5. A low-stock report is missing.
EOF
git commit -qam "docs: add a roadmap section" && git push -q origin main
"""

SETUPS = {
    "plain": "",
    "reorder": REORDER_SETUP,
    "branches": BRANCHES,
    "dirty": DIRTY,
    "interrupted": INTERRUPTED,
    "plan": PLAN,
    "review-comments": REVIEW_COMMENTS,
    "notes": NOTES,
    "legacy-copy": LEGACY_COPY,
    "docs": DOCS,
    "uncommitted-docs": UNCOMMITTED_DOCS,
    "uncommitted-test": UNCOMMITTED_TEST,
    "slow-test": SLOW_TEST,
    "network-test": LEGACY_TEST,
    "chores": CHORES,
    "tracker": TRACKER,
    "roadmap": ROADMAP,
}

# --- prompts ----------------------------------------------------------------------------------------------------
# skill -> (kind, setup, prompt). The base repository's total_price truncates and one test fails.

PROMPTS: dict[str, list[tuple[str, str, str]]] = {
    "change-framework": [
        ("explicit", "plain", "Fix the rounding bug in total_price."),
        ("explicit", "plain", "Add export_csv(items, dest) to inventory/export.py with a test, and commit it on a task branch."),
        ("explicit", "dirty", "Commit the work in the tree and push it."),
        ("explicit", "branches", "Open a draft PR for feature/csv-export."),
        ("explicit", "plain", "Change apply_discount so a percent above 100 raises ValueError, and update its test."),
        ("explicit", "plain", "Add a bulk_set_count helper to inventory/store.py, test it, then commit and push."),
        ("implicit", "plain", "The shop owner says totals are off by a cent on some orders. Sort it out."),
        ("implicit", "plain", "Make find_item ignore case when matching names."),
        ("implicit", "plain", "Rename set_count to update_count everywhere it is used."),
        ("implicit", "plain", "Nobody calls export_json any more. Get rid of it."),
        ("implicit", "plain", "bench.py should also print how many items it timed. Do that."),
        ("implicit", "plain", "Make load return an empty list when the file holds invalid JSON."),
        ("contextual", "dirty", "Finish this."),
        ("contextual", "branches", "Wrap up the CSV work."),
        ("contextual", "plain", "Get the suite green."),
        ("contextual", "legacy-copy", "The old monthly-report module has the same rounding problem. Fix it too."),
        ("near-miss", "plain", "Explain what total_price does and why its test fails. Do not change anything."),
        ("near-miss", "plain", "What is the difference between apply_discount and total_price? Just answer."),
        ("near-miss", "branches", "Show me the commit log of feature/low-stock."),
        ("near-miss", "plain", "List the functions in inventory/ that have no test. Read only."),
    ],
    "review-protocol": [
        ("explicit", "reorder", "Review inventory/reorder.py."),
        ("explicit", "plain", "Audit this repository for defects and report them."),
        ("explicit", "reorder", "Do an adversarial review of the reorder module."),
        ("explicit", "branches", "Review the changes on feature/low-stock against main."),
        ("explicit", "plan", "Review the plan in PLAN.md before we start."),
        ("explicit", "plain", "Assess whether keeping stock counts in a single JSON file is the right fit for this shop."),
        ("implicit", "reorder", "Look at reorder.py and tell me if it is safe to ship."),
        ("implicit", "reorder", "Is the restock plan logic right? I only want an opinion."),
        ("implicit", "plain", "Anything wrong with how store.py writes the file?"),
        ("implicit", "branches", "Second opinion on feature/csv-export before I merge it."),
        ("implicit", "plan", "Sanity check my approach in PLAN.md."),
        ("implicit", "plain", "What would you flag in this repository if you were reading it cold?"),
        ("contextual", "review-comments", "Go through the reviewer's comments."),
        ("contextual", "branches", "Both branches say they are ready. What do you think?"),
        ("contextual", "plan", "Reconcile PLAN.md with what we decided earlier."),
        ("contextual", "reorder", "Ship it?"),
        ("near-miss", "reorder", "Write a docstring for reorder_quantity."),
        ("near-miss", "plain", "Run the tests and tell me the result."),
        ("near-miss", "reorder", "What does within_budget return for an empty list of orders?"),
        ("near-miss", "plain", "Summarize the README in one sentence."),
    ],
    "investigation-framework": [
        ("explicit", "plain", "Find out why test_total_rounds_to_cents fails."),
        ("explicit", "reorder", "Investigate why restock_plan leaves the caller's list changed."),
        ("explicit", "reorder", "Debug why low_stock misses items that sit exactly at the threshold."),
        ("explicit", "legacy-copy", "Compare inventory/calc.py and inventory/legacy_calc.py and tell me how they differ."),
        ("explicit", "plain", "Why is bench.py timing find_item slower than the budget on my machine? Find the cause."),
        ("explicit", "notes", "NOTES.md says the store is thread-safe. Check whether that is true."),
        ("implicit", "plain", "Totals are off by a cent on some orders."),
        ("implicit", "reorder", "The cost of an order of exactly 100 units looks wrong."),
        ("implicit", "plain", "Something about discounts in this repo is off. Work out what."),
        ("implicit", "plain", "The accountant says the counts she gets look stale. Where could that come from?"),
        ("implicit", "plain", "Make find_item faster."),
        ("implicit", "notes", "Can I trust the claims in NOTES.md?"),
        ("contextual", "notes", "The CI log is in ci.log."),
        ("contextual", "plain", "Why is the suite red?"),
        ("contextual", "legacy-copy", "Two modules, same bug, only one is imported by tests. Make sense of it."),
        ("contextual", "reorder", "Counts in the store drop after I run the restock plan."),
        ("near-miss", "plain", "Add a line to the README on how to run bench.py."),
        ("near-miss", "plain", "Print the contents of README.md."),
        ("near-miss", "plain", "Add .DS_Store to .gitignore."),
        ("near-miss", "plain", "Explain in two sentences what a JSON array is."),
    ],
    "agent-execution": [
        ("explicit", "plain", "Delegate the rounding fix to a subagent and check its work."),
        ("explicit", "reorder", "Which agent role and reasoning effort should I use to review reorder.py?"),
        ("explicit", "branches", "Launch an independent reviewer on feature/low-stock, preferably on a different model."),
        ("explicit", "chores", "Dispatch one worker per chore in TASKS.md, in parallel."),
        ("explicit", "plain", "How do I hand a task from this session to an advisor role?"),
        ("explicit", "branches", "Run an external agent harness as a reviewer on the diff of feature/csv-export."),
        ("implicit", "reorder", "Have someone else check reorder.py independently of you."),
        ("implicit", "plain", "Add tests for calc, store and export at the same time, as separate pieces of work."),
        ("implicit", "plain", "I want a second model to look at the rounding fix once you are done."),
        ("implicit", "branches", "Get a fresh pair of eyes, one that has not seen this conversation, on feature/csv-export."),
        ("implicit", "plain", "Use a cheaper model for the mechanical rename of find_item to find_by_name."),
        ("implicit", "chores", "Split the work in TASKS.md so it finishes faster."),
        ("contextual", "chores", "Work through TASKS.md."),
        ("contextual", "branches", "Get both branches reviewed before anything merges."),
        ("contextual", "reorder", "This needs a manager and a reviewer, not just you."),
        ("contextual", "interrupted", "Hand the remaining steps in HANDOFF.md to workers."),
        ("near-miss", "plain", "Run bench.py and tell me the time it prints."),
        ("near-miss", "plain", "Read inventory/calc.py and explain total_price."),
        ("near-miss", "plain", "Explain the delegation design pattern in object-oriented code, with a short Python example."),
        ("near-miss", "plain", "Run the test suite yourself and report the failures."),
    ],
    "session-takeover": [
        ("explicit", "interrupted", "Take over the session on branch work/csv-export."),
        ("explicit", "interrupted", "Resume the interrupted session from HANDOFF.md."),
        ("explicit", "interrupted", "Continue from this handoff: HANDOFF.md."),
        ("explicit", "interrupted", "Take over the session labelled csv-export-spike."),
        ("explicit", "interrupted", "Pick up where the crashed session left off. Its branch is work/csv-export."),
        ("explicit", "interrupted", "Take over the session that was rate limited and finish its work; the handoff is in HANDOFF.md."),
        ("implicit", "interrupted", "The last agent hit its usage limit halfway through. Finish its work."),
        ("implicit", "interrupted", "Someone started the CSV export. Pick it up."),
        ("implicit", "interrupted", "My other session died. See HANDOFF.md and carry on."),
        ("implicit", "interrupted", "There is a half-done branch, work/csv-export. Finish what was started."),
        ("implicit", "interrupted", "Continue the CSV export from yesterday."),
        ("implicit", "interrupted", "The previous run ended mid-change. What is left to do, and do it?"),
        ("contextual", "interrupted", "Carry on."),
        ("contextual", "dirty", "Continue."),
        ("contextual", "interrupted", "What's next?"),
        ("contextual", "interrupted", "Where were we?"),
        ("near-miss", "dirty", "Write a handoff note for the next agent."),
        ("near-miss", "plain", "Show the last five commits."),
        ("near-miss", "plain", "Start the low-stock report from scratch on a new branch."),
        ("near-miss", "plain", "What is the difference between git rebase and git merge?"),
    ],
    "todo": [
        ("explicit", "tracker", "Show the TODO items."),
        ("explicit", "tracker", "Create a TODO for adding a low-stock report, with acceptance criteria."),
        ("explicit", "tracker", "Prioritize the TODOs."),
        ("explicit", "tracker", "What should we work on next?"),
        ("explicit", "tracker", "Implement the TODO round-total-price."),
        ("explicit", "plain", "Write a spec for a low-stock report."),
        ("implicit", "plain", "Track the CSV export work so it does not get forgotten."),
        ("implicit", "tracker", "Which of the open items is ready to start?"),
        ("implicit", "tracker", "The rounding item is done. Close it out."),
        ("implicit", "tracker", "Park the README bench note until the CSV work lands."),
        ("implicit", "tracker", "Rank what is left by how much it matters."),
        ("implicit", "plain", "Brainstorm ways to reduce stock-count mistakes in this shop."),
        ("contextual", "tracker", "Go."),
        ("contextual", "roadmap", "Plan out the roadmap in the README."),
        ("contextual", "tracker", "Do the next thing."),
        ("contextual", "tracker", "I tried to finish csv-export and it refused. Why?"),
        ("near-miss", "plain", "Add a comment above total_price saying a review of the rounding is still due."),
        ("near-miss", "plain", "List every TODO comment in the source files."),
        ("near-miss", "plain", "Add a short checklist of manual release steps to README.md."),
        ("near-miss", "plain", "What does a todo comment usually look like in Python? Just answer."),
    ],
    "code": [
        ("explicit", "reorder", "Implement a low-stock alert in inventory/reorder.py that returns names and counts."),
        ("explicit", "reorder", "Refactor restock_plan so it does not modify its input."),
        ("explicit", "reorder", "Review the code in inventory/reorder.py."),
        ("explicit", "plain", "Debug the error behind the failing test in this repository."),
        ("explicit", "plain", "Improve the performance of find_item."),
        ("explicit", "legacy-copy", "Shrink the code: the two calc modules are mostly the same."),
        ("implicit", "plain", "The accountant wants CSV."),
        ("implicit", "reorder", "Orders of exactly 100 units miss the bulk discount."),
        ("implicit", "plain", "bench.py reports more than the 50 ms budget. Fix that."),
        ("implicit", "plain", "Get the tests passing."),
        ("implicit", "legacy-copy", "Clean up inventory/. There is duplicated code."),
        ("implicit", "review-comments", "The review comments are in REVIEW.md. Deal with them."),
        ("contextual", "review-comments", "Address the follow-ups."),
        ("contextual", "legacy-copy", "Tidy up."),
        ("contextual", "plain", "Iterate until green."),
        ("contextual", "branches", "Finish the open feature branches."),
        ("near-miss", "reorder", "Explain what restock_plan does."),
        ("near-miss", "reorder", "What does LOW_STOCK_THRESHOLD control?"),
        ("near-miss", "plain", "Show git status."),
        ("near-miss", "plain", "Summarize README.md."),
    ],
    "test": [
        ("explicit", "plain", "Write tests for inventory/export.py."),
        ("explicit", "plain", "Run the tests."),
        ("explicit", "plain", "Fix the failing test."),
        ("explicit", "slow-test", "The test suite is slow. Speed it up."),
        ("explicit", "reorder", "Find the coverage gaps in the inventory package."),
        ("explicit", "uncommitted-test", "Commit the test changes."),
        ("implicit", "plain", "Make sure export_json is covered."),
        ("implicit", "plain", "Add a regression check for the discount clamp."),
        ("implicit", "reorder", "Is reorder.py protected against regressions?"),
        ("implicit", "plain", "Check that nothing broke after my change to calc.py."),
        ("implicit", "slow-test", "The suite takes ages. Shave it down."),
        ("implicit", "network-test", "tests/test_legacy_sync.py never passes here. Deal with it."),
        ("contextual", "plain", "Make the failing test pass."),
        ("contextual", "slow-test", "Why did that take so long?"),
        ("contextual", "network-test", "Green please."),
        ("contextual", "uncommitted-test", "Commit this."),
        ("near-miss", "plain", "Explain what unittest.TestCase does, in two sentences."),
        ("near-miss", "plain", "Add a paragraph to the README about the performance budget."),
        ("near-miss", "plain", "Rename the percent parameter of apply_discount to pct."),
        ("near-miss", "plain", "Print tests/test_calc.py."),
    ],
    "docs": [
        ("explicit", "plain", "Create documentation for the inventory package."),
        ("explicit", "docs", "Build the docs."),
        ("explicit", "docs", "Review the docs in docs/."),
        ("explicit", "docs", "Compare docs/usage.md and docs/usage-draft.md."),
        ("explicit", "docs", "Compress docs/usage.md."),
        ("explicit", "uncommitted-docs", "Commit the docs changes."),
        ("implicit", "plain", "Write up how to use this repository for a new contributor."),
        ("implicit", "docs", "The README is out of date. Rewrite it."),
        ("implicit", "docs", "Merge the two usage notes into one."),
        ("implicit", "docs", "Shorten docs/usage.md by half without losing facts."),
        ("implicit", "docs", "Check the docs for mistakes against the code."),
        ("implicit", "plain", "Document export_json."),
        ("contextual", "uncommitted-docs", "Commit this."),
        ("contextual", "docs", "The README mentions CSV. Does the rest of the documentation agree?"),
        ("contextual", "docs", "Tidy the notes."),
        ("contextual", "roadmap", "Write the pieces of documentation the roadmap implies."),
        ("near-miss", "plain", "Add a docstring to total_price."),
        ("near-miss", "plain", "Explain what the README says about the performance budget. Just answer."),
        ("near-miss", "plain", "Add a one-line comment above apply_discount saying the percent is clamped."),
        ("near-miss", "plain", "What is the Markdown syntax for a table?"),
    ],
}


def build() -> list[dict]:
    scenarios = []
    for skill in SKILLS:
        counts: dict[str, int] = {}
        for kind, setup, prompt in PROMPTS[skill]:
            counts[kind] = counts.get(kind, 0) + 1
            scenarios.append({
                "id": f"trig-{skill}-{kind.replace('-', '')}-{counts[kind]}",
                "experiment": "phase3-trigger",
                "unit": f"organic load of {skill} on a {kind} prompt",
                "skill": skill,
                "kind": kind,
                "setup": SETUPS[setup],
                "arms": [ARM],
                "prompt": prompt,
                "checks": {},
                # 1 when a tool call read skill://<name> or the skill's file path; a second count beside
                # `skills_read`, which matches only skill:// text anywhere in the output.
                "metrics": {"read_by_path": (
                    "grep -h '\"tool_execution_start\"' \"$RUN/out.jsonl\" | "
                    f"grep -Eq 'skill://{skill}|skills/(shared-)?{skill}/' && echo 1 || echo 0")},
            })
    return scenarios


SCENARIOS3_TRIGGER = build()
