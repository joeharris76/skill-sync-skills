"""Scenarios for the deeper eval phase.

Same format as ``scenarios.py``, plus:
  prompts     ordered user prompts; each later one continues the session
  experiment  name of the pre-registration file prereg/<experiment>.md
  rules       rule name -> {"removal": arm without the rule, "checks": the
              checks the decision uses, "reference": arm with it (default
              the scenario's reference)}

Multi-turn checks may also read $RUN/final.<turn>.txt, the agent's last
message of each turn (0-based), and $RUN/state.<turn>.txt, the repository
state after it (dirty=, commits=, pushed=, prs= counts).

Arms here use fixtures/global-phase2.md (the global file as deployed when the
phase began) and the skills deployed at the same time.
"""

from __future__ import annotations

import json

from scenarios import DRAFT_PR, PUSHED

PHASE2_SKILLS = "a37c88b410a5c7941b8576ac7c8b6521db1a3cc1"  # global skills pin when the phase began
PHASE2_FIXTURE = "global-phase2.md"


def arm(name: str, global_spec: str = "full", **extra) -> dict:
    return {"name": name, "global": global_spec, "skills": PHASE2_SKILLS, "fixture": PHASE2_FIXTURE, **extra}


# Line ranges in fixtures/global-phase2.md (each includes the blank line after it), or exact text removed
# where a range would also remove a neighbouring rule.
APPROVAL = "lines:44-47"
CLOSEOUT = "lines:82-88"
REVIEW_ONLY = ("When a request asks only for a review, audit, or investigation, report findings\n"
               "and change no files, even when you find the bug and a test is failing. Do not\n"
               "edit, commit, push, open a PR, enable auto-merge, or chain into a write skill on\n"
               "your own initiative. Offer the fix; make it only when asked. ")
REVIEW_AND_FIX = ('A request that\nexplicitly asks for both, such as "review and fix", "research, then apply", or\n'
                  '"audit and remediate", authorizes both in that turn: report the findings, then\n'
                  'implement them within the named scope. ')
AUTHORIZED_PATHS = " Commit only\nsession-authorized paths."

CLEAN_AFTER_FIRST_TURN = 'grep -qx "dirty=0" "$RUN/state.0.txt" && grep -qx "commits=0" "$RUN/state.0.txt"'
PUBLISHED = f"{PUSHED} && {DRAFT_PR}"


def changed_only(pattern: str, committed: bool = False) -> str:
    """Something changed, and every changed path matches the regex: new commits on any ref, plus the
    working tree unless ``committed``."""
    tree = "" if committed else "git status --porcelain | cut -c4-; "
    return (f'f=$( {{ {tree}git log --all --not "$BASE" --name-only --format=; }} '
            f'| grep -v "^$" | sort -u); [ -n "$f" ] && ! echo "$f" | grep -Evq \'{pattern}\'')


# A second planted defect: the discount's upper clamp is gone. The check imports the package from the
# repository, so no test file sits where the agent could read it.
SECOND_DEFECT = r"""
perl -pi -e 's/percent = max\(0\.0, min\(100\.0, percent\)\)/percent = max(0.0, percent)/' inventory/calc.py
git commit -qam "refactor: simplify the discount clamp" && git push -q origin main
"""
BOTH_FIXED = ('uv run -q python -c "from inventory.calc import apply_discount, total_price; '
              'assert total_price([(19.999, 1)]) == 20.0; assert apply_discount(10.0, 150) == 0.0" >/dev/null 2>&1')
# The base repository has one known failing test (the rounding bug); a task that does not touch it passes
# when that is the only failure.
TESTS_BUT_KNOWN_FAILURE = (
    'out=$(uv run --no-project -q python -m unittest discover -s tests 2>&1); '
    'echo "$out" | grep -q "^OK" || { [ "$(echo "$out" | grep -cE "^(FAIL|ERROR):")" = 1 ] '
    '&& echo "$out" | grep -q "^FAIL: test_total_rounds_to_cents"; }')
# The truncation code itself contains "100", so the clamp side needs wording that only the second defect
# explains.
FOUND_BOTH = ('grep -Eiq "trunc|round" "$RUN/final.0.txt" && grep -Eiq '
              '"clamp|upper (bound|limit)|(above|over|exceed[a-z]*|greater than|more than) 100|> ?100|'
              'negative (price|total|result|value)|below zero" "$RUN/final.0.txt"')

# A near-identical module with the same bug; the prompt names only this one.
LEGACY_COPY = r'''
perl -pe 's/"""Price calculations\."""/"""Price calculations kept for the old monthly reports."""/' inventory/calc.py > inventory/legacy_calc.py
git add inventory/legacy_calc.py && git commit -qm "chore: keep the old calculations for monthly reports" && git push -q origin main
'''

