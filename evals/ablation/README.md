# Instruction ablation eval

Measures whether a piece of instruction text changes what an agent does. The
same task runs several times with the text present and several times with it
removed; checks on the resulting repository show the difference.

## How a session runs

`run.py` starts a headless `omp` session (`omp -p --mode json`) for each
scenario, arm and repeat:

- The working directory is a new repository under `/tmp/omp-ablation/`, built
  by `base_setup.sh` plus the scenario's own setup. Its `origin` is a local
  bare repository. The directory name is random, so it does not reveal the arm.
- A config overlay turns off every discovery provider that would load the
  user's real instruction files and skills. The arm's global text is loaded as
  `GLOBAL.md` through `contextFiles.extra`; the arm's skills come from
  `git archive <revision> skills` through `skills.customDirectories`.
- `GIT_CONFIG_GLOBAL` points at a sandbox file, and `shims/gh` stands in for
  the GitHub CLI: it records each call and answers from canned files. A session
  cannot push to a real remote or change anything on GitHub.
- Afterwards each check in the scenario runs as a shell command in the sandbox.
  A check passes when it exits 0.

A filesystem profile (`sandbox-exec`, macOS) also hides the user's own agent
files and projects from the session, so it cannot find another copy of a skill.

Sessions run with `--auto-approve` as the current user. The sandbox limits Git
and GitHub side effects and those reads only; scenario prompts must keep the
work inside the repository.

## Replaying real turns

`replay.py` reruns one real user message from a recorded omp session under an
arm, with the session's own history in front of it:

```sh
uv run --no-project python evals/ablation/replay.py list --session <session.jsonl>
uv run --no-project python evals/ablation/replay.py run --out <dir> --session <session.jsonl> --turn 3 --turn 5 \
    [--global full|none|minus:<heading>|...] [--skills <rev>] [--check-file checks.json] [--smoke]
```

Turns count the session's user messages from 0; `list` shows which ones can be
rebuilt. A replay copies the session file into a new sandbox, cuts it just
before the chosen message, rewrites the recorded working directory and every
absolute path under the original repository to the sandbox repository (sibling
directories such as `<repo>.wt-x` are left alone), and resumes the copy with
`omp --resume` under the usual overlay, the deny profile and the arm's text.
The profile also hides `~/.omp/agent/sessions`, which holds the later turns.
The original session file and repository are never written; each result
records a status, tracked-file modification-time and session-file hash of the
originals from before and after (`replay.isolation`).

The repository is rebuilt from a local bare cache of the GitHub remote under
`/tmp/omp-ablation/cache/` (read-only to the session), never from the user's
clone. Its top level comes from `git rev-parse --show-toplevel`; a session
recorded in a subdirectory resumes in the same subdirectory. Each run gets a
private local `origin`, pushes to GitHub URLs are rewritten to an invalid
address, `SSH_AUTH_SOCK` is unset, and the deny profile hides `~/.ssh`, the
original repository and the folder holding the original session file.

A derived commit is read from the session itself and never guessed or taken
from timestamps (a pinned one is chosen by you; see below). Only two kinds of bash call count as showing HEAD, and only when
they ran inside the repository: `git rev-parse [--short] HEAD`, and `git log`
with nothing but `-N`, `-n N`, `--oneline`, `--format` and `--no-decorate`,
optionally piped to `head`. Anything that may have moved HEAD or changed the
working tree afterwards clears the commit: a HEAD-moving git command (commit,
pull, checkout, merge, reset, `gh pr merge`, ...) that ran in the repository,
ran where the directory cannot be told, or names the repository anywhere; any
`edit`, `write` or `ast_edit` whose path (read from the `edit` header, relative
to the session directory) lies inside the repository or cannot be read; and any
tool that may run commands (`task`, `eval`, `exec`, MCP tools, ...). Only
read-only tools (`read`, `grep`, `glob`, `find`, `web_search`, `todo`, `ask`,
`wait`) leave it alone. If no commit is left, or it is missing from the remote
or newer than the turn, the turn is counted as unrebuildable
(`<dir>/unrebuildable/`) and skipped. This is strict: very few real turns
qualify. Edits made by shell commands (`sed -i`, redirects) are not detected,
and uncommitted work is not restored, so a replay tests the committed state.
Earlier turns of the history were produced under the old text, and only the
next turn is tested.

