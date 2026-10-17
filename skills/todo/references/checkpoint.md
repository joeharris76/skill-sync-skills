# Checkpoint

Record what the next session needs in the tracker items themselves, so any
session that can reach the tracker can resume the work. The tracker, Git, the
PR service, and CI stay authoritative; a checkpoint never creates a second
record of their state.

Never write session state to a handoff file, a scratchpad, or a temporary
directory. They are invisible to other sessions and disappear with the
session or its container. If the tracker is unreachable, stop and give the
state to the user in the reply.

## Per item

For each item the session touched:

1. **Progress** — revise `context` so it says where the work stands now:
   what is done, what was found, and pointers to evidence such as PR
   numbers, commit SHAs, or file paths. Keep background, quoted decisions,
   and met criteria that are still true; remove only what is stale. Session
   history already records who changed the item and when. Keep it short.
2. **Remaining steps** — make sure `acceptance` lists them. Mark met criteria
   with `update_item(acceptance_met=[...])` when the server offers it;
   otherwise say in `context` which criteria are met.
3. **Decisions** — record each user decision that governs the item with
   `record_decision(kind="decision", text=<verbatim quote>, source=<date and
   where it was said>)` when the server offers it; otherwise quote it in
   `context` with its date and source. Never record a decision without a real
   user statement behind it. If the quote contains material that must not be
   public, record a marked summary with the same source.
4. **Open questions** — record a question only the user can answer with
   `record_decision(kind="question", ...)` when offered; otherwise release
   the claim and block the item with the question as its reason.
5. **Holds** — enforce them: `blocked` with a reason, `not_before` for a time
   hold, and the repository's PR hold mechanism for a PR. Never record a hold
   only as prose. A claimed item cannot change status, so release the claim
   before blocking it; other fields can be updated while claimed.
6. **Follow-on work** — create a new item and link it with `needs`, rather
   than describing it in `context`.
7. **Large plans** — put a plan awaiting approval in a document and add its
   location to `links`. Items have a size limit.
8. **Claim** — `release` the claim unless the session will resume the item
   itself before the lease expires.

## What not to record

- Live PR, check, or merge state; the next session queries it.
- Copies of repository rules.
- Credentials, raw logs, host configuration, or anything else that must not
  be public. Many tracker state branches live in public repositories, and
  the server refuses common credential patterns.

## Batches

Also store the latest envelope for each item in the batch ledger
(`references/batch.md`), which records order and the current item. The ledger
is local, so the batch resumes only where its ledger is. A successor in
another environment resumes the items one at a time from the tracker, using
the order given in the reply.

## Reply

End with a short resume prompt in the reply, not in a file: the item IDs in
order, the ledger path for a batch, and the first action for each item. Do
not claim work is committed, tested, pushed, merged, or complete unless you
verified it while writing the checkpoint.
