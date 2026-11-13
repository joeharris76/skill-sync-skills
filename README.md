# skill-sync-skills

Canonical source for personal and shared workflow skills. The public
`skill-sync` product repository owns the bundled `skill-sync` operator skill.

## Ownership

- Edit catalog skills in `skills/`.
- Edit the operator in `skill-sync/skills/skill-sync` with its CLI contract.
- Treat agent and project targets as generated copies.
- Do not edit vendored skills here; see below.

## Vendored skills

`skills/retro` and `skills/writing-for-agents` are copied unmodified from
[mattpocock/skills](https://github.com/mattpocock/skills) at commit
`5863806dd4e15c63174bee4e7515a4256792ecfa`:

| Catalog path | Upstream path | Upstream tree |
|---|---|---|
| `skills/retro` | `skills/engineering/retro` | `335c1862a43da9d629abafdb79ca0c0de118be08` |
| `skills/writing-for-agents` | `skills/productivity/writing-for-agents` | `ad2925850efb8973a72d2e666f7a975f9a2d4a9b` |

Both are © 2026 Matt Pocock under the MIT licence in each directory's
`LICENSE`, not this repository's licence. The catalog adds only `skill.yaml`
and `LICENSE`; `retro` depends on `writing-for-agents`.

To refresh one, replace the upstream files with the copy from a newer upstream
commit, keep `skill.yaml` and `LICENSE`, and update the commit and tree above
(`git rev-parse <commit>:<upstream path>` in an upstream checkout). Then
rerun the tests and scan the refreshed skill before committing. Report a
problem in a vendored skill upstream instead of patching it here.

## Global loader folders

`deployment/global/skill-sync.conf` composes exact product and catalog commits
and writes them straight into the three global loader folders:
`~/.claude/skills`, `~/.codex/skills` and `~/.agents/skills`. The home
directory is the skill-sync project root (`-C ~`; it need not be a Git
repository) and the live config is kept at
`~/.skill-sync-deployment/skill-sync.conf`. The wrapper is vendored at
`tools/skill-sync` (pinned product revision; the header records the source
commit), so routines need no network, no Node, and no bootstrap. skill-sync
never fetches: each `source` must be a local checkout, and each `rev` must be
present there.

```bash
CONF=~/.skill-sync-deployment/skill-sync.conf
tools/skill-sync preview -C ~ -f "$CONF"
tools/skill-sync apply   -C ~ -f "$CONF"
tools/skill-sync verify  -C ~ -f "$CONF"
tools/skill-sync check   -C ~ -f "$CONF"
```

`apply` writes only the selected skills plus each target's
`skill-sync.manifest` and `skill-sync.receipt`. It never removes loader-owned
content: Claude Code's cloud-synced `synced/` (an id directory plus a
`.bucket-<id>` marker) belongs only in `~/.claude/skills`, and Codex may keep
`.system/` in `~/.codex/skills`. `verify` checks each materialized payload
offline against its manifest: every recorded file present with matching bytes
and mode, nothing extra inside a managed skill, no symlinks. It does not prove
the payload matches the configured revision — that is what `check` is for, and
`check` needs the source checkouts.

### Shipping an update

1. Commit the change in the owning repository and bump `rev` in the template
   through review.
2. Copy the new `rev` into `~/.skill-sync-deployment/skill-sync.conf`.
3. Run `preview`, then `apply`, then `verify` and `check` with the commands
   above.

The per-target `skill-sync.receipt` records which commit each payload came
from. Test feature branches through project-local targets; do not point the
deployment config at an authoring worktree, and never record uncommitted
bytes under a clean SHA.

### One-time migration from the symlink model

Older machines have the three loader folders as symlinks into an immutable
snapshot at `~/.skill-sync-deployment/releases/<sha>/store/skills`, and
skill-sync refuses to write through symlinks. Migrate once: build the result in
a staging project root, prove it there, then swap each folder into place by
renaming. Renames within one filesystem are cheap and reversible, so no
folder is ever deleted until the end. This changes live loader folders, so run
it only with owner approval.