**Derived or pinned commit.** By default the commit is derived as above and
each result records `commit_source: "derived"`. When derivation refuses a turn,
pin the commit yourself: `replay.py run ... --commit <sha> --commit-evidence
"<why this is the state at the turn>"`. The result then records `commit_source:
"pinned"` and the evidence text, and a pinned commit dated after the turn is
refused. `replay.py locate --session F [--turn N]` proposes a commit without
applying it: it takes the last branch the session's own output names (`On
branch`, `git status -sb`, `git branch --show-current`, a commit summary line,
`checkout -b`, `worktree add -b`) or, failing that kind of output, the name of
a `<repo>.wt-<name>` worktree directory a command ran in. Output of a command
that changes directory after its start or uses `git -C` is ignored, and branch
output from a sibling worktree counts only when the session's own directory is
that worktree. It refreshes the bare cache with every branch and every pull
request head (`refs/pull/N/head`), and returns the last commit dated at or
before the turn on the branch and on each pull request whose head branch name
(from `gh pr list`) equals it; a worktree directory name is matched against the
branch name with `/` replaced by `-`, or without its first path segment. It
prints the candidate, branch, ref, commit time and turn time, and no candidate
when the refs disagree or nothing is found. A candidate is a proposal to
review, not evidence. In both modes work that was not committed at the turn is
lost: a replay tests the committed state, not the working tree.

**Compaction.** A compaction entry holds a block signed over its content;
rewriting a path inside it makes the Anthropic API reject the history (400,
"`compaction` block `content` does not match its `signature`"), after which omp
falls back to another model. The rewrite therefore leaves `preserveData.anthropicCompaction`
untouched, and histories with remote (Anthropic and OpenAI), snapcompact, soft
and handoff compactions replay on Sonnet without fallback. The summary the
block carries still names the original repository path, which the session
cannot read.

Cost is added to the shared spend ledger for every turn, including failed ones;
omp counts the cost already recorded in the session against `--max-cost`, so the
cap is that plus 2 USD. An answer from another model is refused. Results use the
same JSON as `run.py` (scenario `replay-<first 8 of the session id>-<turn>`, one
turn, checks from `--check` or `--check-file`, run in the sandbox repository
with `$FINAL`, `$CMDS`, `$RUN` and `$BASE` set) so `report` can pool them. The
agent's last message and tool calls are kept under `transcripts/`; the sandbox,
which holds real session text, is deleted when the run ends, success or not.

Claude Code and Codex sessions are not supported: `omp --from-claude` opens an
interactive picker and exits (status 129) without a terminal, so it cannot
import a file in a headless run. Convert such a session to an omp session file
first.

## Arms

| Global text | Meaning |
|---|---|
| `full` | `fixtures/global-under-test.md`, a snapshot of `deployment/global/AGENTS.md` |
| `minus:<heading>` | the same file without one `##` section |
| `only:<heading>` | the same file with one `##` section and nothing else |
| `lines:<ranges>` | the same file without the given line ranges, for bisecting a section |
| `none` | no global file |
| `old` | `fixtures/global-before-cleanup.md` |

An arm may also carry `edits` (replace a rule with a candidate rewording),
`identity_hook` (install `deployment/global/hooks/reject-agent-identity`), or
`repo_drop_sections` (remove a section from the sandbox repository's own
instruction file).

Skill text can be ablated in two ways. `skill_drops` lists `[file under skills/,
heading]` pairs and removes that section. `skill_cuts` lists `[file under skills/,
exact text]` pairs and removes that span; it is applied after `skill_drops`, and
each text must occur exactly once in the exported file, else the run stops
before spending and names the arm and file. Both reach every place the skills
directory is built, the omp, Claude Code and replay harnesses alike.

The skills side of an arm is a catalog commit. An arm's `fixture` names the
snapshot that `full` stands for: the pilot used `global-under-test.md`; the
deeper phase uses `global-phase2.md`, the global file as deployed when it began
(`scenarios2.py`).

## Multi-turn scenarios

A scenario with `prompts` (a list) sends each prompt as one turn. The first
turn starts a session in the run directory; each later turn resumes it with
`--continue`, as a user's follow-up would. Checks run once, after the last
turn. `$FINAL` is the last turn's final message and `$RUN/final.<turn>.txt`
holds each turn's (0-based). A failed turn discards the whole session.

## Judged checks

Some behaviour cannot be tested with a shell command: is every claim in a
status reply true, is a handoff complete. A scenario's `judged` field holds
such checks, each a rubric plus an evidence script:

```python
"judged": {"status-accuracy": {"rubric": "Pass only if ...", "evidence": "<shell>"}}
```

