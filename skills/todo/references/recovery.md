# Recovery

## A gate is not a failure

`kind: "gate"` results are the tracker working. Read `recovery`, act on it, and
continue. Do not retry the same call unchanged.

## Lost claim or restarted session

`take` the same item again: re-adopting your own claim is allowed, mints a
fresh `generation`, and refreshes the lease. An earlier process image still
holding the old generation goes stale — that is the protection working. If
someone else holds the claim, you get `E_CONFLICT`; `show_item` to see who
holds it. When the holder's session is dead and cannot resume, take it over
deliberately with `takeover(item_id, expected_holder, reason)`: name the exact
holder you inspected and say why that session is gone. Never take over a live,
reachable session to skip coordination — report the conflict instead.

`E_MULTIPLE_CLAIMS` means you already hold a live claim on another task. Finish
or `release` it first — one live claim per worker.

## Conflicts

`E_CONFLICT` means a competing writer changed the task first. Re-read with
`show_item`, re-evaluate whether your operation still applies, and only then
retry. Retries re-apply the logical operation; they never merge or overwrite
the newer state.

## Offline and unknown outcomes

- `E_OFFLINE`: the remote is unreachable. `list_items` / `show_item` may serve a
  cached revision marked `stale`; mutations fail rather than succeeding locally.
  Retry when reachable.
- `E_UNKNOWN`: a push reply was lost and the outcome is undetermined. The
  `recovery` list carries the operation ID. A human reconciles with
  `todo-db recover --op-id <id>` before anyone re-applies the work.

## Schema and state errors

`E_SCHEMA` means the state format is newer than the installed package; a human
upgrades. `E_STATE` explains itself in the message — a malformed request, an
unknown task, or a rejected transition. `E_CURSOR_STALE` means restart listing
from the first page.

## Batch recovery

Prepared batches need todo-db 0.13.0 or later (advertises the `todo_db_batch`
version 2 capability). Read the live state first with `show_batch` and
`show_item`; the leader's ledger is only a cache.

- **`E_BATCH_OWNER`**: you are not the batch owner, and only the owner may
  `take`, `takeover`, `prepare`, or `finish` a member of an active batch. The
  message names the owner. Ask the owner; members hand work to the leader instead
  of claiming. If the owner is dead, recover it (below). A previous owner that
  kept a claim after recovery may `release` it but not prepare or finish.
- **`E_BATCH_HEAD`**: a head is not a recorded head, does not descend from the
  required head, or commits sit between the registered head and the submitted
  one. Read `integration_head` and the log with `show_batch`. If the leader made
  a fix or merged the integration base, record it first with `advance_batch_head`
  and retry `prepare`. If a member's base is not a recorded head, create the
  member worktree again from a recorded head, merge, and re-request landing.
- **Stale integration head** (`E_CONFLICT` on `advance_batch_head` or
  `bind_batch_pr`, or the integration branch moved while a member was working):
  re-read with `show_batch`, reconcile with Git, and retry with the current head
  as `expected_head` / `expected_previous_head`. An identical retry is
  idempotent. Send a member back to merge the current head before landing it.
- **Interrupted land between merge and prepare**: the integration branch
  contains the member merge but the tracker has no receipt. Do not re-merge or
  reset. Read `show_batch`; if the integration worktree is clean at the merged
  head, `take` the member and run `prepare` for it (the unrecorded-commit check
  passes when the merge changed only that member's files). If the worktree is
  dirty or the merge is unfinished, finish or abort the merge in Git first. A
  later `prepare` for an earlier member cannot be accepted until this one is
  recorded or the commit is reverted before anything else lands.
- **Dead leader**: a new session calls `recover_batch_owner(batch_id,
  expected_owner, expected_owner_generation, reason)`, naming the owner it
  inspected and why that session is gone. It needs no live member claim, rotates
  the owner generation (returned once, never readable again; store it in the new
  ledger), leaves existing receipts valid, and makes the caller the owner. A
  stale generation fails `E_CLAIM_STALE`; a changed owner fails `E_CONFLICT`.
  The new leader rebuilds its ledger from `show_batch`, Git, and open member
  branches, then resumes. If the generation is lost and no one with Git access to
  the state branch can supply it, abort the batch and re-run.
- **Review revisions**: after the final PR opens, fixes are leader commits:
  `advance_batch_head(reason="fix")`, push, `bind_batch_pr(head=<new>,
  expected_previous_head=<old>)`. If the second step is interrupted, the registered
  head is ahead of the binding: re-push and rebind; do not commit more first.
  Once any member is `done`, heads and bindings cannot change: resume closeout.

## Prepared receipt recovery

Prepared mode is unavailable on an older server or schema (no `todo_db_batch`
version 2 capability): stop and use the serial claim/finish loop. Do not migrate a legacy per-item receipt into a
registered batch by assertion.

If a prepared batch is abandoned, release every live member claim and have the
registered owner call `abort_batch` with the batch owner generation. Abort
refuses with `E_ACTIVE_CLAIMS` while a claim is live, refuses if any member is
already `done`, clears prepared/final member evidence, retains an already-bound
final PR receipt, detaches recoverable non-terminal members from the archived
batch, and returns them to the ordinary claim/finish lifecycle. Expired active
claims return to `open`; live claims must be released first. It is safe to retry
after an unknown publication result. An aborted or completed batch
cannot be reopened by a member or a stale owner.

If `prepare` rejects the source checkout, inspect the exact recorded revision
and clean the isolated worktree before retrying with the current claim
generation. A moved HEAD, dirty checkout, changed member scope, conflict
resolution, or late member invalidates the receipt; do not reset the baseline
or mark the member done. Re-take the member and prepare again after the
leader records the new exact range. If closeout is interrupted, re-read the
member and final integration evidence before retrying `finish`; stale
generations fail closed. A retry must use the registered integration worktree
and branch, and the tracker rechecks the current tree, every accepted member
head, the frozen scope union, and the one bound final PR before committing each
member's terminal transition.
