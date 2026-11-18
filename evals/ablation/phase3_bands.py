"""Bands for phase 3 scored runs.

For each family, model and decision check, compares the `full` arm with
`minus-skill` and `minus-candidates`. The difference is a Mantel-Haenszel risk
difference stratified by variant, with a 20-point margin. All bands are
assigned with one Holm correction across every family x check x model
comparison (stats.assign_bands). Results are loaded with run.load_results,
which voids runs whose pre-registration, checks or scenario definition
changed after they ran.

Usage: uv run --no-project python evals/ablation/phase3_bands.py <out dir> [<out dir> ...]
"""

import collections
import sys
from pathlib import Path

import run
import stats

MARGIN = 0.20
ARMS = ("full", "minus-skill", "minus-candidates")


def main(dirs: list[Path]) -> None:
    by_id = {s["id"]: s for s in run.SCENARIOS if s.get("family")}
    # (family, model, check) -> arm -> variant -> [passes, sessions]
    cells = collections.defaultdict(lambda: {a: collections.defaultdict(lambda: [0, 0]) for a in ARMS})
    void_total = 0
    for d in dirs:
        rows, void = run.load_results(d)
        void_total += void
        for (sid, arm), results in rows.items():
            s = by_id.get(sid)
            if s is None or arm not in ARMS:
                continue
            checks = sorted({c for rule in (s.get("rules") or {}).values() for c in rule.get("checks", [])})
            for r in results:
                for c in checks:
                    cell = cells[(s["family"], r["model"].split("/")[-1], c)][arm][s["variant"]]
                    cell[0] += bool(r["checks"].get(c))
                    cell[1] += 1

    comparisons = {}
    for key, arms in cells.items():
        variants = sorted(set.intersection(*(set(arms[a]) for a in ARMS)))
        if not variants:
            continue
        strata = {a: {key[2]: [tuple(arms[a][v]) for v in variants]} for a in ARMS}
        test = stats.phase3_tests(strata["full"], strata["minus-skill"], strata["minus-candidates"], MARGIN)[key[2]]
        test["n"] = {a: sum(n for _, n in strata[a][key[2]]) for a in ARMS}
        test["rate"] = {a: sum(p for p, _ in strata[a][key[2]]) / max(1, test["n"][a]) for a in ARMS}
        comparisons[key] = test

    banded = stats.assign_bands(comparisons)
    print(f"voided {void_total} results; {len(banded)} comparisons, one Holm family\n")
    print("| family | model | check | sessions (full/skill/candidates) | full | minus-skill | minus-candidates | band |")
    print("|---|---|---|---|---|---|---|---|")
    for key in sorted(banded):
        b = banded[key]
        n, r = b["n"], b["rate"]
        print(f"| {key[0]} | {key[1]} | {key[2]} | {n['full']}/{n['minus-skill']}/{n['minus-candidates']} | "
              f"{r['full']:.2f} | {r['minus-skill']:.2f} | {r['minus-candidates']:.2f} | {b['band']} |")


if __name__ == "__main__":
    main([Path(d) for d in sys.argv[1:]])
