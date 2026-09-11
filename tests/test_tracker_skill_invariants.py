"""Invariants test ensuring todo is the sole canonical tracker skill.

Enforces:
1. Exactly one tracker skill exists in the catalog (``skills/todo``).
2. No legacy tracker aliases (such as ``todo-db``) exist as catalog directories or skill names.
3. The canonical ``todo`` skill is at version 3.0.0.
4. The canonical ``todo`` skill explicitly states ownership and uniqueness.

Standard library only, so CI needs no third-party dependency install.
"""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"

FORBIDDEN_TRACKER_NAMES = {"todo-db", "tracker", "todos"}


def extract_frontmatter_name_and_version(content: str) -> tuple[str | None, str | None]:
    if not content.startswith("---"):
        return None, None
    parts = content.split("---", 2)
    if len(parts) < 3:
        return None, None
    name = None
    version = None
    for line in parts[1].splitlines():
        line = line.strip()
        if line.startswith("name:"):
            name = line.split(":", 1)[1].strip().strip("\"'")
        elif line.startswith("version:"):
            version = line.split(":", 1)[1].strip().strip("\"'")
    return name, version


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
            name, _ = extract_frontmatter_name_and_version(skill_md.read_text(encoding="utf-8"))
            for forbidden in FORBIDDEN_TRACKER_NAMES:
                self.assertNotEqual(
                    name,
                    forbidden,
                    f"skill in {s_dir.name} declares forbidden tracker name {forbidden!r}",
                )

    def test_todo_skill_is_canonical_v3(self):
        todo_dir = SKILLS_DIR / "todo"
        self.assertTrue(todo_dir.is_dir(), "catalog must contain skills/todo")
        skill_md = todo_dir / "SKILL.md"
        self.assertTrue(skill_md.exists(), "skills/todo must contain SKILL.md")
        content = skill_md.read_text(encoding="utf-8")
        name, version = extract_frontmatter_name_and_version(content)
        self.assertEqual(name, "todo", f"skills/todo name must be 'todo', got {name!r}")
        self.assertEqual(version, "3.0.0", f"skills/todo version must be '3.0.0', got {version!r}")

        # Invariant: ownership statement in prose
        self.assertIn(
            "This is the only tracker skill.",
            content,
            "skills/todo must declare itself as the only tracker skill",
        )
        self.assertIn(
            "There is no separate `todo-db` skill",
            content,
            "skills/todo must declare that no separate todo-db skill exists",
        )


if __name__ == "__main__":
    unittest.main()
