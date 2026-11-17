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
