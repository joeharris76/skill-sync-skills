# Loading the `code` skill, 2026-11-18

The phase 3 trigger evaluation found that Sonnet never loaded the `code`
skill (`2026-11-18-phase-3.md`, "Trigger evaluation"). This follow-up tested
two ways to change that.

Agents ran in omp 18.22.2 with the skills at catalog commit `1478815`. The
prompts are the 20 `code` prompts of the trigger evaluation
(`scenarios3_trigger.py`): 6 explicit, 6 implicit, 4 contextual and 4
near-miss. Sonnet 5.5 ran 3 sessions per prompt and arm, Opus 5.5 ran 2 and
Fable 5.2 ran 1.

| Model | Sessions | Cost (USD) |
|---|---|---|
| Sonnet 5.5 | 180 | 8.13 |
| Opus 5.5 | 120 | 18.72 |
| Fable 5.2 | 60 | 20.09 |

The ledger, which also counts failed turns, records 47.16 USD.

## Arms

- **current:** the deployed description, a list of 22 quoted activity phrases
  beginning `Use for "implement code", "build a feature", ...`.
- **rewrite:** the description replaced by:

  > Repository-specific coding rules a model cannot guess: the lint, typecheck
  > and test commands the repository configures, the review checklist, and
  > implementation rules such as when free-text classification needs a typed
  > judgment call. Read before writing, changing, reviewing or debugging code.
  > Also routes PR backlog sweeps, compare, shrink and handoff prompts.

- **rule:** the rewritten description, plus an omp rule file in the sandbox
  repository at `.omp/rules/code-first.md`:

  ```markdown
  ---
  scope: "tool:edit(*.py), tool:write(*.py)"
  condition: "."
  repeatMode: once
  ---
  Before this first change to source code, read skill://code and the reference it routes you to, then continue.
  ```

  omp stops the first matching `edit` or `write` call, injects the text and
  lets the agent continue.

## Result

Sessions that loaded `code`, by how the prompt asked:

| Model | Arm | Explicit | Implicit | Contextual | Near-miss |
|---|---|---|---|---|---|
| Sonnet | current | 0/18 | 0/18 | 0/12 | 0/12 |
| | rewrite | 0/18 | 0/18 | 0/12 | 0/12 |
| | rule | 11/18 | 12/18 | 6/12 | 0/12 |
| Opus | current | 0/12 | 0/12 | 0/8 | 0/8 |
| | rewrite | 0/12 | 0/12 | 3/8 | 0/8 |
| | rule | 7/12 | 12/12 | 8/8 | 0/8 |
| Fable | current | 4/6 | 3/6 | 0/4 | 0/4 |
| | rewrite | 2/6 | 3/6 | 2/4 | 0/4 |
| | rule | 5/6 | 6/6 | 4/4 | 0/4 |

- **The rewritten description did little.** Sonnet stayed at zero. Opus
  gained on contextual prompts only. Fable loaded the skill about as often as
  before.
- **The rule worked whenever it fired.** In the rule arm it fired in 59
  sessions (Sonnet 28, Opus 21, Fable 10), and the agent read `code` in all
  59.
- **Where the rule did not fire, some agents still loaded the skill
  unprompted.** In the rule arm's other explicit, implicit and contextual
  sessions the skill loaded in 1 of 20 on Sonnet, 6 of 11 on Opus and 5 of 6
  on Fable.
- **Near-miss prompts never loaded the skill** in any arm, and the rule never
  fired on one.

The rule arm cost 0.149 USD per session on average, against 0.119 for
current and 0.123 for rewrite.

## When the rule does not fire

The rule matches the `edit` and `write` tools on `*.py` paths. It does not
fire when:

- the task needs no source change, such as a review or a prompt answered
  without editing;
- the agent changes source only through the shell. At least four Sonnet
  sessions did so, with `sed -i`, a `cat >` redirect or a Python one-liner,
  and none of them read the skill.

A rule cannot make a review-only session load the skill.

## What changed

- The `code` description was left as it is.
- A user-level copy of the rule, with more file types in its scope, was
  installed in `~/.omp/agent/rules/code-first.md`. The runner disables every
  user rule file in its sandbox sessions, so the rule does not reach
  evaluation arms.

## Limits

- The scenario file for this run was not kept, so the run cannot be repeated
  from this repository. The prompts, arms and rule are as stated above.
- No pre-registration, one prompt set and one skill. Fable has one session
  per prompt.
- The rule arm also carries the rewritten description, so the rule was not
  tested with the current description.
- The rule works in omp only. Claude Code would need a `PreToolUse` hook.
- Session transcripts and results are private and not committed.
