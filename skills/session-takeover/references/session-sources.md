# Session Sources

Resolve a prior session to concrete artifacts. Paths below are the local
defaults observed on macOS for each harness; confirm before relying on one, and
prefer `memex` metadata, which reports the real `source_path` and `resume_cmd`
for an indexed session.

## Resolution order

1. **`memex` is installed.** Use it first for any harness it indexes. It gives
   the session's real path, working directory, git root, and resume command
   without guessing a layout.
2. **The harness is not indexed** (not among the `--source` values in
   `memex search --help`). Read its store directly; the table below names it.
3. **The input is a handoff file.** Read it, then resolve the session and
   revision it names. A handoff is a lead, not a state record.
4. **The input is a label, not an id.** Check the `label` field of
   `memex sessions`, then branch names, worktree directories, and recent commit
   subjects; confirm a match by working directory and timestamp.

## memex

```bash
memex sessions --cwd . --limit 20 --format json    # this repository
memex sessions --source <harness> --since <date> --format json
memex session <session_id>                         # full transcript
memex search "<anchor>" --session <session_id> --sort ts --limit 50
```

`memex sessions` returns `source_path`, `cwd`, `git_root`, `resume_cmd`, and
`label`. Use `source_path` to read the transcript directly when you need bytes
`memex` did not index. Follow `memex-search/SKILL.md` for query strategy; do
not turn a known session id into a search.

Indexed sources are the `--source` values in `memex search --help`.

## Harness stores

| Harness | Resume form | Store |
|---|---|---|
| `agy` (Antigravity) | `agy --conversation=<uuid>` | `~/.gemini/antigravity-cli/brain/<uuid>/` and `~/.gemini/antigravity-cli/conversations/<uuid>.db` |
| `claude` | `claude --resume <uuid>` | `~/.claude/projects/<flattened-cwd>/<uuid>.jsonl` |
| `codex` | `codex resume <id>` | `~/.codex/sessions/<yyyy>/<mm>/<dd>/rollout-*-<uuid>.jsonl`, plus `~/.codex/session_index.jsonl` |
| `muse` | `muse resume <uuid>` | `~/.local/share/muse/sessions/<yyyy>/<mm>/<dd>/<uuid>/session.jsonl` |
| `grok` | `grok --resume <id>` | the `source_path` from `memex sessions`; `~/.grok/sessions/` now holds only `session_search.sqlite`, so the transcript layout is not known |
| `jcode` | `jcode --resume <id>` | `~/.jcode/sessions/session_*.json` with a paired `.journal.jsonl` |
| `pi` | `pi --session <path\|id>` | `~/.pi/agent/sessions/<flattened-cwd>/<ts>_<uuid>.jsonl` |
| `opencode` | `opencode -s <id>` | `~/.local/share/opencode/opencode.db` (SQLite `session`, `message`, `part` tables) |
| `goose` | `goose session --resume --session-id <id>` | the `source_path` from `memex sessions`; `~/.local/share/goose/` holds only `projects.json` on this machine |
| `omp` | `omp --resume <id-prefix\|path>` | `~/.omp/agent/sessions/<flattened-cwd>/<ts>_<uuid>.jsonl` |
| `aider` | `aider --restore-chat-history` | `.aider.chat.history.md` and `.aider.input.history` in the repo root |
| `hermes` | `hermes session <id>` | `~/.hermes/` (mostly usage and interaction telemetry) |

Claude flattens the cwd by replacing `/` and `.` with `-`
(`/Users/u/Dev/my-repo` becomes `-Users-u-Dev-my-repo`); pi wraps the same
string in `--…--`. Inside omp, `history://` also reads sessions.

### agy specifics

Use these paths when `memex` is not installed.

```bash
B=~/.gemini/antigravity-cli/brain/<uuid>
ls "$B"                                   # artifacts the session wrote
cat "$B/.system_generated/logs/transcript.jsonl"
ls "$B/.system_generated/tasks/"          # delegated task logs
```

`transcript.jsonl` is the interaction log; `transcript_full.jsonl` adds more.
Files the session authored sit at the brain root, and
`<file>.metadata.json` beside each records its provenance.

## Liveness and containment checks

Run these before binding to a branch or worktree.

```bash
# Write-mode descriptors in the workspace, excluding this agent's own process tree:
OWN=$(ps -axo pid=,ppid= | awk -v me=$$ '{p[$1]=$2} END{for(x=me;x>1;x=p[x])print x; for(i in p)for(x=i;x>1;x=p[x])if(x==me){print i;break}}')
lsof +D "$WORKSPACE" 2>/dev/null | awk -v own="$OWN" 'BEGIN{n=split(own,a,"\n");for(i=1;i<=n;i++)s[a[i]]=1} NR==1||($4~/^[0-9]+[wu]/&&!($2 in s))'
git -C "$WORKSPACE" worktree list                   # who else holds this repository?
LOCK_PATH=$(git -C "$WORKSPACE" rev-parse --path-format=absolute --git-path index.lock 2>/dev/null || echo "$WORKSPACE/$(git -C "$WORKSPACE" rev-parse --git-path index.lock)")
test -f "$LOCK_PATH" && echo "Index lock in flight: $LOCK_PATH"
git -C "$WORKSPACE" status --porcelain              # uncommitted work to preserve
git -C "$WORKSPACE" log --oneline -5 "$BRANCH"
```

`cwd` rows in `lsof` output are processes sitting in the directory, not writers.

### Writer admission and concurrency control

When taking over an interrupted session, ensure another successor has not
already claimed the target branch or worktree:

1. **Concurrent writers:** apply the live-writer rule in `SKILL.md` Step 2,
   using the `lsof` command above.
2. **Worktree leases:** treat sibling directories named `<repo>.wt-*` or
   `<repo>.pool-*`, and every entry in `git worktree list`, as owned until shown
   dead.
3. **Admission:** follow `shared-change-framework/SKILL.md` section 4 for branch
   reuse or creation. Claim the worktree with a single `git worktree add`; if it
   fails because the branch is checked out or the directory exists, halt and
   report the existing worktree to the user rather than overwriting it.

`jcode` background tasks report through its own task list rather than `pgrep`
alone; check both when the predecessor was a `jcode` session that detached
work.
