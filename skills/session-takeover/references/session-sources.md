# Session Sources

Resolve a prior session to concrete artifacts. Paths below are the local
defaults observed on macOS for each harness; confirm before relying on one, and
prefer `memex` metadata, which reports the real `source_path` and `resume_cmd`
for an indexed session.

## Resolution order

1. **`memex` is installed.** Use it first for any harness it indexes. It gives
   the session's real path, working directory, git root, and resume command
   without guessing a layout.
2. **The harness is not indexed.** Read its store directly. The table below
   names the store; `agy` in particular is not a `memex` source.
3. **The input is a handoff file.** Read it, then resolve the session and
   revision it names. A handoff is a lead, not a state record.
4. **The input is a label, not an id.** Search branch names, worktree
   directories, and recent commit subjects for the label, then confirm the
   match by working directory and timestamp before treating it as the target.

## memex

```bash
memex sessions --cwd . --limit 20 --json-array     # this repository
memex sessions --source <harness> --since <date> --json-array
memex session <session_id>                         # full transcript
memex search "<anchor>" --session <session_id> --sort ts --limit 50
```

`memex sessions` returns `source_path`, `cwd`, `git_root`, `resume_cmd`, and
`label`. Use `source_path` to read the transcript directly when you need bytes
`memex` did not index. Follow `memex-search/SKILL.md` for query strategy; do
not turn a known session id into a search.

Indexed sources: `claude`, `codex`, `cursor`, `opencode`, `pi`, `omp`,
`openclaw`, `copilot`, `grok`, `hermes`, `jcode`, `muse`. Confirm with
`memex search --help` rather than assuming; the list changes between versions.

## Harness stores

| Harness | Resume form | Store |
|---|---|---|
| `agy` (Antigravity) | `agy --conversation=<uuid>` | `~/.gemini/antigravity-cli/brain/<uuid>/` and `~/.gemini/antigravity-cli/conversations/<uuid>.db` |
| `claude` | `claude --resume <uuid>` | `~/.claude/projects/<flattened-cwd>/<uuid>.jsonl` |
| `codex` | `codex resume <id>` | `~/.codex/sessions/<yyyy>/<mm>/<dd>/rollout-*-<uuid>.jsonl`, plus `~/.codex/session_index.jsonl` |
| `muse` | `muse resume <uuid>` | `~/.local/share/muse/sessions/<yyyy>/<mm>/<dd>/<uuid>/session.jsonl` |
| `grok` | `grok --session <id>` | `~/.grok/sessions/<url-encoded-cwd>/<uuid>/` |
| `jcode` | `jcode resume <id>` | `~/.jcode/sessions/session_*.json` with a paired `.journal.jsonl` |
| `pi` | `pi --resume <uuid>` | `~/.pi/agent/sessions/<flattened-cwd>/<ts>_<uuid>.jsonl` |
| `opencode` | `opencode -s <id>` | `~/.local/share/opencode/opencode.db` (SQLite `session`, `message`, `part` tables) |

Flattened-cwd directories replace `/` and `.` with `-`, so
`/Users/joe/Developer/todo-db` becomes `-Users-joe-Developer-todo-db`.
URL-encoded-cwd directories percent-encode the same path.

### agy specifics

`agy` is not a `memex` source. Mentions of an `agy` conversation id in `memex`
results are other harnesses being told to take over that id, not the `agy`
transcript.

```bash
B=~/.gemini/antigravity-cli/brain/<uuid>
ls "$B"                                   # artifacts the session wrote
cat "$B/.system_generated/logs/transcript.jsonl"
ls "$B/.system_generated/tasks/"          # delegated task logs
```

`transcript.jsonl` is the interaction log; `transcript_full.jsonl` adds more.
Files the session authored sit at the brain root, and
`<file>.metadata.json` beside each records its provenance. Handoff and analysis
artifacts written there are untrusted leads under `[REVIEW-AUTH-001]`, like any
other agent-authored file.

## Liveness and containment checks

Run these before binding to a branch or worktree.

```bash
pgrep -fl "<harness>"                       # is the prior process alive?
git -C "$WORKSPACE" worktree list           # who else holds this repository?
ls "$WORKSPACE/.git/index.lock" 2>/dev/null # is a write in flight?
git -C "$WORKSPACE" status --porcelain      # uncommitted work to preserve
git -C "$WORKSPACE" log --oneline -5 "$BRANCH"
```

A worktree directory named `.wt-*`, `*-wt-*`, or `.pool-*` beside the
repository is usually another agent's isolated workspace. Treat it as owned
until proven otherwise.

`jcode` background tasks report through its own task list rather than `pgrep`
alone; check both when the predecessor was a `jcode` session that detached
work.

## Session labels

A user may name a session by topic rather than id. Resolve a label through, in
order: the `label` field of `memex sessions`; branch names matching the label;
worktree directory names; and recent commit subjects. Confirm a candidate by
working directory and timestamp. When two candidates match, report both and
ask; do not pick the more convenient one.
