# PR Review Follow-up Sweep

Use BenchBox's project-owned review-follow-up routine. Read
`_project/audits/pr-review-sweep-template.md` before acting. The template,
Make targets, and supporting script are authoritative; do not replace them
with a manual GitHub scan.

## Scope and authorization

Identify the sweep with the repository's existing convention. Otherwise use
the PR window, date range, or another stable scope label. Use a pass number
only when the user or repository requires one.

Always preview the queue first:

```bash
make pr-review-followups-list PR_REVIEW_SINCE=YYYY-MM-DD PR_REVIEW_UNTIL=YYYY-MM-DD
```

A request to list, inspect, review, or audit follow-ups authorizes only the
preview. After the preview, run the write-shaped target when the user asks to
run or execute the sweep, or to address, fix, or action the findings:

```bash
make pr-review-followups PR_REVIEW_SINCE=YYYY-MM-DD PR_REVIEW_UNTIL=YYYY-MM-DD
```

Use the project template for worktree setup, reviewer filters, classification,
resume behavior, replies, verification, and PR publication. If the template
or Make targets are missing, report the project-binding gap and stop. Do not
invent a parallel workflow.

## Report

Report the scope label, preview counts, dispositions, commits, replies, PR URL,
verification result, and any remaining or awaiting-review items. If the run
stops, include the documented resume command.