```bash
CONF=~/.skill-sync-deployment/skill-sync.conf
STAGE=~/.skill-sync-deployment/staging

# 1. Build and prove the result in the staging project root.
mkdir -p "$STAGE"
tools/skill-sync apply  -C "$STAGE" -f "$CONF"
tools/skill-sync verify -C "$STAGE" -f "$CONF"
tools/skill-sync check  -C "$STAGE" -f "$CONF"

# 2. Claude Code's synced/ belongs only in ~/.claude/skills; copy it in.
cp -a ~/.claude/skills/synced "$STAGE/.claude/skills/synced"
# Codex's loader-owned .system/, if present, is kept the same way.
[ -d ~/.codex/skills/.system ] && cp -a ~/.codex/skills/.system "$STAGE/.codex/skills/.system"

# 3. For each loader: rename the symlink aside, then rename the staged folder in.
for loader in claude codex agents; do
  mv ~/.$loader/skills ~/.$loader/skills.symlink    # renames the link itself
  mv "$STAGE/.$loader/skills" ~/.$loader/skills
  ls ~/.$loader/skills > /dev/null                    # loader folder is live
done

# 4. Check and verify at the live paths.
tools/skill-sync check  -C ~ -f "$CONF"
tools/skill-sync verify -C ~ -f "$CONF"

# 5. Remove the renamed symlinks and the emptied staging root (the snapshots
#    under releases/ stay).
for loader in claude codex agents; do rm ~/.$loader/skills.symlink; done
rm -r "$STAGE"
```

Between the two `mv` calls of step 3 the loader folder is absent for an
instant; do it while no agent session is starting. Release snapshots stay on
disk as rollback targets.

### Rollback

Rename the live folder aside and restore the symlink to the last release (the
snapshots under `~/.skill-sync-deployment/releases/` stay on disk):

```bash
REL=~/.skill-sync-deployment/releases/<last-release-sha>
for loader in claude codex agents; do
  mv ~/.$loader/skills ~/.$loader/skills.managed
  ln -s "$REL/store/skills" ~/.$loader/skills
  ls ~/.$loader/skills > /dev/null
done
```

`~/.claude/skills.managed/synced` holds Claude Code's current cloud-synced
skills; copy it back if you return to the managed folders later.

## Template gate

`tests/test_skill_sync_conf.py` validates the deployment template statically
(pins are full SHAs resolvable in this history, only tracked catalog skills
are selected, targets are exactly the three relative loader paths) and runs a
real preview/apply/check/verify cycle over those targets with the vendored
wrapper, proving loader-owned content (`synced/`, `.system/`) survives apply
and covering the mutation cases `verify` must reject. Standard library only. The pre-commit
hook and `.github/workflows/verify-deployment.yml` run the same suite:

```bash
python3 -m unittest discover -s tests -v
```

## Security scan

Every pull request to `main` scans each tracked skill in `skills/` with
[NVIDIA SkillSpector](https://github.com/NVIDIA/SkillSpector) and fails on any
finding that is not in a baseline. The scan is static (`--no-llm`): it needs
no credentials and calls no model.

The gate covers only `skills/` in this repository. It does not scan the
`skill-sync` operator skill (owned by the product repository) or
loader-owned folders such as `synced/` and `.system/`.

Run the same scan locally:

```bash
# One-time install of the pinned scanner, using its own lockfile.
PIN=$(python3 scripts/skillspector_scan.py --print-commit)
SRC=~/.cache/skillspector-src
git init --quiet "$SRC"
git -C "$SRC" fetch --quiet --depth 1 https://github.com/NVIDIA/SkillSpector.git "$PIN"
git -C "$SRC" checkout --quiet --detach FETCH_HEAD
uv sync --frozen --no-dev --project "$SRC"

# Scan all tracked skills, or name some: ... skillspector_scan.py code todo
SKILLSPECTOR_BIN="$SRC/.venv/bin/skillspector" python3 scripts/skillspector_scan.py
```

### Baselines

Accepted findings are suppressed per skill in
`.skillspector/baselines/<skill>.yaml`; `docs/skillspector-triage.md` explains
each one. An entry is a fingerprint of the finding and the file it is in, so it
stops matching when that file changes. The scan then fails with the old
finding and a stale-entry error. To fix it:

1. Confirm the finding is still the accepted one. Triage anything new in
   `docs/skillspector-triage.md` first, and never baseline a real finding.
2. Regenerate that skill's baseline:
   `skillspector baseline skills/<skill> --no-llm -o .skillspector/baselines/<skill>.yaml`
3. Replace every auto-generated `reason` with the reason from the triage
   record. The scan rejects the default reason and any `rules` entry.
4. Delete the baseline file if the skill has no findings left.

### Bumping the scanner

Change `PINNED_COMMIT` and `PINNED_VERSION` together in
`scripts/skillspector_scan.py`, reinstall, and rerun the scan. Fingerprints
include the scanner version, so regenerate every baseline and rewrite its
reasons as above, and triage any finding the new version adds. Rerun the
semantic pass described in `docs/skillspector-triage.md` after a scanner bump
or a vendored-skill refresh.

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
