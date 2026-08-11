# Adversarial Review

A hostile, evidence-first review of completed work. Read-only under
`SHARED/review-protocol/SKILL.md` [REVIEW-AUTH-001]: findings only — no
edits, commits, PRs, or tracker closes, even when the request bundles
"review and fix". Remediation needs a later authorizing message (or run it
inside a write-shaped action such as `todo` `closeout`, which cites this
file for its review phase).

## Scope — pick exactly one, confirm it in the report header

| Scope | Covers |
|---|---|
| `session` | all work completed in the current or a named prior session |
| `change` | a diff, branch, PR, or PR set |
| `feature` | one feature/subsystem across its recent changes |
| `project` | a whole project — including its right to exist and complexity-vs-value |

## Stance

- Treat every self-report, commit message, and PR body as a **claim**, not a
  fact. Re-verify: does the commit exist, did CI pass, do the tests actually
  assert what the claim says?
- Known or suspected defects supplied with the request are a floor, not a
  ceiling — confirm them, then look past them.
- Look for gaps, blind spots, and deeper questions, not just line defects:
  what would a domain expert notice, and what production assumption is
  hidden? Route these through review-protocol L2/L3 [REVIEW-DEPTH-001].
- For code content, evaluate with `references/five-axis-review.md`; for
  docs, the `docs` skill's adversarial persona review.

## Verdict — always render one

`Ship` | `Ship with caveats` | `Do not ship`, with the caveats or blockers
enumerated. For `project` scope the verdict is instead
`Keep` | `Simplify` | `Retire`, with the complexity-vs-value evidence.

## Report

1. Header: scope, exact revision(s) reviewed, verdict.
2. Severity table (Critical / Required / Nit / Consider) with `file:line`.
3. Claims checked vs. claims that failed verification.
4. L2 blind-spot findings and any L3 reframe.
5. What's done well — criticism-only reviews are incomplete.

Defects route per [REVIEW-DEFECT-001]; capture per [REVIEW-CAPTURE-001].
