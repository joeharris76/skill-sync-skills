# SkillSpector triage

Triage record for the findings NVIDIA SkillSpector reports on this catalog.
Every finding is classed as **real** (fixed), **declared purpose** (the skill
does this on purpose and says so) or **false positive** (the scanner matched
words, not behaviour). The CI gate (`scripts/skillspector_scan.py`) fails on
any static finding not accepted here; README.md, "Security scan", explains how
to keep the baselines in step with this file.

- Scanner: SkillSpector 2.12.0, commit
  `9dc82fe473329b2b742aa5097dcfe7ae55f51b01`.
- Scan date: 2026-11-13.
- Scope: the 15 skills tracked in `skills/`.

## Static findings

These are the findings accepted in `.skillspector/baselines/`. The reason
column is the text each baseline entry carries.

| Skill | Rule | File | Flagged text | Triage | Reason |
|---|---|---|---|---|---|
| `code` | EA2 Autonomous Decision Making | `references/pr-sweep.md` | "authorize unrelated work or bypass approval gates." | False positive | The sentence says a sweep request does *not* authorize bypassing approval gates. |
| `shared-agent-execution` | EA2 Autonomous Decision Making (two matches: "auto-approve", "--auto-approve") | `references/external-harnesses.md` | "Confirmation automation (`--approval-mode`, `--auto-approve`) is allowed only within that already-bounded write scope." | False positive | The sentence restricts the flag to an authorized, dedicated worktree; it does not grant unattended approval. |
| `shared-investigation-framework` | EA2 Autonomous Decision Making | `SKILL.md` | "claim a documented rule is mechanically enforced without checking the enforcement path." | False positive | The sentence forbids claiming enforcement without checking it. |
| `todo` | AS1 Agent Config Directory Access | `references/bootstrap.md` | "`~/.codex/config.toml`" | Declared purpose | Documents where a human registers the tracker's MCP server for Codex; the skill never reads the file. |
| `todo` | RA2 Session Persistence | `references/queries.md` | "create a task that waits until a set time." | False positive | Describes the tracker's `not_before` field, not a cron job, startup script or other persistence mechanism. |

The retired `tidy-perms` skill accounted for four further AS1 findings; it was
removed rather than baselined. The `skill-sync` operator skill (owned by the
product repository) has one AS3 false positive on sample diff output; this
catalog does not scan it.

## Semantic findings

One pass with the LLM analyzers (`SKILLSPECTOR_PROVIDER=claude_cli`; the
provider does not report the model name). Three skills (benchbox, blog, code)
hit the scan's runtime limit when five scans ran at once and were rerun one at
a time; all 15 then completed every semantic analyzer. LLM output varies
between runs, so this pass is not a CI gate. The semantic analyzers also
repeated the static findings above; they are not listed again.

| Skill | Rule | File | Finding | Triage | Outcome |
|---|---|---|---|---|---|
| `substack` | SQP-1 vague trigger (low) | `SKILL.md` description | The description was a bare list of verbs (`status`, `sync`, `pull`, ...) with no Substack context, so it could match git or other requests, including publishing actions. | Real | Fixed: the description now names Substack and the letterops MCP server and excludes git and other sync requests. A rescan reports nothing. |
| `code` | SQP-1 vague trigger (low) | `SKILL.md` description | Trigger phrases such as "implement code" and "review code" are broad. | Declared purpose | `code` is the catalog's general coding skill; broad coding triggers are its job. |
| `shared-investigation-framework` | SQP-1 vague trigger (low) | `SKILL.md` description | The description bundles five workflows without exclusions. | Declared purpose | A shared framework that other skills cite by path; the description lists exactly the workflows it owns. |
| `shared-agent-execution` | SDI-4 description-behaviour mismatch (low) | `references/external-harnesses.md`, claude reviewer | The claude reviewer is labelled Hard Read-Only although `--tools` restricts tools, not the process, and it runs in the reviewed worktree. | Declared design, open question | The skill defines Hard Read-Only as "a sandbox or tool allowlist", and seven harnesses share that rule. Whether project settings and hooks loaded from the reviewed worktree make allowlist reviewers soft is a policy question for all seven, recorded as a follow-up rather than changed for one row. |

`retro` and `writing-for-agents` (vendored) had no findings, static or
semantic.

## When to rerun

Run the semantic pass again when a vendored skill is refreshed or the scanner
pin is bumped. From a terminal with a working `claude` login, for each skill:

```bash
SKILLSPECTOR_PROVIDER=claude_cli skillspector scan skills/<skill> --format json --output /tmp/<skill>.json
```

Run scans one or two at a time; more trips the scanner's runtime limit.
Triage every new finding here before fixing or baselining it.
