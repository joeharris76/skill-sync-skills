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
uv run --no-project python evals/ablation/run.py run --out <dir> [--scenario <id>] [--arm <name>] [--reps 30] [--jobs 6] [--model <id>] [--smoke] [--ledger <file>] [--harness omp|claude-code]
uv run --no-project python evals/ablation/run.py report --out <dir> [--out <dir> ...]
```

Results are one JSON file per session under `<dir>/results/`; a finished
session is not run again. The report prints pass counts per check and arm, and
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
  reaches 800 USD, so concurrent turns can overshoot by at most their own
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
