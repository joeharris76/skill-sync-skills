"""Significance tests and the pre-registered decision rule.

Every check is scored so that a pass is the wanted behaviour. A scenario that
tests a rule names the arm that has the rule and the arm that lacks it; each
check compares the two.

Decision bands for one scenario on one model:
  keep          the rule's arm beats the removal arm by at least KEEP_GAP on
                some check, with a Holm-adjusted p below ALPHA
  harmful       the removal arm beats the rule's arm the same way
  conflict      both of the above, on different checks
  within        every check differs by at most DELETE_GAP and both arms have
                at least MIN_N sessions; one of the conditions for deletion
  inconclusive  anything else

A rule is deleted only when every scenario that targets it, on every model
tested, is ``within``. One ``keep`` keeps it; ``keep`` in one place and
``harmful`` in another is a conflict to resolve by rewording.
"""

from __future__ import annotations

from math import comb

KEEP_GAP = 0.30
DELETE_GAP = 0.10
ALPHA = 0.01
MIN_N = 30


def fisher(a_pass: int, a_n: int, b_pass: int, b_n: int) -> float:
    """Two-sided Fisher exact p-value for two pass counts."""
    total_pass, total = a_pass + b_pass, a_n + b_n

    def prob(k: int) -> float:
        return comb(a_n, k) * comb(b_n, total_pass - k) / comb(total, total_pass)

    observed = prob(a_pass)
    lo, hi = max(0, total_pass - b_n), min(a_n, total_pass)
    return min(1.0, sum(prob(k) for k in range(lo, hi + 1) if prob(k) <= observed + 1e-12))


def holm(pvalues: list[float]) -> list[float]:
    """Holm-Bonferroni adjusted p-values, in the input order."""
    m = len(pvalues)
    order = sorted(range(m), key=lambda i: pvalues[i])
    adjusted = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvalues[i]))
        adjusted[i] = running
    return adjusted


def compare(counts: dict[str, tuple[int, int, int, int]]) -> dict:
    """Band for one scenario on one model.

    ``counts`` maps check name to (passes with rule, n with rule, passes
    without rule, n without rule).
    """
    names = list(counts)
    raw = [fisher(*counts[name]) for name in names]
    adjusted = holm(raw)
    checks = {}
    for name, p_raw, p_adj in zip(names, raw, adjusted):
        kw, nw, ko, no = counts[name]
        checks[name] = {"with": f"{kw}/{nw}", "without": f"{ko}/{no}",
                        "gap": round(kw / nw - ko / no, 3), "p": p_raw, "p_holm": p_adj}
    gaps = [c["gap"] for c in checks.values()]
    significant = [c for c in checks.values() if c["p_holm"] < ALPHA]
    min_n = min(min(nw, no) for _, nw, _, no in counts.values())
    helps = any(c["gap"] >= KEEP_GAP for c in significant)
    hurts = any(c["gap"] <= -KEEP_GAP for c in significant)
    if helps and hurts:
        band = "conflict"  # a trade-off between two checks, such as opposite failure modes
    elif helps:
        band = "keep"
    elif hurts:
        band = "harmful"
    elif min_n >= MIN_N and all(abs(g) <= DELETE_GAP for g in gaps):
        band = "within"
    else:
        band = "inconclusive"
    return {"band": band, "min_n": min_n, "checks": checks}


def rule_decision(bands: list[str]) -> str:
    """Decision for a rule from its per-scenario, per-model bands.

    ``untested`` (a scenario for the rule with no results on a model that ran
    others) blocks deletion; it does not block keep.
    """
    if not bands:
        return "untested"
    if "conflict" in bands or ("keep" in bands and "harmful" in bands):
        return "conflict"
    if "keep" in bands:
        return "keep"
    if "harmful" in bands:
        return "reword"
    if all(b == "within" for b in bands):
        return "delete"
    return "inconclusive"