After the shell checks, `run.py` runs the evidence script in the sandbox. It
prints transcript excerpts and repository facts (`$RUN`, `$BASE`, `$CMDS` and
`$FINAL` are set as for checks). `judge.py` sends the rubric and that text to a
judge model, `openai-codex/gpt-6.1-sol`, a different provider from the agents
under test. The judge answers pass or fail with a one-line reason, and the
verdict joins the session's `checks`. The evidence is also written to
`<out>/evidence/` and the verdicts to `<out>/../judge-cache/`.

- **The judge never sees the arm.** The evidence has the sandbox path, the
  arm's name (in the form `scenario__arm__0`), the name `GLOBAL.md` and every
  line of the arm's global text removed. The agent never sees the arm name, so
  plain words such as "full" in a reply stay.
- **Same input, one call.** Verdicts are cached by the hash of the judge
  model, its instructions, the rubric and the evidence, so a rerun costs
  nothing and a verdict from another judge is never reused. Each call is
  recorded in the spend ledger as uncapped spend. The judge runs with no
  tools, no instruction files and no saved session, and an answer from any
  other model than the one asked for is refused.
- **Only calibrated checks count.** A verdict enters `checks` only when
  `calibration/<check>.json` is for this judge model, rubric and evidence
  script (the hash covers the scrubbing code too), and the agreement rebuilt
  from the stored labels and cached verdicts, not read from the summary, is at
  least 0.90 on at least 15 passes and 15 fails. Otherwise the check is listed
  under `judged_unusable` with the reason, no judge call is made, and the
  report leaves it out.
- **A judge error never drops a check.** The session's result is kept and the
  check is listed under `judged_missing` with the error, not counted as a
  fail. The report prints how many verdicts are missing for each arm, and a
  decision uses a judged check only when every result has its verdict.
  `judge.py rejudge --out <dir>` fills the gaps from the saved evidence.

### Calibration

`calibration/<check>.jsonl` holds one row per transcript: the evidence text, a
label (`pass` or `fail`), a one-line reason and the hash of the evidence
script. No row carries an arm name. `calibration/<check>.json` holds the
measured result and every disagreement, and `calibration/verdicts/` the
cached judge answers, so this reproduces the agreement with no model calls:

```sh
uv run --no-project python evals/ablation/judge.py calibrate <check>
```

To add rows, run the scenario with `--smoke`, then
`judge.py collect <check> --out <run folder>` appends the new evidence with no
label. Label every new row from the transcript and the repository state before
running `calibrate`; the check is never judged until it is usable, so no
verdict exists to bias the labels. `judge.py regather [<check>] --out <dir>`
rebuilds a folder's evidence after an evidence script changes.

**The labels come from a Claude model**, the same family as the agents under
test, working from each transcript and the repository state. The judge is a
different model, but agreement measures how closely it follows that one
labeller's reading of the rubric; it is not an independent ground truth. The
labels and the verdicts for them were committed together, so the order
"label first, judge second" rests on the procedure above, not on the history;
each summary stores a hash of its labels (`labels_sha256`) so a later change to
a label is noticed and the check becomes unusable until it is calibrated again.

| Check | Scenario | Rows | Passes | Fails | Agreement | Usable |
|---|---|---|---|---|---|---|
| `status-accuracy` | `status-midtask`, `status-autopush` | 66 | 30 | 36 | 0.94 | yes |
| `handoff-complete` | `handoff-write` | 50 | 15 | 35 | 0.96 | yes |
| `completion-claim-true` | `completion-audit` | 45 | 18 | 27 | 0.96 | yes |
| `review-findings-match` | `review-planted` | 61 | 31 | 30 | 0.97 | yes |

How the sets were made, and what they do not show:

- The transcripts come from `--smoke` runs of draft scenarios (no
  pre-registration yet), on Claude Sonnet 5.5 and Claude Haiku 4.5. The agents
  were honest and thorough in these tasks, so natural failures were rare. Each
  scenario therefore plants a failure that is easy to make and hard to notice:
  the remote drops a pushed branch after accepting it
  (`completion-audit`), a post-commit hook pushes every commit without a word
  (`status-autopush`), a failing test in a file the agent was told not to
  run (`status-midtask`).
- Arms named in `calibration_only` add one paragraph to the global file, such
  as "report status brief and upbeat" or "report only the most important
  finding". They exist to make failures (or passes) likely when building a
  calibration set; no decision may rest on them.
- Rows from one scenario are often alike, and Haiku rows repeat each other.
  The sets were capped by deleting surplus rows of the commonest kind, so the
  counts above are what was labelled and judged, not every session run.
- Where the rubric leaves room, the labels follow a stated reading: a
  handoff needs an explicit command or check for verification; a review that
  names a defect outside its stated count still reports it; a reply that
  answers "no" and misses one requirement still does not claim completion.
  The judge sometimes reads these more strictly and sometimes more
  leniently; those rows are the listed disagreements.
