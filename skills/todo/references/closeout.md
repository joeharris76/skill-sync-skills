# Batch Close-out

Use `closeout` to validate a prior session's batch and close it out. One
`closeout` call over a named batch authorizes the validation, fixes for
confirmed defects, follow-up PRs, and tracker closure for those items only.
Do not re-ask per phase. This differs from a bare review request — if the
user asked only to review or validate, use the `code` skill `adversarial`
action instead and stop at findings.

Run the three phases in order. Do not start a later phase before the earlier
one's output exists.

## Phase 1 — verify claims

The prior session's report (handoff, PR bodies, tracker notes) is a set of
claims, not facts. For each claimed item verify with commands, not prose:

- the commit/PR exists, targets the right branch, and actually merged;
- CI on the merge commit is green;
- tests asserted what the claim says (read the test, not its name);
- the tracker state matches reality (`todo show <id> --json`).

Record each claim as `verified` or `failed` with evidence.

## Phase 2 — adversarial review (findings only, no edits)

Apply the `code` skill `adversarial` action (`session` or `change` scope) to
the batch's combined diff. Known defects listed in the handoff are a floor,
not a ceiling. This phase is internal verification inside an authorized
write action per `SHARED/review-protocol/SKILL.md` [REVIEW-AUTH-001]; it
still produces zero edits — output is the severity table and verdict.

## Phase 3 — close out

1. Fix every Critical and Required finding from Phases 1–2, or prove it
   invalid. Group fixes by concern; follow `references/batch.md` mechanics
   (worktree, verify, explicit staging, PR) for each fix.
2. Resolve open deferrals with `promote` or `dismiss`.
3. Close tracker items: `complete` with PR evidence, or `drop` with
   evidence when the work proved unnecessary ("already fixed" is a
   legitimate outcome).
4. Nit/Consider findings that stay unfixed become deferrals or documented
   skips — never silent.

## Final report

Per item: `TODO | claim status | findings | disposition | PR`. Then the
Phase 2 verdict, any remaining blockers with unblock steps, and whether the
batch is fully closed.
