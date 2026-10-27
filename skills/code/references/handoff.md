# Handoff Reference

Prepare another agent to resume the work without rereading everything.

## Where the state goes

- When repository instructions keep session state in a todo-db tracker, or
  the user asks for a checkpoint, record it with the `todo` skill's
  `checkpoint` workflow, limited to the items this session worked on. The
  item is the record; do not keep a second copy elsewhere. Otherwise the
  handoff stays read-only.
- Give the resume prompt or summary in the reply. Write it to a file only
  when the user asks for one and names where it goes. Never use a
  scratchpad or temporary directory: other sessions cannot see it, and it
  disappears with the session.
- Follow repository instructions that name a different home for session
  state.

## Include

- Goal and current status.
- Files changed or read, and why they matter.
- Decisions made, quoted with their source, and alternatives rejected.
- Commands run and results.
- Known failures, blockers, risks, and assumptions.
- Exact next steps with paths and commands.

Leave out live PR and CI state, which goes stale; the next agent queries it.

## Modes

- `--compact`: under 300 words, highest-signal only.
- `--task`: produce a task prompt with objective, context, constraints, verification, and expected output.

## Rules

Do not claim work is committed, tested, pushed, or complete unless verified in the current session. Separate facts from recommendations.
