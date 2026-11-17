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

from math import comb, erf, sqrt

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


MIN_MODELS_TO_DELETE = 2


def rule_decision(bands: list[str], models: int = MIN_MODELS_TO_DELETE) -> str:
    """Decision for a rule from its per-scenario, per-model bands.

    ``untested`` (a scenario for the rule with no results on a model that ran
    others) blocks deletion; it does not block keep. ``models`` is how many
    distinct models the bands cover: no rule is deleted on one model's result,
    so all-within on fewer than MIN_MODELS_TO_DELETE models is ``within``, a
    candidate that needs another model.
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
        return "delete" if models >= MIN_MODELS_TO_DELETE else "within"
    return "inconclusive"


# --- Phase 3: equivalence testing of a skill section against a margin --------------------------------------
#
# Phase 3 compares three arms per check: ``full``, ``minus-skill`` and ``minus-candidates``, stratified by
# variant. A stratum is ``(passes, n)`` for one arm; a table is a list of strata, one per variant, in the same
# order for both arms. Risk difference d = pass rate of the first arm minus the second, pooled across strata.
#
# Test choice: Mantel-Haenszel weighted risk difference with a normal approximation (a Wald-type test in the
# CMH family, not the CMH chi-square itself, and not an exact
# test. An exact conditional test fixes the odds ratio, not a risk difference, so it cannot test a margin on
# the risk-difference scale; an unconditional exact test would need a nuisance-parameter search per stratum.
# Weights are n1*n2/(n1+n2) per stratum; the variance uses add-half rates so a 30/30 stratum has a small
# positive variance instead of zero. The approximation is coarse below about 20 sessions per stratum.

PHASE3_ALPHA = 0.05


def _normal_sf(z: float) -> float:
    return 0.5 * (1 - erf(z / sqrt(2)))


def pooled_difference(a: list[tuple[int, int]], b: list[tuple[int, int]]) -> tuple[float, float]:
    """Mantel-Haenszel risk difference (a minus b) across strata and its standard error."""
    if len(a) != len(b) or not a:
        raise ValueError("arms need the same, non-empty list of strata")
    num = var = total = 0.0
    for (ka, na), (kb, nb) in zip(a, b):
        if na <= 0 or nb <= 0 or not (0 <= ka <= na and 0 <= kb <= nb):
            raise ValueError(f"bad stratum {(ka, na)} / {(kb, nb)}")
        w = na * nb / (na + nb)
        pa, pb = (ka + 0.5) / (na + 1), (kb + 0.5) / (nb + 1)
        num += w * (ka / na - kb / nb)
        var += w * w * (pa * (1 - pa) / na + pb * (1 - pb) / nb)
        total += w
    return num / total, sqrt(var) / total


def exceeds_p(a: list[tuple[int, int]], b: list[tuple[int, int]], margin: float) -> float:
    """One-sided p-value for H0: risk difference (a minus b) <= margin, against > margin."""
    d, se = pooled_difference(a, b)
    return _normal_sf((d - margin) / se)


def tost_p(a: list[tuple[int, int]], b: list[tuple[int, int]], margin: float) -> float:
    """TOST p-value for equivalence: the larger of the two one-sided tests against -margin and +margin."""
    return max(exceeds_p(a, b, -margin), exceeds_p(b, a, -margin))


def holm_reject(pvalues: list[float], alpha: float = PHASE3_ALPHA) -> list[bool]:
    """Holm decisions in the input order: True where the adjusted p-value is below ``alpha``."""
    return [p < alpha for p in holm(pvalues)]


def phase3_tests(full: dict[str, list[tuple[int, int]]], minus_skill: dict[str, list[tuple[int, int]]],
                 minus_candidates: dict[str, list[tuple[int, int]]], margin: float) -> dict[str, dict]:
    """Raw p-values and differences per check; no decision. Four tests per check: ``sensitive`` (minus-skill drops
    at least ``margin``), ``keep`` (minus-candidates drops), ``harmful`` (minus-candidates rises), ``tost``."""
    out = {}
    for name in full:
        d_skill, _ = pooled_difference(full[name], minus_skill[name])
        d_cand, _ = pooled_difference(full[name], minus_candidates[name])
        out[name] = {"drop_minus_skill": round(d_skill, 3), "drop_minus_candidates": round(d_cand, 3),
                     "p": {"sensitive": exceeds_p(full[name], minus_skill[name], margin),
                           "keep": exceeds_p(full[name], minus_candidates[name], margin),
                           "harmful": exceeds_p(minus_candidates[name], full[name], margin),
                           "tost": tost_p(minus_candidates[name], full[name], margin)}}
    return out


TEST_ORDER = ("sensitive", "keep", "harmful", "tost")


def assign_bands(comparisons: dict, alpha: float = PHASE3_ALPHA) -> dict:
    """Final bands for every comparison at once, with one Holm correction over all of them.

    ``comparisons`` maps any key (family, check, model ...) to a ``phase3_tests`` entry. Four p-values per
    comparison go into a single Holm family, so the correction spans all family x check x model comparisons.
    Bands are exclusive, checked in this order:

    insensitive   minus-skill does not show a drop of at least the margin against full
    keep          sensitive, and minus-candidates drops at least the margin
    harmful       sensitive, and minus-candidates rises at least the margin
    equivalent    sensitive, and TOST puts minus-candidates within +-margin of full
    inconclusive  sensitive, and none of the above
    """
    keys = list(comparisons)
    flat = holm_reject([comparisons[k]["p"][t] for k in keys for t in TEST_ORDER], alpha)
    out = {}
    for i, key in enumerate(keys):
        sensitive, keep, harmful, equivalent = flat[4 * i:4 * i + 4]
        band = ("insensitive" if not sensitive else "keep" if keep else "harmful" if harmful
                else "equivalent" if equivalent else "inconclusive")
        out[key] = {**comparisons[key], "band": band}
    return out


def phase3_band(full: dict[str, list[tuple[int, int]]], minus_skill: dict[str, list[tuple[int, int]]],
                minus_candidates: dict[str, list[tuple[int, int]]], margin: float,
                alpha: float = PHASE3_ALPHA) -> dict[str, dict]:
    """Bands for the checks of one family on one model: ``assign_bands`` over just these checks. To correct
    across families and models, collect ``phase3_tests`` for all of them and call ``assign_bands`` once."""
    return assign_bands(phase3_tests(full, minus_skill, minus_candidates, margin), alpha)
