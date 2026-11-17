# Which instruction sources reach the model

Measured on 2026-11-17 with omp 18.22.0 (model `anthropic/claude-sonnet-5-5`; omp's own `reviewer` agent ran on `anthropic/claude-opus-5-5`, the user's review role) and Claude Code 2.1.323 (`--model sonnet`).

## Method

Every source carries a unique marker string. In each session the main model is asked to quote, verbatim and without any tool use, every marker present in its instructions, system prompt, listed skills or the message that assigned it work. It then spawns two subagents and each of them is asked the same thing: a task subagent (omp `task` tool, agent `task`; Claude Code Agent tool, general-purpose) and a reviewer (omp agent `reviewer`; Claude Code a general-purpose subagent given a "review probe" brief). The parent writes the brief marker into each subagent's task text.

A cell is **received** only when the exact marker is quoted back in at least 2 of the 3 sessions. Counts are quoted sessions out of 3. The control marker sits in `/tmp/loading-map-probe/control/CONTROL.md`, which no harness loads; it was quoted in none of the 45 role answers (15 sessions, 3 roles each). One unplanted string (`MARK-WORD-XXX`) was echoed once by an omp task subagent; it is the model restating the pattern, not a source.

Sources (markers): `global` (MARK-GLOBAL-7Q2), `repo AGENTS.md` (MARK-REPOAGENTS-4K8), `repo CLAUDE.md` at the repository root (MARK-REPOCLAUDE-2M5), `repo .claude/CLAUDE.md` (MARK-DOTCLAUDE-5H6), skill description (MARK-SKILLDESC-9X3), skill body (MARK-SKILLBODY-6T1), brief (MARK-BRIEFTASK-7R4 / MARK-BRIEFREV-3W9). The brief cell is n/a for the main session, which has no parent.

Sandbox: throwaway git repo under `/tmp/loading-map-probe/runs/`, no remote, `sandbox-exec` hiding the user's own agent directories (for Claude Code only its instruction sources are hidden, since it needs `~/.claude` for credentials), `--setting-sources project --strict-mcp-config` for Claude Code, discovery providers switched off for the isolated omp configuration.

## Result

Cells are main / task subagent / reviewer subagent, each as quoted-sessions out of 3. R = received, – = not received.

