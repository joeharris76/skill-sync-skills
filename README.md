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
