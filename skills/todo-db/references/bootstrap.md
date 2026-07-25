# Bootstrap The Tracker In A Fresh Project

Adopt the `todo-db` tracker in a project that has none. Prerequisite: a
checkout of the standalone todo-db package (default assumption: sibling
checkout at `<repo>/../todo-db`). Document only what `todo-db --help` confirms;
the CLI contract is authoritative.

## 1. Local database init

```sh
todo-db --db .todo-db/standalone.sqlite init \
  --project-id <project-id> \
  --repository <repository-url>
```

- The database binds permanently to `--project-id`/`--repository`; every later
  call must present the same identity or be rejected. Pick stable values.
- Gitignore the database directory: add `.todo-db/` to `.gitignore`.
- Without a wrapper, run via `uv run --project <todo-db-checkout> todo-db ...`.
  `--db` defaults from `TODO_DB_PATH` (local path) or `TODO_DB_URL` (hosted),
  else `./.todo-db/standalone.sqlite`; identity defaults from
  `TODO_DB_PROJECT_ID`/`TODO_DB_REPOSITORY`. The audit actor comes from
  `--actor` or `TODO_ACTOR`/`CLAUDE_SESSION_ID`/`CODEX_SESSION_ID`/
  `AGENT_SESSION_ID`.

## 2. Project wrapper (recommended)

Create `_project/scripts/todo` (chmod +x) so every caller gets the project
identity injected and the `todo` command resolves per the SKILL.md rule:

```bash
#!/usr/bin/env bash
#
# <project> TODO tracker entry point. Routes every subcommand to the canonical
# `todo-db` CLI, injecting this project's immutable identity so the database
# refuses any mismatched or cross-project access.
#
# Env overrides (tests/CI):
#   TODO_DB_TOOL  path to the todo-db tool checkout (default: sibling ../todo-db)
#   TODO_DB_PATH  path to the project database (default: <repo>/.todo-db/standalone.sqlite)
#
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
TODO_DB_TOOL="${TODO_DB_TOOL:-$REPO_ROOT/../todo-db}"
TODO_DB_PATH="${TODO_DB_PATH:-$REPO_ROOT/.todo-db/standalone.sqlite}"

if [ ! -d "$TODO_DB_TOOL" ]; then
  echo "todo: todo-db tool not found at '$TODO_DB_TOOL' (set TODO_DB_TOOL)" >&2
  exit 2
fi

exec uv run --project "$TODO_DB_TOOL" todo-db \
  --db "$TODO_DB_PATH" \
  --project-id "<project-id>" \
  --repository "<repository-url>" \
  "$@"
```

Replace `<project-id>`/`<repository-url>` with the values used at init. Global
flags (`--db`/`--project-id`/`--repository`/`--actor`) precede the subcommand;
the wrapper supplies the first three. Add `--extra legacy` to the `uv run`
line only if the project needs the YAML import bridge.

## 3. Hosted backend (Turso/libSQL)

Provisioning happens OUTSIDE this tool: create the database and mint tokens
with the Turso tooling (`turso db create ...` plus token minting) before any
`todo-db` call. The CLI never creates the remote database — a first-use
connection to a missing database fails; it does not provision.

Then supply credentials through the environment and address the database by
URL:

- `TODO_DB_URL=libsql://<db>.<region>.turso.io` (or pass `--db <url>`;
  plaintext `http://` URLs are refused).
- `TODO_DB_AUTH_TOKEN` — read-write connections.
- `TODO_DB_RO_AUTH_TOKEN` — read-only connections (e.g. `export`).
- Read-write hosted use requires a per-worktree embedded replica:
  `--replica .todo-db/replica.db` (keep `.todo-db/` gitignored; one replica
  path per worktree, never shared).

```sh
TODO_DB_AUTH_TOKEN=... todo-db \
  --db libsql://<db>.<region>.turso.io \
  --replica .todo-db/replica.db \
  init --project-id <project-id> --repository <repository-url>
```

Hosted adapters are optional extras of the todo-db package
(`uv sync --extra hosted --extra audit` in the tool checkout).