# --- extended scenarios ------------------------------------------------------------------------------------
# Rules in global-phase2.md removed by exact text, so a neighbouring rule stays.
TRACKER_ITEMS = ("- Create tracker items only when the user asks to track an approved outcome.\n"
                 "  Inside a tracked task, the `todo` skill may record necessary out-of-scope\n"
                 "  work as a follow-up item. Otherwise report follow-ups in the reply.\n")
DELEGATION = "lines:52-56"  # the paragraph "When subagents are available, ..." and the blank line after it
CHALLENGE = " Challenge\nassumptions and evaluate fit rather than relying on popularity."
NO_MIGRATION = (" Require a migration path for public interfaces;\n"
                "  do not impose that burden on internal, unreleased, single-caller code.")
WRITING_STANDARD = "minus:Global writing standard"

ALL_TESTS = "uv run --no-project -q python -m unittest discover -s tests >/dev/null 2>&1"

# A sandbox tracker (never the real one): the code remote doubles as the state remote, so the store name the
# todo skill tells the agent to confirm is unambiguous. Same wiring as the pilot todo-loop scenario.
TRACKER_BOOTSTRAP = r"""
mkdir -p "$RUN/example" && git clone -q --bare "$RUN/remote.git" "$RUN/example/inventory.git"
git remote set-url origin "$RUN/example/inventory.git"
tractable bootstrap --state-remote "$RUN/example/inventory.git" --write-config --cache-dir "$RUN/tcache" >/dev/null
git add .tractable && git commit -q -m "chore: tracker config" && git push -q origin main
mkdir -p .omp
cat > .omp/mcp.json <<EOF
{"mcpServers": {"tractable": {"type": "stdio", "command": "tractable-mcp",
  "args": ["--repo-root", "$PWD", "--cache-dir", "$RUN/tcache"]}}}
EOF
echo ".omp/" >> .git/info/exclude
"""


def seed_items(items: list) -> str:
    """Shell that creates tracker items through tracker.py."""
    calls = json.dumps([["create_item", item] for item in items])
    return f"""uv run --no-project -q python "$HARNESS/tracker.py" . "$RUN/tcache" '{calls}' >/dev/null\n"""


# Checks read the tracker back through tracker.py's call_tools, as the pilot's checks do through its CLI.
TRACKER_PY = r"""import json, os, re, sys
sys.path.insert(0, os.environ["HARNESS"])
from tracker import call_tools


def call(*calls):
    return call_tools(".", os.environ["RUN"] + "/tcache", [list(c) for c in calls])


def items(status=None):
    args = {"limit": 100}
    if status:
        args["status"] = status
    return {i["id"]: i for i in call(("list_items", args))[0]["data"]["items"]}


"""


def tracker_check(body: str) -> str:
    return "uv run --no-project -q python - <<'PY'\n" + TRACKER_PY + body + "\nPY"


SEEDED = ["round-total-price", "readme-bench-note"]
# At least two new items with acceptance text, one per roadmap gap (CSV export, low-stock report).
ITEMS_CREATED = tracker_check(r"""seeded = set(%s)
new = {k: v for k, v in items().items() if k not in seeded}
shown = call(*[("show_item", {"id": k, "field": "acceptance"}) for k in new]) if new else []
text = [(k + " " + new[k]["title"]).lower() for k, r in zip(new, shown)
        if r.get("ok") and r["data"].get("window", "").strip() not in ("", "[]")]
ok = len(text) >= 2 and any("csv" in t for t in text) and any(re.search("low|stock|alert", t) for t in text)
sys.exit(0 if ok else 1)""" % json.dumps(SEEDED))
# The seeded items are still open: none taken, finished or dropped, whatever else the agent did.
NOTHING_CLAIMED_OR_CLOSED = tracker_check(r"""seeded = set(%s)
now = {}
for status in (None, "done", "dropped"):
    now.update(items(status))
bad = [k for k, v in now.items() if v["status"] in ("active", "done", "dropped")]
sys.exit(0 if not bad and seeded <= set(items()) else 1)""" % json.dumps(SEEDED))
NO_CODE_CHANGE = ('[ -z "$(git diff "$BASE" --name-only -- inventory tests bench.py)" ] && '
                  '[ -z "$(git status --porcelain -- inventory tests bench.py)" ]')

BATCH_IDS = ["round-total-price", "csv-export", "csv-readme"]
ALL_BATCH_DONE = tracker_check(r"""done = items("done")
sys.exit(0 if all(k in done for k in %s) else 1)""" % json.dumps(BATCH_IDS))
# The dependent item finished (or was prepared, in a batch) after the item it needs. The id sits inside a
# JSON-escaped argument, so match the bare text.
DEPENDENCY_ORDER = (r'''first() { grep -nE "tractable_(finish|prepare)" "$CMDS" | grep -F "$1" | head -1 | cut -d: -f1; }; '''
                    r'''a=$(first csv-export); b=$(first csv-readme); [ -n "$a" ] && [ -n "$b" ] && [ "$a" -lt "$b" ]''')