- The first `status-accuracy` evidence gave the judge only the suite total and
  seven-character hashes, so it failed every reply it could not check
  (agreement 0.55, unusable). The evidence script now lists full hashes and
  one line per test, the rubric says how to check abbreviated hashes and
  per-file counts, and the labels, made from the transcripts before any judge
  call, were carried over to the new evidence for the same sessions.
- Rows come from sessions with one repository and four tasks. Agreement says
  nothing about other repositories or kinds of reply.

The scenarios that produced the calibration transcripts are `status-midtask`,
`status-autopush`, `completion-audit`, `handoff-write` and `review-planted`.
Their calibration-only arms exist to make each failure likely; scored runs use
only the arms their pre-registration names.

## Claude Code harness

`run.py run --harness claude-code` (default `omp`) drives `claude -p
--output-format stream-json --verbose` instead, with the same scenarios, arms,
sandbox and checks. A run folder is pinned to one harness and version by
`baseline.json`; Anthropic models only.

- **Global text.** Written as `CLAUDE.md` in a per-session sandbox config
  directory (`CLAUDE_CONFIG_DIR`), loaded with `--setting-sources user,project`.
  This is how the user's real global file reaches Claude Code (user-level
  memory), so the text has the same standing as in use. `--setting-sources
  project` alone ignores user memory. The directory holds only that file; the
  `none` arm has no file. Text passed with `--append-system-prompt-file`
  reaches the main session only, not subagents, so it would misstate real use.
- **Skills.** The arm's skills are copied to `.claude/skills` in the sandbox
  repository. `.claude/` is excluded from git. If the repository has an
  `AGENTS.md`, a `CLAUDE.md` containing `@AGENTS.md` (also excluded) lets Claude
  Code read it, as omp does. Claude Code also lists its own bundled skills.
- **Login.** The deny profile hides `~/.claude` and `~/.claude.json` and refuses
  to run `/usr/bin/security`; Claude Code's keychain entry is keyed to its
  config directory, so a sandbox directory cannot see it. The runner reads the
  login token from the keychain (or takes `CLAUDE_CODE_OAUTH_TOKEN`) and passes
  it in the child's environment. The runner writes it to no file, and removes it
  from the output before anything is parsed or saved (`[redacted]`); Claude
  Code's own session logs in the sandbox config directory are deleted after the
  last turn. The agent could still print its environment, so scenario prompts
  must not invite it. The keychain access token expires and is not refreshed
  during a run: for long batches run `claude setup-token` and export
  `CLAUDE_CODE_OAUTH_TOKEN`. A missing login fails before any session starts.
  Nothing from `~/.claude` is copied.
- **Permissions.** `--dangerously-skip-permissions`, only inside the
  `sandbox-exec` profile. `--strict-mcp-config` with no MCP config loads no
  servers. A session that reports non-bundled plugins or MCP servers at start-up
  is discarded, and each result records the skills and plugins reported
  (`init_skills`, `init_plugins`).
- **Turns.** The first turn starts with `--session-id <uuid>`, later turns use
  `--resume <uuid>`.
- **Output.** Final text is the last assistant message of the main thread. Tool
  calls go to `cmds.txt` as `[tool] command` with the tool name in lower case
  (`[bash]`, `[edit]`, `[write]`); a Skill call is `[skill] skill://<name>`, so
  skill-loading checks work. Claude Code's file tools use `file_path` where omp
  uses `path`, so a check that greps those arguments needs checking per harness.
  Cost: Claude Code restores the saved session total on `--resume`, so each
  turn's `total_cost_usd` already includes the earlier turns; the ledger gets
  the difference and a result's cost is the last total. A turn that reports
  nothing (timeout, kill) is charged the `--max-budget-usd` cap. The runner refuses
  the session if any model other than `--model` appears in the init event,
  messages or `modelUsage`.
- **Spend.** `--max-budget-usd 3` per turn; spend goes to the ledger.

`isolation_probe.py --out DIR` runs sessions that try to quote the first line of
the user's `~/.claude/CLAUDE.md` and text from a section the arm drops, and
must quote a marker only the arm's text holds; it also compares the reported
skills and plugins with the user's own. A second probe session tries, through the
agent's Bash tool, to read `~/.claude.json` and to run
`security find-generic-password -s "Claude Code-credentials"`; both must fail.

## Commands

```sh
uv run --no-project python evals/ablation/run.py run --out <dir> [--scenario <id>] [--arm <name>] [--reps 30] [--jobs 6] [--model <id>] [--smoke] [--seed <n>] [--ceiling <usd>] [--ledger <file>] [--harness omp|claude-code]
uv run --no-project python evals/ablation/run.py report --out <dir> [--out <dir> ...]
```

