# skill-sync-skills

Canonical personal skill source for Claude, Codex, and project-local skill
mirrors.

## Active Loader Topology

- `/Users/joe/.skill-sync/skills` is the authoritative editable skill tree.
- `/Users/joe/.claude/skills` is expected to be a symlink to that canonical
  tree, not a separate tracked copy.
- Project mirrors such as `BenchBox/.claude/skills` and `BenchBox/.codex/skills`
  are generated materializations. Do not edit them as source of truth.

Any tool or hook that writes through `/Users/joe/.claude/skills` now edits the
canonical repo. Review `git -C /Users/joe/.skill-sync status --short` before and
after skill work.

## Lock invariant

`skill-sync.lock` records a sha256 and size for every file of every managed
skill. It only means anything if it is committed in the **same commit** as the
skill files it describes: a commit that edits a skill and keeps the old lock
ships a snapshot describing something other than what is in the tree, and
consumers cannot tell, because they trust the lock.

`scripts/verify_lock.py` enforces this. It fails when a declared skill is
missing from the lock, a locked skill is undeclared, a locked file is missing,
a recorded hash or size disagrees with disk, or a file exists under a locked
skill but the lock has never seen it — the last case being the one a hash
comparison alone cannot catch.

```bash
python3 scripts/verify_lock.py     # exit 0 when the lock matches the tree
```

It runs on every PR to `main` via `.github/workflows/verify-lock.yml`. When it
fails, regenerate the lock and commit it with the skill change, not after.

### Enforce it locally

The CI job **cannot be made a required status check**: this repository is
private on a plan without branch protection (the API returns
`403 Upgrade to GitHub Pro or make this repository public`). CI therefore only
goes red *after* a stale lock has already merged.

Install the pre-commit hook so the gate lands at the commit instead, which is
also where the fix lives:

```bash
pre-commit install     # once per checkout
```

It runs only when a commit touches `skills/`, `skill-sync.lock` or
`skill-sync.yaml` — nothing else can break the invariant — and prints the exact
files that drifted:

```
skill-sync lock is out of date with the tree (2 problem(s)):
  - todo/SKILL.md: size 1019 != locked 972
  - todo/SKILL.md: sha256 ba417d6e2126… != locked 039a3ff5e610…
```

This is distinct from the `skill-sync` CLI's own commands: `verify` checks
committed mirrors in *consumer* projects, `status` compares *installed* targets
under `~/.claude/skills`, and `validate` checks manifest portability. None of
them check this repository's own tree against its own lock.

## Recovery

If the local canonical checkout is missing or damaged:

1. Restore it from `github.com/joeharris76/skill-sync-skills`.
2. Re-create the Claude loader symlink:

   ```bash
   ln -sfn /Users/joe/.skill-sync/skills /Users/joe/.claude/skills
   ```

3. Regenerate project mirrors from each project that tracks a `skill-sync.yaml`:

   ```bash
   make skill-sync
   ```

Stage explicit paths only when committing; never use `git add -A`.
