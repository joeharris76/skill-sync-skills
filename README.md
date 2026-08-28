# skill-sync-skills

Canonical source for personal and shared workflow skills. The public
`skill-sync` product repository owns the bundled `skill-sync` operator skill.

## Ownership

- Edit catalog skills in `skills/`.
- Edit the operator in `skill-sync/skills/skill-sync` with its CLI contract.
- Treat agent and project targets as generated copies.

## Stable global store

`deployment/global/skill-sync.yaml` composes exact product and catalog commits
into one store. After the product ownership PR merges:

```bash
mkdir -p ~/.skill-sync-deployment
cp deployment/global/skill-sync.yaml ~/.skill-sync-deployment/skill-sync.yaml
node /Users/joe/Developer/skill-sync/dist/cli/index.js sync --dry-run --project ~/.skill-sync-deployment
node /Users/joe/Developer/skill-sync/dist/cli/index.js sync --project ~/.skill-sync-deployment
node /Users/joe/Developer/skill-sync/dist/cli/index.js validate --exit-code --project ~/.skill-sync-deployment
python3 scripts/verify_deployment_store.py ~/.skill-sync-deployment/store/skills
uv run scripts/activate_global_store.py ~/.skill-sync-deployment/store/skills --apply
```

Activation rechecks every lock-owned file before changing a loader symlink. The
exact top-level `.system/` directory is loader-owned and excluded from managed-
payload attestation, so the loader root itself is not immutable. All other
payload must match the generated lock exactly. The activation script refuses
to replace real directories and atomically updates only symlinks. Test feature
branches through project-local targets; do not repoint this store to an
authoring worktree.

## Lock invariant

`skill-sync.lock` must describe the skill tree in the same commit.
`scripts/verify_lock.py` checks declarations, files, hashes, sizes, and untracked
skill files. Regenerate and verify the lock after each skill change:

```bash
uv run --with pyyaml scripts/verify_lock.py --write
uv run --with pyyaml scripts/verify_lock.py
```

The writer refreshes only file metadata and `lockedAt`; it preserves source,
install-mode, and other provenance fields. It refuses manifest/lock skill-set
changes, which require the provenance-aware catalog workflow.

The pre-commit hook and `.github/workflows/verify-lock.yml` run the same gate.
This source check differs from `skill-sync verify`, which checks tracked
consumer targets against a consumer lock.

Stage explicit paths only; never use `git add -A`.
