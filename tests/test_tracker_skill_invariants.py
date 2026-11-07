"""Invariants test ensuring todo is the sole canonical tracker skill.

Enforces:
1. Exactly one tracker skill exists in the catalog (``skills/todo``).
2. No legacy tracker aliases (such as ``todo-db``) exist as catalog directories or skill names.

Standard library only, so CI needs no third-party dependency install.
"""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"

FORBIDDEN_TRACKER_NAMES = {"todo-db", "tractable", "tracker", "todos"}


def extract_frontmatter_name(content: str) -> str | None:
    if not content.startswith("---"):
        return None
    parts = content.split("---", 2)
    if len(parts) < 3:
        return None
    for line in parts[1].splitlines():
        line = line.strip()
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip().strip("\"'")
    return None


class TrackerSkillInvariantsTests(unittest.TestCase):
    def setUp(self):
        self.skill_dirs = [d for d in SKILLS_DIR.iterdir() if d.is_dir() and not d.name.startswith(".")]

    def test_no_forbidden_tracker_directories(self):
        dir_names = {d.name for d in self.skill_dirs}
        for forbidden in FORBIDDEN_TRACKER_NAMES:
            self.assertNotIn(
                forbidden,
                dir_names,
                f"catalog must not contain retired tracker directory {forbidden!r}",
            )

    def test_no_forbidden_tracker_skill_names(self):
        for s_dir in self.skill_dirs:
            skill_md = s_dir / "SKILL.md"
            if not skill_md.exists():
                continue
            name = extract_frontmatter_name(skill_md.read_text(encoding="utf-8"))
            for forbidden in FORBIDDEN_TRACKER_NAMES:
                self.assertNotEqual(
                    name,
                    forbidden,
                    f"skill in {s_dir.name} declares forbidden tracker name {forbidden!r}",
                )


if __name__ == "__main__":
    unittest.main()
