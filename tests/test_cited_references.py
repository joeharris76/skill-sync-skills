"""Every skill file, skill name, and policy ID the catalog cites must exist.

Instruction text goes stale silently: a renamed skill directory or a deleted
reference file leaves pointers that send an agent to nothing. This test fails
when a catalog skill or the global instruction file cites:

1. a ``<skill-dir>/SKILL.md`` or ``<skill-dir>/references/<file>.md`` path
   that is not in ``skills/``;
2. a bare ``references/<file>.md`` path that is not in the citing skill;
3. the retired ``SHARED/`` directory layout;
4. (global instruction file only) a skill by name, as "the `<name>` skill",
   that no catalog skill declares, or a policy ID no catalog skill defines.

Vendored skills are not checked; their text is owned upstream.

Standard library only, so CI needs no third-party dependency install.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"
GLOBAL_AGENTS = ROOT / "deployment" / "global" / "AGENTS.md"

VENDORED = frozenset({"memex-search", "retro", "writing-for-agents"})

QUALIFIED = re.compile(r"(?<![\w./~-])([a-z][a-z0-9-]*)/(SKILL\.md|references/[A-Za-z0-9_.-]+\.md)")
BARE_REFERENCE = re.compile(r"(?<![\w/-])references/([A-Za-z0-9_.-]+\.md)")
NAMED_SKILL = re.compile(r"`([a-z][a-z0-9-]*)`(?:,\s*`[a-z][a-z0-9-]*`)*,?\s*(?:or\s+`[a-z][a-z0-9-]*`\s+)?skill\b")
BACKTICKED = re.compile(r"`([a-z][a-z0-9-]*)`")
POLICY_ID = re.compile(r"\b([A-Z]+(?:-[A-Z]+)+-\d{3})\b")


def catalog_files() -> list[Path]:
    return sorted(
        path
        for skill in SKILLS_DIR.iterdir()
        if skill.is_dir() and skill.name not in VENDORED
        for path in skill.rglob("*.md")
    )


def skill_names() -> set[str]:
    names = set()
    for skill_md in SKILLS_DIR.glob("*/SKILL.md"):
        for line in skill_md.read_text(encoding="utf-8").splitlines()[1:]:
            if line.strip() == "---":
                break
            if line.startswith("name:"):
                names.add(line.split(":", 1)[1].strip().strip("\"'"))
    return names


class CitedReferencesTests(unittest.TestCase):
    def test_qualified_skill_paths_exist(self):
        skill_dirs = {d.name for d in SKILLS_DIR.iterdir() if d.is_dir()}
        missing = []
        for path in [*catalog_files(), GLOBAL_AGENTS]:
            for skill, rest in QUALIFIED.findall(path.read_text(encoding="utf-8")):
                if skill in skill_dirs and not (SKILLS_DIR / skill / rest).is_file():
                    missing.append(f"{path.relative_to(ROOT)}: {skill}/{rest}")
        self.assertEqual(missing, [], "cited skill files that do not exist")

    def test_bare_reference_paths_exist_in_citing_skill(self):
        missing = []
        for path in catalog_files():
            skill = SKILLS_DIR / path.relative_to(SKILLS_DIR).parts[0]
            text = QUALIFIED.sub("", path.read_text(encoding="utf-8"))
            for name in BARE_REFERENCE.findall(text):
                if not (skill / "references" / name).is_file():
                    missing.append(f"{path.relative_to(ROOT)}: references/{name}")
        self.assertEqual(missing, [], "cited reference files that do not exist")

    def test_retired_shared_layout_is_not_cited(self):
        stale = [
            str(path.relative_to(ROOT))
            for path in [*catalog_files(), GLOBAL_AGENTS]
            if "SHARED/" in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(stale, [], "files citing the retired SHARED/ directory")

    def test_global_instruction_file_names_real_skills(self):
        names = skill_names()
        text = " ".join(GLOBAL_AGENTS.read_text(encoding="utf-8").split())
        cited = {name for match in NAMED_SKILL.finditer(text) for name in BACKTICKED.findall(match.group(0))}
        self.assertTrue(cited, "expected the global instruction file to cite skills by name")
        self.assertEqual(sorted(cited - names), [], "skills cited by name that no catalog skill declares")

    def test_global_instruction_file_policy_ids_are_defined(self):
        defined = {
            policy_id for path in catalog_files() for policy_id in POLICY_ID.findall(path.read_text(encoding="utf-8"))
        }
        cited = set(POLICY_ID.findall(GLOBAL_AGENTS.read_text(encoding="utf-8")))
        self.assertEqual(sorted(cited - defined), [], "policy IDs cited that no catalog skill defines")


if __name__ == "__main__":
    unittest.main()