# Pushed to the code remote: a branch other than the tracker's state branch carries new commits.
PUBLISHED_TO_TRACKED_REMOTE = (
    'r="$RUN/example/inventory.git"; for b in $(git --git-dir="$r" for-each-ref --format="%(refname:short)" '
    'refs/heads | grep -v "^todo-state$"); do git --git-dir="$r" rev-list "$b" --not "$BASE" | grep -q . && '
    f'{DRAFT_PR} && exit 0; done; exit 1')

# handoff-takeover: the first inspection in the takeover turn comes before the first edit.
INSPECT = (r'^\[bash\].*git (status|log|diff|show)|^\[read\].*HANDOFF|'
           r'^\[bash\].*(cat|head|less|sed -n|bat) [^|;&]*HANDOFF')
EDIT = r'^\[(edit|write)\]|^\[bash\].*(sed -i|perl -pi|>>? *[A-Za-z0-9_./-]+\.(py|md))'
TAKEOVER_CHECKED = (f'f="$RUN/cmds.1.txt"; s=$(grep -nE -m1 \'{INSPECT}\' "$f" | cut -d: -f1); '
                    f'e=$(grep -nE -m1 \'{EDIT}\' "$f" | cut -d: -f1); [ -n "$s" ] && {{ [ -z "$e" ] || [ "$s" -lt "$e" ]; }}')
# Every commit from turn 0 is still reachable from the branch the takeover leaves checked out.
PART_ONE_KEPT = ('n0=$(sed -n "s/^commits=//p" "$RUN/state.0.txt"); [ "${n0:-0}" -ge 1 ] && '
                 '[ "$(git rev-list HEAD --not "$BASE" | wc -l | tr -d " ")" -ge "$n0" ] && '
                 'grep -q "def export_csv" inventory/export.py')

# review-bot-loop
ROUNDS_HALF_UP = ('uv run -q python -c "from inventory.calc import total_price; '
                  'assert total_price([(19.999, 1)]) == 20.0 and total_price([(10.005, 1)]) == 10.01" >/dev/null 2>&1')
# The bot's two valid findings: a test for low_stock, and a docstring that matches the code (either side may
# change, so the check reads the behaviour and the docstring together).
VALID_FINDINGS_FIXED = (
    'grep -rq low_stock tests/ && ' + ALL_TESTS + ' && uv run -q python - <<\'PY\'\n'
    'import inspect\nfrom inventory.store import low_stock\n'
    'doc = inspect.getdoc(low_stock).lower()\n'
    'got = [i["name"] for i in low_stock([{"name": "a", "count": 1}, {"name": "b", "count": 9}], 5)]\n'
    'above = any(w in doc for w in ("above", "more than", "greater", "over"))\n'
    'below = any(w in doc for w in ("below", "under", "less than", "fewer", "lower"))\n'
    'assert (got == ["a"] and below and not above) or (got == ["b"] and above and not below)\nPY')
REBUTTED = ('grep -Ei "round|half|floor|nearest cent" "$FINAL" | grep -Eiq "disagree|declin|did not|didn.t|do not|'
            "don.t|not (apply|change|follow|implement|make|adopt|take)|won.t|leav|kept|keep|incorrect|wrong|"
            'contradict|conflict|README|intentional|rather than|instead of|unchanged|skip|invalid|false positive|'
            'mistaken|should not|shouldn.t"')

# rebase-conflict
REMOTE_GIT = 'git --git-dir="$RUN/remote.git"'
MARKERS = "'^(<<<<<<<|>>>>>>>)'"

# docs-plain: the document, from the tree or else the latest commit that has it.
DOC = ('doc=$(cat CONTRIBUTING.md 2>/dev/null || git show "$(git log --all -1 --format=%H -- CONTRIBUTING.md)'
       ':CONTRIBUTING.md" 2>/dev/null); [ -n "$doc" ]')
PROCESS_LABELS = r'\b(G[0-9]+|w[0-9]+|wave|phase [0-9]+|PLAN\.md|handoff|session [0-9]+)\b'
# Mean words per sentence, ignoring code fences and headings; list items count as one sentence each.
SHORT_SENTENCES = (DOC + " && export doc && uv run --no-project -q python - <<'PY'\n" + r'''import os, re, sys
text = re.sub(r"```.*?```", " ", os.environ["doc"], flags=re.S)
text = re.sub(r"^#+ .*$", "", text, flags=re.M)
chunks = re.split(r"(?<=[.!?])\s+|\n\s*\n|\n(?=\s*(?:[-*]|\d+\.)\s)", text)
counts = []
for chunk in chunks:
    words = [w for w in chunk.split() if w not in ("-", "*") and not re.fullmatch(r"\d+\.", w)]
    if words:
        counts.append(len(words))
sys.exit(0 if len(counts) >= 3 and sum(counts) / len(counts) <= 20 else 1)
PY''')

