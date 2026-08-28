# Propagation Model

## Flow

```text
skill-sync product commit ────────┐
                                  ├─> pinned global store ─> agent loaders
skill-sync-skills catalog commit ─┘

source commits ─> consumer sync ─> consumer lock and project-local targets
```

The product repository owns `skill-sync`. This repository owns the other
catalog skills. `deployment/global/skill-sync.yaml` joins exact commits and
routes `skill-sync` to the product source.

## Rules

1. Edit only an authoritative source.
2. Merge and push source changes before advancing deployment or consumer pins.
   For a breaking skill rename, merge the catalog first, then replace
   feature-branch pins in consumers with the permanent `main` commit SHA.
3. Regenerate each source or consumer lock with the files it describes.
4. Serve global loaders from the generated store, never an authoring checkout.
5. Do not hand-edit generated global or project-local targets.

## Feature-branch testing

Create a temporary or project-local manifest whose local sources point to the
feature worktrees. Materialize into that project's `.claude/skills` and
`.codex/skills`, then start the test agent in that project. This exercises the
branch without changing global loaders or other sessions.

## Deployment

1. Update the exact product or catalog ref in
   `deployment/global/skill-sync.yaml` through review.
2. Copy the approved manifest to `~/.skill-sync-deployment/`.
3. Dry-run, sync, and validate that deployment project.
4. Attest the generated store with `scripts/verify_deployment_store.py`.
5. Run `scripts/activate_global_store.py` with `--apply`; it repeats the
   attestation before changing either loader link.
6. Sync downstream projects that need the new revision.

The deployment lock records the exact resolved revisions. Activation changes
only loader symlinks after the generated store contains
`skill-sync/SKILL.md`. Attestation covers the exact lock-owned payload, not the
whole loader root: the exact top-level `.system/` directory is loader-owned,
excluded before traversal, and never modified or deleted by these scripts.

## Renamed shared skills

The shared framework skills were renamed from `SHARED/<name>` to
`shared-<name>` so one-level workspace loaders can discover them. Consumers
using the old names must update their manifest, dependency references, and
lock in the same change before switching to the new catalog revision. Do not
pin a consumer to a temporary catalog branch after the catalog PR merges;
regenerate the consumer lock against the permanent `main` commit.
