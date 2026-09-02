"""R3 — parity list / section order guard for shared-review-protocol.

Validates that ``skills/shared-review-protocol/SKILL.md`` preserves its
8-section contract. Read-only; fails with the offending ID named.

Two invariants (against origin/main 099ed49 and later polish branches that
do not renumber sections):

  a) Section headers ``## N. ... [REVIEW-XXX-001]`` appear numbered 1-8 in
     document order matching EXPECTED_IDS.
  b) The bullet list under §7 (Semantic Parity, ``[REVIEW-PARITY-001]``)
     contains exactly those 8 IDs. This test enforces **document order**
     (not just set equality) so drift in ordering is also caught.
"""

import re
import unittest
from pathlib import Path

EXPECTED_IDS = [
    "REVIEW-AUTH-001",
    "REVIEW-DEFECT-001",
    "REVIEW-DEPTH-001",
    "REVIEW-L2-001",
    "REVIEW-CAPTURE-001",
    "REVIEW-FIT-001",
    "REVIEW-PARITY-001",
    "REVIEW-PLAN-RECON-001",
]

# ``## 1. Scope [REVIEW-AUTH-001]`` — capture number and ID.
HEADER_RE = re.compile(
    r"^##\s+(?P<num>\d+)\.\s+.*?\["
    r"(?P<id>REVIEW-[A-Z0-9-]+)"
    r"\]",
    re.MULTILINE,
)

# Bullets like ``- `REVIEW-AUTH-001` `` (backticks optional, any indent).
BULLET_RE = re.compile(r"^\s*-\s+`?(REVIEW-[A-Z0-9-]+)`?\s*$", re.MULTILINE)


def _skill_path() -> Path:
    # tests/test_*.py -> repo root is parent of tests/
    p = Path(__file__).resolve().parents[1] / "skills" / "shared-review-protocol" / "SKILL.md"
    if not p.is_file():
        # Fallback when cwd is repo root (discover) — same location, but be explicit.
        p = Path.cwd() / "skills" / "shared-review-protocol" / "SKILL.md"
    return p


def _read_skill() -> str:
    path = _skill_path()
    assert path.is_file(), f"SKILL.md not found at {path}"
    return path.read_text(encoding="utf-8")


class ReviewProtocolParityTests(unittest.TestCase):
    def test_section_headers_numbered_1_to_8_with_expected_ids_in_order(self):
        """Sections 1-8 must appear in order with the canonical REVIEW-* IDs."""
        text = _read_skill()
        matches = list(HEADER_RE.finditer(text))

        found_nums = [int(m.group("num")) for m in matches]
        found_ids = [m.group("id") for m in matches]

        # Must be exactly 8 headers numbered 1-8.
        self.assertEqual(
            found_nums,
            list(range(1, 9)),
            f"Section numbers misordered or missing: expected {list(range(1, 9))}, got {found_nums} "
            f"(ids in document order: {found_ids})",
        )
        self.assertEqual(
            len(found_ids),
            8,
            f"Expected 8 REVIEW-* section headers, got {len(found_ids)}: {found_ids}",
        )
        # Order-sensitive comparison with per-ID diagnostics.
        for idx, (expected, actual) in enumerate(zip(EXPECTED_IDS, found_ids), start=1):
            self.assertEqual(
                actual,
                expected,
                f"§{idx} ID mismatch: expected `{expected}` but found `{actual}`; "
                f"full header order: {found_ids} vs expected {EXPECTED_IDS}",
            )
        # Also catch unexpected duplicates / missing via set diff (error names the IDs).
        missing = set(EXPECTED_IDS) - set(found_ids)
        extra = set(found_ids) - set(EXPECTED_IDS)
        self.assertEqual(missing, set(), f"Missing REVIEW-* section header IDs: {sorted(missing)}")
        self.assertEqual(extra, set(), f"Unexpected REVIEW-* section header IDs: {sorted(extra)}")

    def test_parity_list_under_section_7_contains_exactly_expected_ids_in_document_order(self):
        """§7 bullet list must contain exactly the 8 canonical IDs in document order.

        Policy: document order is enforced (not just set equality). If a future
        change intentionally reorders the parity list, update EXPECTED_IDS and
        this docstring together.
        """
        text = _read_skill()

        # Slice to §7 body: from "## 7." header up to (but not including) "## 8.".
        m7 = re.search(r"^##\s+7\.\s+.*?\[REVIEW-PARITY-001\]", text, re.MULTILINE)
        self.assertIsNotNone(m7, "Could not locate §7 header `## 7. ... [REVIEW-PARITY-001]`")
        m8 = re.search(r"^##\s+8\.\s+.*?\[REVIEW-PLAN-RECON-001\]", text, re.MULTILINE)
        self.assertIsNotNone(m8, "Could not locate §8 header `## 8. ... [REVIEW-PLAN-RECON-001]`")
        assert m7 and m8
        self.assertGreater(m8.start(), m7.end(), "§8 appears before §7 — document order broken")
        section7_body = text[m7.end() : m8.start()]

        bullet_ids = BULLET_RE.findall(section7_body)

        self.assertEqual(
            len(bullet_ids),
            8,
            f"Parity list under §7 should contain exactly 8 bullets, got {len(bullet_ids)}: {bullet_ids}",
        )
        # Document-order check (names the first divergence).
        self.assertEqual(
            bullet_ids,
            EXPECTED_IDS,
            f"Parity list order/content mismatch under §7: expected {EXPECTED_IDS} in document order, "
            f"got {bullet_ids}; missing {sorted(set(EXPECTED_IDS) - set(bullet_ids))} "
            f"extra {sorted(set(bullet_ids) - set(EXPECTED_IDS))}",
        )
        # Redundant set check with a clear message if duplicates/missing slipped through.
        self.assertEqual(set(bullet_ids), set(EXPECTED_IDS), f"Parity list set mismatch: got {sorted(set(bullet_ids))}")
        self.assertEqual(len(set(bullet_ids)), 8, f"Parity list has duplicate IDs: {bullet_ids}")


if __name__ == "__main__":
    unittest.main()