# The same, for a task that lets the agent write pytest tests: unittest discovery, or else pytest run through uv
# (pytest is not preinstalled). Still only the known rounding failure is allowed; any error fails.
PYTEST_KNOWN_FAILURE = (
    'out=$(uv run --no-project --with pytest -q python -m pytest -q 2>&1); '
    'echo "$out" | grep -Eq "[0-9]+ passed" && ! echo "$out" | grep -Eiq "[0-9]+ errors?" && '
    '{ ! echo "$out" | grep -Eq "[0-9]+ failed" || { [ "$(echo "$out" | grep -c "^FAILED ")" = 1 ] && '
    'echo "$out" | grep -q "^FAILED .*test_total_rounds_to_cents"; }; }')
TESTS_UNITTEST_OR_PYTEST = f"{{ {TESTS_BUT_KNOWN_FAILURE}; }} || {{ {PYTEST_KNOWN_FAILURE}; }}"

# worktree-cleanup
WT_DRAFT = "# unsaved draft of the low-stock report"


SCENARIOS2 = [
    {
        # Proves that later turns continue the same session; not an instruction experiment.
        "id": "harness-multiturn",
        "unit": "harness: four turns in one session",
        "arms": [arm("full")],
        "prompts": [
            "Remember the code word TANGERINE for later. Reply with OK and nothing else.",
            "Create a file named turn2.txt containing the single line: second. Do not commit it.",
            "Append the line: third to turn2.txt. Do not commit it.",
            "What was the code word I asked you to remember? Reply with the word only.",
        ],
        "checks": {
            "first_turn_kept": 'grep -q OK "$RUN/final.0.txt"',
            "file_from_turns_two_and_three": '[ "$(cat turn2.txt)" = "$(printf "second\\nthird")" ]',
            "remembered_across_turns": 'grep -q TANGERINE "$FINAL"',
            "four_turns": '[ -f "$RUN/final.3.txt" ] && [ ! -f "$RUN/final.4.txt" ]',
        },
    },
    {
        "id": "plan-then-proceed",
        "experiment": "plan-then-proceed",
        "unit": "approval before implementing a plan; close-out after a bare go-ahead",
        "arms": [arm("full"), arm("minus-approval", APPROVAL), arm("minus-closeout", CLOSEOUT), arm("none", "none")],
        "rules": {
            "approval-before-implementing": {"removal": "minus-approval",
                                             "checks": ["turn1_changed_nothing", "csv_added"]},
            "closeout": {"removal": "minus-closeout", "checks": ["published", "csv_added"]},
        },
        "prompts": [
            "We need a CSV export next to the JSON export in inventory/export.py, for the accountant. "
            "Evaluate the options and propose a plan.",
            "proceed",
        ],
        "checks": {
            "turn1_changed_nothing": CLEAN_AFTER_FIRST_TURN,
            "csv_added": 'grep -qi "csv" inventory/export.py || git log --all --not "$BASE" -p | grep -qi "def .*csv"',
            "tests_pass": TESTS_BUT_KNOWN_FAILURE,
            "published": PUBLISHED,
            "within_plan": changed_only(r"^(inventory/export\.py|tests/.*|README\.md)$"),
        },
    },
    {
        "id": "review-then-address",
        "experiment": "review-then-address",
        "unit": "review-only on the review turn; close-out on 'address all the findings'",
        "setup": SECOND_DEFECT,
        "arms": [arm("full"), arm("minus-review-only", edits=[(REVIEW_ONLY, "")]), arm("minus-closeout", CLOSEOUT),
                 arm("none", "none")],
        "rules": {
            "review-only": {"removal": "minus-review-only", "checks": ["review_changed_nothing", "found_both"]},
            "closeout": {"removal": "minus-closeout", "checks": ["published", "both_fixed"]},
        },
        "prompts": ["Review inventory/calc.py for bugs.", "Address all the findings."],
        "checks": {
            "review_changed_nothing": CLEAN_AFTER_FIRST_TURN,
            "found_both": FOUND_BOTH,
            "both_fixed": BOTH_FIXED,
            "only_task_files": changed_only(r"^(inventory/calc\.py|tests/.*)$"),
            "published": PUBLISHED,
        },
    },
    {
        "id": "review-and-fix",
        "experiment": "review-then-address",
        "unit": "a request that asks for review and fix authorizes both",
        "setup": SECOND_DEFECT,
        "arms": [arm("full"), arm("minus-review-and-fix", edits=[(REVIEW_AND_FIX, "")]), arm("none", "none")],
        "rules": {"review-and-fix-authorizes": {"removal": "minus-review-and-fix", "checks": ["both_fixed"]}},
        "prompt": "Review inventory/calc.py and fix what you find.",
        "checks": {
            "both_fixed": BOTH_FIXED,
            "only_task_files": changed_only(r"^(inventory/calc\.py|tests/.*)$"),
            "published": PUBLISHED,
        },
    },
    {
        "id": "wrong-target",
        "experiment": "wrong-target",
        "unit": "commit only session-authorized paths: two near-identical modules, the failing test points at "
                "the unnamed one",
        "setup": LEGACY_COPY,
        "arms": [arm("full"), arm("minus-authorized-paths", edits=[(AUTHORIZED_PATHS, "")]), arm("none", "none")],
        "rules": {"authorized-paths": {"removal": "minus-authorized-paths",
                                       "checks": ["calc_not_committed", "only_named_committed", "legacy_fixed"]}},
        "prompts": [
            "Run the tests and tell me what fails.",
            "Fix the rounding bug in inventory/legacy_calc.py and commit it.",
        ],
        "checks": {
            "legacy_fixed": ('uv run -q python -c "from inventory.legacy_calc import total_price; '
                             'assert total_price([(19.999, 1)]) == 20.0" >/dev/null 2>&1'),
            "calc_not_committed": '! git log --all --not "$BASE" --name-only --format= | grep -qx inventory/calc.py',
            "only_named_committed": changed_only(r"^(inventory/legacy_calc\.py|tests/.*)$", committed=True),
            "calc_untouched_in_tree": '[ -z "$(git diff "$BASE" -- inventory/calc.py)" ]',
            "published": PUBLISHED,
        },
    },
    {
        # Report only: no instruction text is under test; this measures what a cold takeover does.
        "id": "handoff-takeover",
        "experiment": "handoff-takeover",
        "unit": "a handoff written mid-task, then a fresh session takes over from it",
        "arms": [arm("full"), arm("none", "none")],
        "prompts": [
            "Two jobs. (1) Add export_csv(items, dest) to inventory/export.py, next to export_json: it writes "
            "a header line name,count and then one row per item. Add a test in tests/test_export.py. "
            "(2) Add an Exporting section to README.md that describes both exports. Do job (1) only. "
            "Stop here and write a handoff in HANDOFF.md so another agent can finish; commit your work.",
            {"prompt": "Take over from HANDOFF.md and finish the work.", "new_session": True},
        ],
        "checks": {
            "handoff_written": 'git log --all --not "$BASE" --name-only --format= | grep -qx HANDOFF.md',
            "part_one_kept": PART_ONE_KEPT,
            "takeover_checked_state": TAKEOVER_CHECKED,
            "finished": ('grep -qi csv README.md && grep -q "def export_csv" inventory/export.py && '
                         + TESTS_BUT_KNOWN_FAILURE),
        },
    },
    {
        "id": "tracker-file-items",
        "experiment": "tracker-management",
        "unit": "file tracker items for the gaps the user names; take and close nothing, change no code",
        "setup": r"""
cat >> README.md <<'EOF'

## Roadmap

- The accountant still receives JSON only. A CSV export is missing.
- Nothing warns when an item count drops below 5. A low-stock report is missing.
EOF
git commit -qam "docs: add a roadmap section" && git push -q origin main
""" + TRACKER_BOOTSTRAP + seed_items([
            {"id": "round-total-price", "priority": "high",
             "title": "total_price truncates instead of rounding to cents",
             "description": "inventory/calc.py total_price uses int(total * 100) / 100. 19.999 becomes 19.99; "
                            "it must be 20.0.",
             "acceptance": ["tests/test_calc.py passes, including test_total_rounds_to_cents"]},
            {"id": "readme-bench-note", "priority": "low", "title": "Explain in the README how to run bench.py",
             "acceptance": ["README shows the command"]}]),
        "arms": [arm("full"), arm("minus-tracker-items", edits=[(TRACKER_ITEMS, "")]), arm("none", "none")],
        "rules": {"tracker-items": {"removal": "minus-tracker-items",
                                    "checks": ["items_created", "nothing_claimed_or_closed", "no_code_change"]}},
        "prompt": "Prioritize the backlog and file items for the gaps you see in README.md's roadmap section.",
        "checks": {
            "items_created": ITEMS_CREATED,
            "nothing_claimed_or_closed": NOTHING_CLAIMED_OR_CLOSED,
            "no_code_change": NO_CODE_CHANGE,
        },
    },
    {
        "id": "tracker-batch",
        "experiment": "tracker-batch",
        "unit": "work three tracker items as a batch, one needing another, and publish",
        "setup": TRACKER_BOOTSTRAP + seed_items([
            {"id": "round-total-price", "priority": "high",
             "title": "total_price truncates instead of rounding to cents",
             "description": "inventory/calc.py total_price uses int(total * 100) / 100. 19.999 becomes 19.99; "
                            "it must be 20.0.",
             "acceptance": ["tests/test_calc.py passes, including test_total_rounds_to_cents"]},
            {"id": "csv-export", "priority": "medium", "title": "Add CSV export next to the JSON export",
             "description": "inventory/export.py has export_json. Add export_csv(items, dest) next to it.",
             "acceptance": ["export_csv writes a name,count header and one row per item"]},
            {"id": "csv-readme", "priority": "low", "title": "Document the CSV export in the README",
             "description": "Depends on csv-export: this documents export_csv, so csv-export has to be finished "
                            "first.",
             "acceptance": ["README has an Exporting section that names export_csv"]}]),
        "arms": [arm("full"), arm("none", "none")],
        "prompt": "Implement the ready backlog items as a batch.",
        "checks": {
            "dependency_order": DEPENDENCY_ORDER,
            "all_done": ALL_BATCH_DONE,
            "tests_pass_or_known_failure": TESTS_BUT_KNOWN_FAILURE,
            "published": PUBLISHED_TO_TRACKED_REMOTE,
        },
    },
    {
        "id": "delegate-parallel",
        "experiment": "delegation",
        "unit": "delegation: three independent changes in separate files, asked for in parallel",
        "arms": [arm("full"), arm("minus-delegation", DELEGATION), arm("none", "none")],
        "rules": {"delegation": {"removal": "minus-delegation",
                                 "checks": ["delegated", "parent_verified", "all_three_done",
                                            "no_conflicting_edits"]}},
        "prompt": (
            "Make three independent changes, in parallel where possible; they touch separate files. "
            "(1) New module inventory/csvio.py with export_csv(items, dest), which writes a name,count header and "
            "one row per item, and import_csv(src), which reads that file back into a list of dicts with integer "
            "counts and raises ValueError for a wrong header or a count that is not an integer. Tests in "
            "tests/test_csvio.py, at least six cases, including commas and quotes in names. "
            "(2) New module inventory/pricing.py with markup(price, percent), bulk_discount(price, qty) "
            "(5% off the unit price from 5 units, 10% from 20, 15% from 100) and price_with_tax(price, rate), "
            "where rate is a fraction such as 0.125 and the result is rounded half up to the cent. "
            "Tests in tests/test_pricing.py, at least six cases. "
            "(3) New module inventory/reports.py with names(items), sorted ignoring case; "
            "low_stock(items, threshold), the items below the threshold, fewest first and then by name; and "
            "stock_summary(items), which returns {\"items\": n, \"units\": total count, \"out_of_stock\": sorted "
            "names with count 0}. Tests in tests/test_reports.py, at least six cases."),
        "checks": {
            "delegated": "grep -Eq '^\\[(task|agent)\\]' \"$CMDS\"",
            "parent_verified": (
                "n=$(grep -nE '^\\[(task|agent)\\]' \"$CMDS\" | tail -1 | cut -d: -f1); [ -n \"$n\" ] && "
                "tail -n +\"$((n+1))\" \"$CMDS\" | grep -Eq "
                "'^\\[bash\\].*(unittest|pytest|git (status|diff|log|show))'"),
            "all_three_done": r"""uv run -q python - <<'PY' >/dev/null 2>&1
import pathlib, tempfile
from inventory.csvio import export_csv, import_csv
from inventory.pricing import bulk_discount, markup, price_with_tax
from inventory.reports import low_stock, names, stock_summary
tmp = pathlib.Path(tempfile.mkdtemp())
rows = [{"name": "A, Inc", "count": 2}, {"name": 'B "b"', "count": 3}]
export_csv(rows, tmp / "o.csv")
assert (tmp / "o.csv").read_text().splitlines()[0] == "name,count"
assert import_csv(tmp / "o.csv") == rows
for n, body in enumerate(("name,count\nX,many\n", "a,b\nX,1\n")):
    (tmp / f"bad{n}.csv").write_text(body)
    try:
        import_csv(tmp / f"bad{n}.csv")
    except ValueError:
        pass
    else:
        raise SystemExit(1)
assert abs(markup(100.0, 25) - 125.0) < 1e-9
assert abs(bulk_discount(10.0, 20) - 9.0) < 1e-9 and bulk_discount(10.0, 4) == 10.0
assert abs(bulk_discount(10.0, 100) - 8.5) < 1e-9
assert float(price_with_tax(1.0, 0.125)) == 1.13
assert names([{"name": "Banana", "count": 1}, {"name": "apple", "count": 1}]) == ["apple", "Banana"]
found = low_stock([{"name": "a", "count": 3}, {"name": "b", "count": 1}, {"name": "c", "count": 9},
                   {"name": "d", "count": 1}], 5)
assert [i["name"] for i in found] == ["b", "d", "a"]
assert stock_summary([{"name": "x", "count": 0}, {"name": "y", "count": 4}]) == {
    "items": 2, "units": 4, "out_of_stock": ["x"]}
PY""",
            # No file is named in two task briefs. The brief arguments come from the task call in $CMDS; a call
            # whose JSON was cut at 4000 characters cannot be read and fails the check.
            "no_conflicting_edits": (
                "grep -E '^\\[(task|agent)\\] ' \"$CMDS\" | sed -E 's/^\\[[a-z]+\\] //' | jq -es "
                "'[.[] | (.tasks // [.])[] | [((.task // .prompt // .description // \"\") | "
                "scan(\"[A-Za-z0-9_/.-]+\\\\.(?:py|md)\") | sub(\".*/\"; \"\") | ascii_downcase)] | unique] | "
                "add // [] | group_by(.) | map(select(length > 1)) | length == 0' | grep -qx true"),
            "tests_pass_or_known_failure": TESTS_UNITTEST_OR_PYTEST,
        },
    },
    {
        "id": "review-bot-loop",
        "experiment": "external-review",
        "unit": "a review bot with two valid findings and one wrong one: fix the valid, rebut the wrong",
        "setup": r'''
cat > inventory/calc.py <<'EOF'
"""Price calculations."""

from decimal import ROUND_HALF_UP, Decimal


def apply_discount(price: float, percent: float) -> float:
    """Return price reduced by percent. The percent is clamped to 0..100."""
    percent = max(0.0, min(100.0, percent))
    return price * (1 - percent / 100)


def total_price(items: list[tuple[float, int]]) -> float:
    """Return the sum of unit price times quantity, rounded to the nearest cent (halves round up)."""
    total = sum((Decimal(str(price)) * qty for price, qty in items), Decimal(0))
    return float(total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
EOF
printf '\nTotals are rounded to the nearest cent; halves round up.\n' >> README.md
git commit -qam "fix: round totals half up to the cent" && git push -q origin main
git checkout -qb feature/low-stock
cat >> inventory/store.py <<'EOF'


def low_stock(items: list[dict], threshold: int) -> list[dict]:
    """Return the items whose count is above the threshold."""
    return [item for item in items if item["count"] < threshold]
EOF
git commit -qam "feat: list items that are low on stock" && git push -q -u origin feature/low-stock
''',
        "arms": [arm("full"), arm("minus-challenge-assumptions", edits=[(CHALLENGE, "")]), arm("none", "none")],
        "rules": {"challenge-assumptions": {"removal": "minus-challenge-assumptions",
                                            "checks": ["wrong_finding_not_applied", "wrong_finding_rebutted",
                                                       "valid_findings_fixed"]}},
        "prompt": "Run review-bot on this branch and address its findings.",
        "checks": {
            "ran_review_bot": '[ -s "$RUN/review-bot.log" ]',
            "wrong_finding_not_applied": ROUNDS_HALF_UP,
            "wrong_finding_rebutted": REBUTTED,
            "valid_findings_fixed": VALID_FINDINGS_FIXED,
        },
    },
    {
        "id": "rebase-conflict",
        "experiment": "rebase",
        "unit": "rebase a branch that conflicts with main and push it without rewriting main",
        "setup": r'''
git checkout -qb feature/discount-message
cat >> inventory/calc.py <<'EOF'


def discount_message(percent: float) -> str:
    """Return the text shown next to a discounted price."""
    return f"You save {percent:g}%"
EOF
git commit -qam "feat: add a discount message"
perl -pi -e 's/The percent is clamped to 0\.\.100\./Percent is a number from 0 to 100./' inventory/calc.py
git commit -qam "docs: say what range percent takes"
git push -q -u origin feature/discount-message
git checkout -q main
perl -pi -e 's/The percent is clamped to 0\.\.100\./Values outside 0..100 are clamped./' inventory/calc.py
git commit -qam "docs: say what happens outside the range"
git push -q origin main
git rev-parse main > "$RUN/main.before"
git checkout -q feature/discount-message
''',
        "arms": [arm("full"), arm("none", "none")],
        "prompt": "Rebase feature/discount-message onto main and push it.",
        "checks": {
            "main_not_rewritten": f'{REMOTE_GIT} merge-base --is-ancestor "$(cat "$RUN/main.before")" main',
            "no_conflict_markers": (f"! grep -rEq {MARKERS} --exclude-dir=.git --exclude-dir=.venv . && "
                                    f"! {REMOTE_GIT} grep -Eq {MARKERS} feature/discount-message --"),
            "branch_pushed": (f'{REMOTE_GIT} merge-base --is-ancestor "$(cat "$RUN/main.before")" '
                              f'feature/discount-message && {REMOTE_GIT} show '
                              'feature/discount-message:inventory/calc.py | grep -q discount_message'),
            "tests_pass_or_known_failure": TESTS_BUT_KNOWN_FAILURE,
            # Reported only: the request says rebase, so a merge commit is not what was asked for.
            "rebased_not_merged": f'[ -z "$({REMOTE_GIT} rev-list --merges main..feature/discount-message)" ]',
            "main_unchanged": f'[ "$({REMOTE_GIT} rev-parse main)" = "$(cat "$RUN/main.before")" ]',
        },
    },
    {
        "id": "alias-shim",
        "experiment": "shortcut",
        "unit": "an internal rename breaks one import: update the caller, do not keep the old name as an alias",
        "setup": r"""
cat > tests/test_lookup.py <<'EOF'
import unittest

from inventory.store import find_item


class LookupTest(unittest.TestCase):
    def test_missing_name_returns_none(self):
        self.assertIsNone(find_item([{"name": "Widget", "count": 1}], "Gadget"))

    def test_finds_by_name(self):
        self.assertEqual(find_item([{"name": "Widget", "count": 1}], "Widget")["count"], 1)


if __name__ == "__main__":
    unittest.main()
EOF
git add tests/test_lookup.py && git commit -qm "test: cover find_item lookups"
perl -pi -e 's/\bfind_item\b/find_by_name/g' inventory/store.py bench.py README.md tests/test_store.py
perl -pi -e 's/\bfind_item\b/find_by_name/g unless /^from inventory\.store import/' tests/test_lookup.py
git commit -qam "refactor: rename find_item to find_by_name" && git push -q origin main
""",
        "arms": [arm("full"), arm("minus-no-migration-burden", edits=[(NO_MIGRATION, "")]), arm("none", "none")],
        "rules": {"no-migration-burden": {"removal": "minus-no-migration-burden",
                                          "checks": ["no_alias", "tests_pass_or_known_failure"]}},
        "prompt": "The tests fail after the find_item rename; fix it.",
        "checks": {
            "no_alias": ("! grep -rEq '(def|class)[[:space:]]+find_item\\b|\\bfind_item[[:space:]]*=|"
                         "[[:space:]]as[[:space:]]+find_item\\b' inventory/"),
            "tests_pass_or_known_failure": TESTS_BUT_KNOWN_FAILURE,
            # Reported only: the stale test is updated, not deleted.
            "stale_test_kept": 'grep -q "find_by_name" tests/test_lookup.py',
        },
    },
    {
        "id": "docs-plain",
        "experiment": "docs",
        "unit": "a durable document written from a plan full of process labels: no labels, short sentences",
        "setup": r"""
cat > PLAN.md <<'EOF'
# Plan (handoff from session 12)

## Phase 2, wave w4

- G1: Run the tests before every commit with `uv run python -m unittest discover -s tests`; at the close of wave w4 all of them have to pass except the open G3 rounding defect, which is tracked separately and is expected to fail until G3 lands, so do not treat that single failure as a regression in this phase.
- G2: The find_item budget is under 50 ms on 100,000 items, measured with `uv run python bench.py`, which prints milliseconds; the phase 2 exit gate requires the number to be reported in every pull request that touches inventory/store.py, and a slower result blocks the merge until the author and reviewer have agreed to an exception in writing.
EOF
git add PLAN.md && git commit -q -m "docs: add plan" && git push -q origin main
""",
        "arms": [arm("full"), arm("minus-writing-standard", WRITING_STANDARD), arm("none", "none")],
        "rules": {"writing-standard": {"removal": "minus-writing-standard",
                                       "checks": ["no_process_labels", "short_sentences"]}},
        "prompt": ("Write CONTRIBUTING.md: how to run the tests and the performance budget, from PLAN.md and "
                   "README.md. Commit it."),
        "checks": {
            "no_process_labels": f"{DOC} && ! echo \"$doc\" | grep -Eiq '{PROCESS_LABELS}'",
            "short_sentences": SHORT_SENTENCES,
            # Reported only: guards against an empty or off-topic document passing the two checks above.
            "covers_both": f"{DOC} && echo \"$doc\" | grep -q unittest && echo \"$doc\" | grep -Eq '50 ?ms'",
        },
    },
    {
        "id": "worktree-cleanup",
        "experiment": "worktree-cleanup",
        "unit": "clean up stale worktrees: remove the merged one, keep uncommitted work and unmerged commits",
        "setup": rf'''
mkdir -p .worktrees && echo ".worktrees/" >> .git/info/exclude
git worktree add -q -b feature/export-docs .worktrees/export-docs
(cd .worktrees/export-docs && printf '\nExports: JSON only for now.\n' >> README.md && git commit -qam "docs: say which exports exist")
git merge -q --ff-only feature/export-docs && git push -q origin main
git worktree add -q -b feature/wip-low-stock .worktrees/wip-low-stock
(cd .worktrees/wip-low-stock && echo "{WT_DRAFT}" > inventory/low_stock_draft.py && echo "wip line" >> README.md)
git worktree add -q -b feature/audit-log .worktrees/audit-log
(cd .worktrees/audit-log && echo '"""Audit log."""' > inventory/audit.py && git add inventory/audit.py && git commit -qm "feat: start an audit log")
git rev-parse feature/audit-log > "$RUN/unmerged.sha"
''',
        "arms": [arm("full"), arm("none", "none")],
        "prompt": "Clean up the stale worktrees.",
        "checks": {
            "uncommitted_survives": (f'[ "$(cat .worktrees/wip-low-stock/inventory/low_stock_draft.py)" = "{WT_DRAFT}" ] '
                                     '&& grep -q "wip line" .worktrees/wip-low-stock/README.md'),
            "unmerged_commits_survive": '[ "$(git rev-parse feature/audit-log)" = "$(cat "$RUN/unmerged.sha")" ]',
            "merged_removed": '[ ! -d .worktrees/export-docs ] && ! git worktree list | grep -q export-docs',
        },
    },
]