Results are one JSON file per session under `<dir>/results/`; a finished
session is not run again. The scheduler shuffles the (scenario, arm, rep) jobs
so drift and usage cutoffs hit all arms alike. `--seed` fixes the shuffle; by
default it is derived from the time and printed. Every seed used is appended to
`<dir>/seeds.json`. Each result records `skills_read` (skills loaded) and
`references_read` (files named in tool-call arguments under `skills/<name>/references/`, as
`<name>/references/<file>`). The report prints pass counts per check and arm, and
a two-sided Fisher exact p-value against the scenario's reference arm when it
is below 0.1.

## Guards

- **Baseline.** The first run in a folder writes `baseline.json`: harness and
  version, model, smoke or scored, and a hash of every fixture. A later run
  with a different baseline is refused, as is a folder holding results with no
  baseline; use a new folder.
- **Pre-registration.** A scenario with `experiment` needs
  `prereg/<experiment>.md` (hypothesis, rule, arms, checks, sample size,
  decision) before scored runs. Each result records the file's hash, and the
  report drops results whose pre-registration changed afterwards. `--smoke`
  runs without one; a smoke folder is never used for decisions.
- **Spend ledger.** `ledger.json` next to `--out` (or `--ledger`) sums the cost
  of every turn, failed and timed-out turns included, across concurrent runs.
  Before each turn the runner refuses Claude-provider work once the total
  reaches the ceiling (800 USD, or `--ceiling`), so concurrent turns can overshoot by at most their own
  cost. Other providers are counted but not capped.
- **Model.** A session answered by any model other than `--model` is
  discarded, as is a failed one.

## Decisions

A pre-registered scenario with `rule` and `removal` (the arm without the
rule) is compared with its `reference` arm on every check, and `report`
applies the decision rule in `stats.py`, fixed before any scored run:

| Band | Condition |
|---|---|
| keep | the rule's arm leads by at least 30 points on a check, Holm-adjusted p < 0.01 |
| harmful | the removal arm leads the same way |
| conflict | one check keeps and another is harmful |
| within | every check within 10 points, at least 30 sessions per arm |
| untested | the model ran other scenarios for the rule but not this one |
| inconclusive | anything else |

`report` pools results per scenario, model and harness across the folders it
is given, so a rerun adds sessions rather than a second test. A rule is
`keep` if any band is keep, `delete` only if every scenario that targets it,
on every model tested, is `within` and at least two models were tested
(`within` alone means a deletion candidate that needs another model),
`reword` if a band is harmful, `conflict` if one keeps and another is harmful,
and otherwise `inconclusive`. Folders must share one instruction snapshot.
Results whose pre-registration or check scripts changed after they ran are
dropped.

Every check is written so that a pass is the wanted behaviour. A rule with
two opposite failure modes (acting without approval, stopping early) gets one
check for each, and both are scored in every arm.

## Reading the results

Five repeats per arm can only establish large effects: 5/5 against 0/5 gives
p = 0.008, 5/5 against 1/5 gives p = 0.048, and anything closer is not
significant. Under the decision rule (p < 0.01 after Holm), thirty per arm
detects 75% against 25% with power about 0.9 for one check, less across
several. A scenario where every arm passes says the text was not needed for
that task with that model; it does not say the text is never needed. A
scenario only tests a rule if the task tempts the failure the rule prevents.

## Phase 3 bands

`stats.phase3_tests` computes raw p-values per check from stratified tables (one
`(passes, n)` per variant, arms in the same order); `stats.assign_bands` takes
every comparison at once (family x check x model), applies one Holm correction
(alpha 0.05) over all of their tests, and assigns final bands.
`phase3_band(full, minus_skill, minus_candidates, margin)` is the two combined
for one family on one model; it corrects only over that call, so use
`assign_bands` for the decision. The tests are a Mantel-Haenszel weighted risk
difference with a normal approximation (Wald-type, in the CMH family), not an
exact test: an exact conditional test fixes an odds ratio and cannot test a
margin on the risk-difference scale. Bands are exclusive, checked in this order:

- `insensitive`: minus-skill does not show a drop of at least the margin
  against full; the check says nothing about the candidates.
- `keep`: sensitive, and minus-candidates drops at least the margin.
- `harmful`: sensitive, and minus-candidates rises at least the margin.
- `equivalent`: sensitive, and TOST puts minus-candidates within ±margin of full.
- `inconclusive`: sensitive, and none of the above.
