# Release

Drive a BenchBox release with the version-branch flow. The authoritative
runbook is `docs/operations/release-guide.md` in the BenchBox repo — read it
before acting; this file adds only agent behavior. If this file and the
guide disagree, the guide wins.

## Authorization

One release request authorizes the full flow: `make release-cut
VERSION=X.Y.Z` → release PR checks → merge → `make release-finalize
VERSION=X.Y.Z`. Work it end to end; do not stop mid-flow to re-ask for the
finalize step. Stop and ask only when a gate genuinely needs the user
(a required human approval, or evidence that cannot be regenerated).

## Preconditions — check before cutting

Verify, do not assume; each failure has a recovery path in the guide:

1. Committed UAT release-gate evidence is fresh (≤21 days) — stale evidence
   fails `validate-base`.
2. The latest release-canary run is green, <48h old, and its tested
   `develop` SHA is an ancestor of the intended release head.
3. `develop` is green and up to date.

## Hard rules

- `VERSION` is explicit on every target invocation; never guess it.
- Never bypass or ask to bypass `validate-base`,
  `release-required-result`, or the `release-only` ruleset.
- A failed or interrupted cut is **resumable**; prefer resume
  (`git checkout vX.Y.Z && make release-cut VERSION=X.Y.Z`) over
  `release-cut-abort`. Abort only to start over deliberately.
- Curation is the targets' job. Never hand-delete release-branch paths;
  route classification gaps through `scripts/check_release_curation.py`
  per the guide.
- Post-merge and PyPI failures: follow the guide's "Recovering from common
  failures" / "Recovering from a broken PyPI release" sections rather than
  improvising.

## Report

Version, release PR URL and merge state, tag, finalize result, and the
verification evidence consulted (UAT gate summary, canary run). If stopped
at a gate, name the gate, the exact blocker, and the resume command.
