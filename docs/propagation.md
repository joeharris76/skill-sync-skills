# Propagation Model

How a skill edit in this repo reaches every agent session on the machine, and
where that chain has broken in practice. This repo is the single source of
truth for skills; everything downstream is a materialization of some commit
of it, sometimes a stale one.

## Topology

```
~/.skill-sync (this repo, working tree)
  |
  |-- ~/.claude/skills   (symlink -> ~/.skill-sync/skills)   \  live targets:
  |-- ~/.codex/skills    (symlink -> ~/.skill-sync/skills)   /  read on every session
  |
  `-- skill-sync sync --project <path>   (per skill-sync.yaml `projects:`)
        |
        `-- BenchBox/.claude/skills, BenchBox/.codex/skills, ...  (mirror copy,
             tracked snapshot + skill-sync.lock, no symlink)
```

Two propagation mechanisms, not one:

1. **Symlink targets** (`~/.claude/skills`, `~/.codex/skills`): not a copy.
   The working tree *is* the served state. There is no sync step between
   editing a file here and every Claude/Codex session on the machine reading
   it — the change is live the instant it hits disk, committed or not.
2. **Scoped in-repo mirrors** (e.g. `~/Developer/BenchBox/.claude/skills`):
   real copies with their own `skill-sync.lock`, produced by running
   `skill-sync sync` (BenchBox: `make skill-sync`) from a project's own
   `skill-sync.yaml`. These lag the source by however long it's been since
   someone last ran the sync there. `make skill-sync-verify` in a downstream
   repo checks its snapshot against its own lock, not against this repo's
   HEAD — it can pass while being commits behind.

The symlink targets make this repo's working tree feel like "just a config
file," but it is a deploy target with zero propagation delay. Treat edits
here with the same care as a push to a service that machine-wide sessions
depend on right now, because that's what it is.

## Invariants

**(a) The checked-out branch must always be pushed.**
Because the symlink targets serve the working tree directly, a commit that
exists only locally is a single point of failure for every skill on the
machine: if this checkout is lost or corrupted, that work is gone and every
session using it breaks simultaneously. Local-only commits are not "not yet
shared," they are "currently load-bearing and unrecoverable." Push before
moving on to other work, not at the end of a session.

**(b) Never switch branches (checkout/switch/stash) while sessions are
active.**
`git checkout` on this repo is a deploy, not a workspace nicety — it changes
what every open Claude/Codex session reads on the next skill invocation,
mid-task, with no version negotiation. A branch switch here is equivalent to
swapping a binary out from under running processes. If a branch change is
needed, confirm no session depends on the current state first, the same way
you'd drain traffic before a deploy.

**(c) The lock is regenerated in the same commit as any skill edit.**
`skill-sync.lock` records a SHA256 per tracked file. Editing a skill file
without re-running `sync` leaves the lock describing a version of the file
that no longer exists on disk — `status`/`verify` will report drift (or
silently miss it if nothing re-checks), and consumers of the lock (CI gates,
`skill-sync verify`, downstream promote/audit tooling) are reasoning about a
state that isn't real. There is no grace period: the lock and the skill tree
it describes must never be committed out of step.

**(d) Scoped in-repo copies are downstream deployments; cross-repo
references create ordering dependencies.**
A project mirror (`BenchBox/.claude/skills`) does not update itself. It
needs an explicit refresh (`skill-sync sync` / `make skill-sync` run from
that project) before it reflects a change made here — treat "I edited the
skill" and "the mirror has the edit" as two separate, ordered steps, not one.
The same ordering applies one level up: anything outside this repo that
cites specifics of an unpushed commit (a doc referencing a section number, a
PR description quoting new skill text, a downstream repo's CLAUDE.md pointing
at a path only the local branch has) is citing state that doesn't exist yet
from any other reader's vantage point. Push this repo's commits *before*
merging or publishing anything that references their content, not after —
otherwise the citation is correct only on the machine that wrote it.

For policy-contract changes, stable policy IDs are the cross-repository join
key. Land and push the canonical skill first; then regenerate downstream
mirrors and update any unabridged project protocol to carry the same IDs and
semantics. Never hand-edit a generated mirror to make a parity check pass.

## Observed failure (2026-07-26)

Concrete instance of (a) and (d) compounding: `feat/minimize-wrapper-skills`
picked up three commits (`2f838ff`, `14531b8`, `9f5409e`) that existed only
in this local checkout. `skill-sync.lock` had been regenerated at `2f838ff`
and was never re-run after the next two commits touched
`skills/todo-db/{SKILL.md,references/batch.md,references/bootstrap.md,references/queries.md}`
— a direct violation of (c), caught via `skill-sync status` reporting
`todo-db` as `modified` against a lock that no longer matched disk. Separately,
BenchBox PR #1309 was merged citing section numbers from `review-protocol`
that only existed on the unpushed branch — a violation of (d): the reference
was published before the referenced state was reachable by anyone else.
Fixed by pushing the branch, re-running `sync` to regenerate the lock, and
writing this document so the next edit doesn't repeat the same two mistakes.

## Operational checklist

Before ending a session that touched this repo:

- [ ] `git push` the checked-out branch — no unpushed commits left serving
      live sessions from a single machine.
- [ ] If any `skills/**` file changed: `skill-sync sync` (or `--dry-run`
      first if unsure the plan is safe), then `skill-sync status` reports
      clean for the changed skill(s).
- [ ] `skill-sync.lock` diff is staged in the same commit as the skill
      change it describes.
- [ ] Any downstream project mirror that depends on the change has been
      refreshed (`make skill-sync` in that project) before you rely on it
      there, or you've flagged it as a known-stale fork.
- [ ] Anything outside this repo referencing the new content (a PR,
      another repo's docs) is written/merged *after* the push, not before.
