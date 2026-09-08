# skill-sync-skills

Canonical source for personal and shared workflow skills. The public
`skill-sync` product repository owns the bundled `skill-sync` operator skill.

## Ownership

- Edit catalog skills in `skills/`.
- Edit the operator in `skill-sync/skills/skill-sync` with its CLI contract.
- Treat agent and project targets as generated copies.

## Stable global store

`deployment/global/skill-sync.conf` composes exact product and catalog commits
into one store. The wrapper is vendored at `tools/skill-sync` (pinned product
revision; the header records the source commit), so routines need no network,
no Node, and no bootstrap. skill-sync never fetches: each `source` must be a
local checkout, and each `rev` must be present there.

```bash
mkdir -p ~/.skill-sync-deployment
cp deployment/global/skill-sync.conf ~/.skill-sync-deployment/skill-sync.conf
# Point each `source` at a local checkout, then:
tools/skill-sync preview -C ~/.skill-sync-deployment
tools/skill-sync apply   -C ~/.skill-sync-deployment
tools/skill-sync verify  -C ~/.skill-sync-deployment
```

The config targets the plain directory `store/skills` inside the deployment
project — never `$HOME`, never the live loader symlinks (the wrapper refuses
to write through symlinks by design). `verify` checks the materialized payload
offline against `store/skills/skill-sync.manifest`: every recorded file present
with matching bytes and mode, nothing extra inside a managed skill, no
symlinks. It does not prove the payload matches the configured revision —
that is what `check` is for, and `check` needs the source checkouts.

To ship a catalog or operator update, commit it in the owning repository and
bump `rev` in the template through review, then re-apply. The per-target
`skill-sync.receipt` records which commit each payload came from.

## Activation (documented follow-up, needs approval)

Global loader directories (`~/.claude/skills`, `~/.codex/skills`) are symlinks
into an immutable snapshot under `~/.skill-sync-deployment/releases/`. The
current release keeps serving until its replacement is validated: promoting a
new store means snapshotting it and repointing the two symlinks, as an exact,
reviewable change. Do not run the repointing without explicit approval.

```bash
NEW=~/.skill-sync-deployment/releases/<validated-sha>
mkdir -p "$NEW/store"
cp -a ~/.skill-sync-deployment/store/skills "$NEW/store/skills"
ln -sfn "$NEW/store/skills" ~/.claude/skills
ln -sfn "$NEW/store/skills" ~/.codex/skills
```

Test feature branches through project-local targets; do not repoint the
deployment store at an authoring worktree, and never record uncommitted bytes
under a clean SHA.

## Template gate

`tests/test_skill_sync_conf.py` validates the deployment template statically
(pins are full SHAs resolvable in this history, only tracked catalog skills
are selected, targets stay inside the project) and runs a real
preview/apply/check/verify cycle with the vendored wrapper, including the
mutation cases `verify` must reject. Standard library only. The pre-commit
hook and `.github/workflows/verify-deployment.yml` run the same suite:

```bash
python3 -m unittest discover -s tests -v
```

## Retired TypeScript-transport files (historical)

The rsync wrapper replaced the TypeScript CLI. The files below were removed
in that migration; this mapping is archaeology only, not an active fallback:

| Removed | Replacement |
|---|---|
| `skill-sync.yaml` / `skill-sync.lock` | `deployment/global/skill-sync.conf` plus the per-target `skill-sync.receipt` / `skill-sync.manifest` pair |
| `scripts/verify_lock.py` | `skill-sync verify`, plus the template gate above |
| `scripts/verify_deployment_store.py` | `skill-sync verify` against `skill-sync.manifest` |
| `scripts/activate_global_store.py` | The documented manual activation above |
| `skill-sync sync [--dry-run]`, `validate`, `doctor` | `skill-sync apply`, `preview`, `check` (see the product `MIGRATION.md`) |

Stage explicit paths only; never use `git add -A`.
