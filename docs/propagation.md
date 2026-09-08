# Propagation Model

## Flow

```text
skill-sync product commit ────────┐
                                  ├─> pinned global store ─> agent loaders
skill-sync-skills catalog commit ─┘

source commits ─> consumer apply ─> receipt/manifest and project-local targets
```

The product repository owns `skill-sync`. This repository owns the other
catalog skills. `deployment/global/skill-sync.conf` joins exact commits and
routes `skill-sync` to the product source.

## Rules

1. Edit only an authoritative source.
2. Merge and push source changes before advancing deployment or consumer pins.
   For a breaking skill rename, merge the catalog first, then replace
   feature-branch pins in consumers with the permanent `main` commit SHA.
3. Re-apply each consumer after bumping its pinned `rev`; review and commit
   the resulting receipt, manifest, and payload through that project's Git
   workflow.
4. Serve global loaders from a validated release snapshot, never an authoring
   checkout.
5. Do not hand-edit generated global or project-local targets.

## Feature-branch testing

Create a temporary or project-local `skill-sync.conf` whose local sources
point to the feature worktrees. Preview, then apply into that project's
`.claude/skills` and `.codex/skills`, then start the test agent in that
project. This exercises the branch without changing global loaders or other
sessions.

## Deployment

1. Update the exact product or catalog `rev` in
   `deployment/global/skill-sync.conf` through review.
2. Copy the approved config to `~/.skill-sync-deployment/skill-sync.conf`.
3. Preview, apply, and check that deployment project with the vendored
   wrapper (`tools/skill-sync`).
4. Verify the materialized store offline: `skill-sync verify` proves the
   committed payload is exactly what `apply` wrote (bytes, modes, membership,
   no symlinks). `skill-sync check` proves it matches the configured
   revision; it needs the source checkouts.
5. Promote the validated store to a release snapshot and repoint the loader
   symlinks — an exact, separately approved activation; the live release
   keeps serving until then. See the repository README.
6. Re-apply downstream projects that need the new revision.

The per-target receipt records the exact resolved revisions. Activation
changes only loader symlinks, and only after validation.

Loader-owned content beside the managed skills (such as a top-level
`.system/` directory) is never modified or deleted: apply scopes its
sync-and-delete to one selected skill directory at a time, and `verify`
only inspects files inside recorded skill directories.

## Renamed shared skills

The shared framework skills were renamed from `SHARED/<name>` to
`shared-<name>` so one-level workspace loaders can discover them. Consumers
using the old names must update their `skill-sync.conf` selection in the same
change that moves them to the new catalog revision. Do not pin a consumer to
a temporary catalog branch after the catalog PR merges; point its `rev` at
the permanent `main` commit.