| Source | omp: global via `contextFiles.extra` (all providers on) | omp: global as discovered `~/.agents/AGENTS.md` (all providers on) | omp: providers off except built-in (the ablation runner's setup) | Claude Code (`--setting-sources project`) |
|---|---|---|---|---|
| Global file | R 3/3, R 3/3, R 3/3 | R 3/3, – 0/3, – 0/3 | R 3/3, R 3/3, R 3/3 (extra) | R 3/3, – 0/3, – 0/3 (`--append-system-prompt-file`) |
| Repo `AGENTS.md` | – 0/3 ×3 (shadowed by `.claude/CLAUDE.md`, see below) | – 0/3 ×3 (same) | R 3/3, – 0/3, – 0/3 | – 0/3 ×3 (never loaded) |
| Repo `CLAUDE.md` (root) | – 0/3 ×3 | – 0/3 ×3 | – 0/3 ×3 | R 3/3, R 3/3, R 3/3 |
| Repo `.claude/CLAUDE.md` | R 3/3, R 3/3, R 3/3 | R 3/3, R 3/3, R 3/3 | – 0/3 ×3 (claude provider off) | R 3/3, R 3/3, R 3/3 |
| Skill description | R 3/3, R 3/3, R 3/3 | R 3/3, R 3/3, R 3/3 | R 3/3, R 3/3, R 3/3 | R 3/3, R 3/3, R 3/3 |
| Skill body (no description text) | – 0/3 ×3 | – 0/3 ×3 | – 0/3 ×3 | – 0/3 ×3 |
| Subagent brief | n/a, R 3/3, R 3/3 | n/a, R 3/3, R 3/3 | n/a, R 3/3, R 3/3 | n/a, R 3/3, R 3/3 |
| Control (never loaded) | – 0/3 ×3 | – 0/3 ×3 | – 0/3 ×3 | – 0/3 ×3 |

The first omp column is the `omp-all-providers` configuration (and `omp-claude-provider`, which gave identical counts). The second is `omp-user-file`: a stand-in home whose `~/.agents/AGENTS.md` carries the marker, which is how the deployed global file is actually found. The third is `omp-isolated`.

### Which project instruction file omp loads (main session only, all providers on, 3 sessions each)

| Files present | Loaded |
|---|---|
| `AGENTS.md` only | `AGENTS.md` 3/3 |
| root `CLAUDE.md` only | `CLAUDE.md` 3/3 |
| `.claude/CLAUDE.md` only | `.claude/CLAUDE.md` 3/3 |
| `AGENTS.md` + root `CLAUDE.md` | `AGENTS.md` 3/3; `CLAUDE.md` 0/3 |
| `AGENTS.md` + `.claude/CLAUDE.md` | `AGENTS.md` 0/3; `.claude/CLAUDE.md` 3/3 |

omp loads one project instruction file, in the order `.claude/CLAUDE.md`, then `AGENTS.md`, then root `CLAUDE.md`. The probe repository contained all three, so in the all-providers runs only `.claude/CLAUDE.md` loaded.

### Direct answers

- **Do omp task subagents receive the global file?** It depends on how the file is supplied. Listed in `contextFiles.extra`: yes, 3/3 for both the task subagent and the reviewer. Discovered as `~/.agents/AGENTS.md` (how the deployed file is found): no, 0/3 for both, although the main session received it 3/3.
- **Do omp task subagents receive the repository `AGENTS.md`?** No. 0/3 for the task subagent and 0/3 for the reviewer in every configuration, including the one where the main session received it 3/3.
- Claude Code subagents do not receive an `--append-system-prompt-file` global (0/3), but they do receive repository `CLAUDE.md` and `.claude/CLAUDE.md` (3/3). Claude Code never loads `AGENTS.md`.

## Sources that reach no role in some harness, with recommendations

Recommendations only; no instruction file was edited.

1. **Global file in omp subagents.** The deployed `~/.agents/AGENTS.md` reaches the main session only. Any rule in it that must bind a `task` or `reviewer` subagent (for example commit, authorship, or verification rules) is not in force there. Either put those rules into the briefs the main session writes (relocate), or list the global file under `contextFiles.extra` in the omp config so that subagents get it (move). Untested: whether listing it duplicates the text in the main session's prompt.
2. **Repository `AGENTS.md` in omp subagents.** Never received. Rules that matter to subagents (build and test commands, do-not-touch areas) belong in the brief; keep `AGENTS.md` for the main session.
3. **Repository `AGENTS.md` in omp when `.claude/CLAUDE.md` exists.** Shadowed in every role. In repositories that have both, move the AGENTS.md content into `.claude/CLAUDE.md` or remove the `.claude/CLAUDE.md` file; otherwise keep only one.
4. **Repository `AGENTS.md` in Claude Code.** Never loaded in any role. A repository that keeps its rules only in `AGENTS.md` gives Claude Code none. Add a `CLAUDE.md` that carries or points to the same content (whether an `@AGENTS.md` import works was not tested).
5. **Root `CLAUDE.md` in omp.** Loaded only when no `.claude/CLAUDE.md` and no `AGENTS.md` exists. Keep it for Claude Code, but do not count on it in omp.
6. **Global file in Claude Code subagents.** An appended system prompt reaches the main session only. [INFERENCE] A global `~/.claude/CLAUDE.md` would reach subagents as repository `CLAUDE.md` does, but `--setting-sources project` excludes it, so it was not measured. Keep as is if the real global is a user-level `CLAUDE.md`; otherwise relocate critical rules into briefs.
7. **Skill bodies** reach no role until the skill is loaded, in either harness; descriptions reach every role in both. A rule that must hold without the skill being invoked belongs in the description or the brief (keep the body for procedure).

## Reproduce

```sh
uv run --no-project python evals/ablation/loading-map/probe.py run --out /tmp/loading-map-probe/out --reps 3 --jobs 4
uv run --no-project python evals/ablation/loading-map/probe.py report --out /tmp/loading-map-probe/out
uv run --no-project python evals/ablation/loading-map/probe.py shadow --out /tmp/loading-map-probe/shadow
```

`run --config <name>` runs one configuration (`omp-isolated`, `omp-claude-provider`, `omp-all-providers`, `omp-user-file`, `claude-code`). Sessions run `omp -p --mode json --model anthropic/claude-sonnet-5-5 --config <overlay> --cwd <repo> --no-session --no-title --auto-approve ...` and `claude -p --model sonnet --setting-sources project --strict-mcp-config --append-system-prompt-file <file> --tools Agent,Skill --output-format stream-json --verbose ...`, both under `sandbox-exec`.

## Cost

Reported cost of the final 15 sessions: $0.925 (omp $0.18 per three sessions, subagents included, read from the JSON progress records; Claude Code $0.196 per three, from `total_cost_usd`). The shadow test cost $0.058. Earlier pilot and discarded runs (an extraction bug that treated omp's asynchronous "spawned" message as the subagent's answer) cost roughly $0.5 more; all well under the 5 USD limit.

## Limits

- Quoting is evidence of presence, not of influence. A model could omit a marker it holds; the brief markers were quoted every time, which shows the method works for text that is present, and the control was never quoted.
- Three sessions per cell, one model per harness. Each session probes all roles at once, so a subagent's answer comes from one spawn per session.
- The task and reviewer prompts forbid tools, so "skill body" means "present without loading"; loading a skill was not tested.
- In omp the subagent briefs are rewritten by the harness ("Complete assignment thoroughly: ..."), so the brief cell shows the parent's text arrives, not that it arrives unchanged.
- Claude Code's user-level `~/.claude/CLAUDE.md` and user skills were excluded by design (`--setting-sources project`).
- The first omp columns share the same sessions' skill and brief results; only the global-file and project-file rows differ between configurations.
- Raw transcripts and per-session JSON are under `/tmp/loading-map-probe/` and are not committed.
