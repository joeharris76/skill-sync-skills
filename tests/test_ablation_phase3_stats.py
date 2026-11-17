"""Phase 3 equivalence statistics on fixed tables. Standard library only."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ABLATION = Path(__file__).resolve().parents[1] / "evals" / "ablation"
sys.path.insert(0, str(ABLATION))

import stats  # noqa: E402

MARGIN = 0.20


def band(full, skill, cand):
    return stats.phase3_band({"c": full}, {"c": skill}, {"c": cand}, MARGIN)["c"]


class Phase3Bands(unittest.TestCase):
    def test_clear_keep(self):
        r = band([(28, 30), (27, 30), (28, 30)], [(10, 30), (9, 30), (11, 30)], [(12, 30), (11, 30), (12, 30)])
        self.assertEqual(r["band"], "keep")

    def test_clear_equivalence_with_sensitive_minus_skill(self):
        r = band([(27, 30), (28, 30), (27, 30)], [(9, 30), (10, 30), (9, 30)], [(27, 30), (27, 30), (28, 30)])
        self.assertEqual(r["band"], "equivalent")

    def test_insensitive(self):
        r = band([(30, 30)] * 3, [(30, 30)] * 3, [(30, 30)] * 3)
        self.assertEqual(r["band"], "insensitive")

    def test_inconclusive(self):
        r = band([(24, 30), (25, 30), (24, 30)], [(6, 30), (5, 30), (6, 30)], [(19, 30), (20, 30), (20, 30)])
        self.assertEqual(r["band"], "inconclusive")

    def test_harmful(self):
        r = band([(12, 30), (11, 30), (12, 30)], [(0, 30), (1, 30), (0, 30)], [(29, 30), (28, 30), (29, 30)])
        self.assertEqual(r["band"], "harmful")

    def test_bands_are_exclusive_over_a_grid(self):
        for k in range(0, 31, 5):
            r = band([(24, 30)], [(6, 30)], [(k, 30)])
            self.assertIn(r["band"], {"keep", "harmful", "equivalent", "inconclusive"})
            tests = r["p"]
            self.assertFalse(tests["keep"] < 0.05 and tests["tost"] < 0.05)


class AssignBands(unittest.TestCase):
    def test_holm_spans_all_comparisons(self):
        weak = stats.phase3_tests({"c": [(24, 30)]}, {"c": [(14, 30)]}, {"c": [(14, 30)]}, MARGIN)["c"]
        alone = stats.assign_bands({"a": weak})["a"]["band"]
        crowd = {"a": weak, **{f"n{i}": weak for i in range(40)}}
        self.assertEqual(alone, stats.assign_bands({"a": weak})["a"]["band"])
        self.assertEqual(set(stats.assign_bands(crowd)), set(crowd))
        flat = [stats.holm_reject([weak["p"][t] for t in stats.TEST_ORDER] * n)[0] for n in (1, 40)]
        self.assertGreaterEqual(flat[0], flat[1])

    def test_pooling_raises_the_holm_threshold(self):
        edge = stats.phase3_tests({"c": [(30, 30)] * 3}, {"c": [(10, 30)] * 3}, {"c": [(20, 30)] * 3}, MARGIN)["c"]
        null = stats.phase3_tests({"c": [(15, 30)]}, {"c": [(15, 30)]}, {"c": [(15, 30)]}, MARGIN)["c"]
        self.assertEqual(stats.assign_bands({"edge": edge})["edge"]["band"], "keep")
        pooled = stats.assign_bands({"edge": edge, **{f"null{i}": null for i in range(20)}})
        self.assertEqual(pooled["edge"]["band"], "inconclusive")

    def test_matches_phase3_band(self):
        tables = ([(27, 30)] * 3, [(9, 30)] * 3, [(27, 30)] * 3)
        direct = stats.phase3_band({"c": tables[0]}, {"c": tables[1]}, {"c": tables[2]}, MARGIN)
        tests = stats.phase3_tests({"c": tables[0]}, {"c": tables[1]}, {"c": tables[2]}, MARGIN)
        self.assertEqual(direct, stats.assign_bands(tests))


class Primitives(unittest.TestCase):
    def test_pooled_difference_weights_strata(self):
        d, se = stats.pooled_difference([(10, 10), (0, 10)], [(0, 10), (0, 10)])
        self.assertAlmostEqual(d, 0.5)
        self.assertGreater(se, 0)

    def test_exceeds_and_tost_directions(self):
        self.assertLess(stats.exceeds_p([(30, 30)], [(0, 30)], MARGIN), 1e-6)
        self.assertGreater(stats.exceeds_p([(15, 30)], [(15, 30)], MARGIN), 0.5)
        self.assertLess(stats.tost_p([(150, 300)], [(150, 300)], MARGIN), 0.01)
        self.assertGreater(stats.tost_p([(15, 30)], [(15, 30)], MARGIN), 0.05)

    def test_holm_reject(self):
        self.assertEqual(stats.holm_reject([0.01, 0.04, 0.03], 0.05), [True, False, False])

    def test_bad_strata_raise(self):
        with self.assertRaises(ValueError):
            stats.pooled_difference([(1, 2)], [])


if __name__ == "__main__":
    unittest.main()
