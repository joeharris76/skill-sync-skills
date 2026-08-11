# Handoff Reference

Create a continuation prompt or session summary that lets another agent resume without rereading everything.

## Include

- Goal and current status.
- Files changed/read and why they matter.
- Decisions made and alternatives rejected.
- Commands run and results.
- Known failures, blockers, risks, and assumptions.
- Exact next steps with paths/commands.

## Modes

- `--compact`: under 300 words, highest-signal only.
- `--task`: produce a task prompt with objective, context, constraints, verification, and expected output.
- `--batch`: a self-contained prompt that drives a multi-TODO batch (or batch
  close-out) in a fresh session. Use the template below.

## Batch handoff template (`--batch`)

The prompt must stand alone — the next session has no scratchpad, no ledger,
and none of this conversation. Required sections, in order:

1. **Objective and item set** — the batch slug, every TODO id, and which
   skill drives it (`todo` `batch` or `closeout`).
2. **Tracker access preflight** — how to reach the tracker, and the check
   that the backend is the intended one (e.g. hosted vs. a silent local
   fallback) before any write.
3. **State snapshot** — live PR numbers and states, branch names, CI status,
   ledger path, captured at write time. Query them now; a handoff written
   from memory just relays a summary.
4. **Order and dependencies** — suggested sequence with each real dependency
   and why it orders the work.
5. **Non-negotiables** — worktree rule, one TODO per PR, toolchain rules
   (e.g. `uv run` only), explicit staging, integration-branch target,
   approval-gate paths that withhold auto-merge.
6. **Known traps** — every failure that cost this session time, each with
   its symptom and avoidance.
7. **Judgement guidance** — items needing a decision (make the call, record
   rationale, don't stall) vs. items needing unavailable verification (mark
   `blocked`, never mark done on an unverified claim). "Already fixed" is a
   legitimate outcome — close with evidence.
8. **Review gate** — per-phase or final adversarial review
   (`references/adversarial-review.md`) and what verdict permits closing.
9. **Revision marker** — title the prompt `<batch> handoff rev N`; a
   superseding handoff increments N and states what changed.

## Rules

Do not claim work is committed, tested, pushed, or complete unless verified in the current session. Separate facts from recommendations.
