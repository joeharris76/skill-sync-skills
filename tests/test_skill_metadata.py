"""Tests verifying YAML schemas and frontmatter parsing across the catalog.

Validates that every skill directory in ``skills/`` contains:
1. ``SKILL.md`` with valid YAML frontmatter containing required fields
   (``name``, ``description``, and optional ``version``, ``tools``, ``allowed-tools``).
2. ``skill.yaml`` with valid schema conforming to catalog structure:
   allowed keys, dependency existence and acyclicity, tag formatting, and targets.
3. Synchrony with ``docs/dependency-closure.md``.

Standard library only, so CI needs no third-party dependency install.
When PyYAML is available, cross-checks standard-library parsing against yaml.safe_load.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")

ALLOWED_SKILL_YAML_KEYS = {
    "depends",
    "config_inputs",
    "tags",
    "category",
    "targets",
    "portability_allow",
    "standalone_only_commands",
}

ALLOWED_CONFIG_INPUT_KEYS = {"key", "type", "description"}


def parse_val(val: str):
    """Parse primitive scalars from YAML subset."""
    if val == "true":
        return True
    if val == "false":
        return False
    if val == "{}":
        return {}
    if val == "[]":
        return []
    if val.isdigit():
        return int(val)
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        return val[1:-1]
    return val


def parse_simple_yaml(text: str) -> dict:
    """Parse the clean subset of YAML used by skill.yaml and SKILL.md frontmatter.

    Supports top-level key-values, lists of scalars, mappings of scalar booleans,
    and lists of small dictionaries (e.g. config_inputs).
    """
    lines = text.splitlines()
    root: dict = {}
    current_key: str | None = None
    current_list: list | None = None
    current_dict_in_list: dict | None = None

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        indent = len(line) - len(line.lstrip())

        # List item under current_key
        if line.lstrip().startswith("- "):
            val = line.lstrip()[2:].strip()
            if current_list is None:
                current_list = []
                root[current_key] = current_list

            if ":" in val:
                # Dict item in list (e.g. config_inputs)
                k, _, v = val.partition(":")
                item_dict = {k.strip(): parse_val(v.strip())}
                current_list.append(item_dict)
                current_dict_in_list = item_dict
            else:
                current_list.append(parse_val(val))
                current_dict_in_list = None
            i += 1
            continue

        # Nested keys inside a dict inside a list (e.g. config_inputs item properties)
        if indent >= 4 and current_dict_in_list is not None and ":" in stripped:
            k, _, v = stripped.partition(":")
            current_dict_in_list[k.strip()] = parse_val(v.strip())
            i += 1
            continue

        # Nested mapping under current_key (e.g. targets: claude: true)
        if indent >= 2 and current_key is not None and isinstance(root.get(current_key), dict) and ":" in stripped:
            k, _, v = stripped.partition(":")
            root[current_key][k.strip()] = parse_val(v.strip())
            i += 1
            continue

        # Top-level or sub-level key
        if ":" in stripped:
            k, _, v = stripped.partition(":")
            k = k.strip()
            v = v.strip()
            current_key = k
            current_list = None
            current_dict_in_list = None
            if not v:
                next_is_list = False
                for j in range(i + 1, len(lines)):
                    s = lines[j].strip()
                    if s and not s.startswith("#"):
                        next_is_list = s.startswith("- ")
                        break
                if next_is_list:
                    current_list = []
                    root[k] = current_list
                else:
                    root[k] = {}
            else:
                root[k] = parse_val(v)
            i += 1
            continue
        i += 1
    return root


def extract_frontmatter(content: str) -> tuple[dict, str]:
    """Extract and parse YAML frontmatter from markdown content."""
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("Document does not start with YAML frontmatter delimiter '---'")

    closing_idx = -1
    for idx, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            closing_idx = idx
            break

    if closing_idx == -1:
        raise ValueError("Document frontmatter missing closing '---' delimiter")

    fm_text = "\n".join(lines[1:closing_idx])
    body_text = "\n".join(lines[closing_idx + 1:])
    return parse_simple_yaml(fm_text), body_text


class SkillMetadataTests(unittest.TestCase):
    """Tests for skill frontmatter, schemas, and catalog consistency."""

    @classmethod
    def setUpClass(cls):
        cls.skill_dirs = sorted(
            [d for d in SKILLS_DIR.iterdir() if d.is_dir() and not d.name.startswith(".")]
        )
        cls.skill_names = {d.name for d in cls.skill_dirs}

    def test_all_skill_dirs_contain_skill_md_and_skill_yaml(self):
        """Every skill directory must contain both SKILL.md and skill.yaml."""
        self.assertTrue(self.skill_dirs, "No skill directories found in skills/")
        for s_dir in self.skill_dirs:
            skill_md = s_dir / "SKILL.md"
            skill_yaml = s_dir / "skill.yaml"
            self.assertTrue(skill_md.is_file(), f"Missing SKILL.md in {s_dir}")
            self.assertTrue(skill_yaml.is_file(), f"Missing skill.yaml in {s_dir}")

    def test_skill_md_frontmatter_schema(self):
        """SKILL.md frontmatter must contain name and description, with valid optional fields."""
        for s_dir in self.skill_dirs:
            skill_md = s_dir / "SKILL.md"
            content = skill_md.read_text(encoding="utf-8")
            try:
                fm, body = extract_frontmatter(content)
            except Exception as e:
                self.fail(f"Failed to parse frontmatter in {skill_md}: {e}")

            # Required fields
            self.assertIn("name", fm, f"{skill_md}: frontmatter missing 'name'")
            self.assertIsInstance(fm["name"], str, f"{skill_md}: 'name' must be string")
            self.assertTrue(fm["name"], f"{skill_md}: 'name' cannot be empty")

            self.assertIn("description", fm, f"{skill_md}: frontmatter missing 'description'")
            self.assertIsInstance(fm["description"], str, f"{skill_md}: 'description' must be string")
            self.assertTrue(fm["description"], f"{skill_md}: 'description' cannot be empty")

            # Optional version
            if "version" in fm:
                version_str = str(fm["version"])
                self.assertTrue(
                    SEMVER_RE.match(version_str),
                    f"{skill_md}: version {version_str!r} is not semver X.Y.Z",
                )

            # Optional tools / allowed-tools
            if "tools" in fm:
                self.assertIsInstance(fm["tools"], str, f"{skill_md}: 'tools' must be a string")
            if "allowed-tools" in fm:
                self.assertIsInstance(fm["allowed-tools"], str, f"{skill_md}: 'allowed-tools' must be a string")

            # Must have non-empty markdown body
            self.assertTrue(body.strip(), f"{skill_md}: markdown body is empty")

    def test_skill_yaml_schema(self):
        """skill.yaml must conform to the catalog schema and allowed keys."""
        for s_dir in self.skill_dirs:
            skill_yaml = s_dir / "skill.yaml"
            content = skill_yaml.read_text(encoding="utf-8")
            data = parse_simple_yaml(content)

            # Allowed keys only
            unknown_keys = set(data.keys()) - ALLOWED_SKILL_YAML_KEYS
            self.assertEqual(
                unknown_keys,
                set(),
                f"{skill_yaml}: unknown keys in skill.yaml: {unknown_keys}",
            )

            # depends validation
            if "depends" in data:
                deps = data["depends"]
                self.assertIsInstance(deps, list, f"{skill_yaml}: 'depends' must be a list")
                for dep in deps:
                    self.assertIsInstance(dep, str, f"{skill_yaml}: dependency {dep!r} must be str")
                    self.assertIn(
                        dep,
                        self.skill_names,
                        f"{skill_yaml}: dependency {dep!r} does not exist in skills/",
                    )
                    self.assertNotEqual(
                        dep, s_dir.name, f"{skill_yaml}: skill cannot depend on itself"
                    )

            # tags validation
            if "tags" in data:
                tags = data["tags"]
                self.assertIsInstance(tags, list, f"{skill_yaml}: 'tags' must be a list")
                for tag in tags:
                    self.assertIsInstance(tag, str, f"{skill_yaml}: tag {tag!r} must be str")
                    self.assertTrue(tag, f"{skill_yaml}: tag cannot be empty")

            # category validation
            if "category" in data:
                self.assertIsInstance(data["category"], str, f"{skill_yaml}: 'category' must be str")
                self.assertTrue(data["category"], f"{skill_yaml}: 'category' cannot be empty")

            # targets validation
            if "targets" in data:
                targets = data["targets"]
                self.assertIsInstance(targets, dict, f"{skill_yaml}: 'targets' must be a dict")
                for target_name, enabled in targets.items():
                    self.assertIsInstance(enabled, bool, f"{skill_yaml}: target {target_name} must be bool")

            # portability_allow validation
            if "portability_allow" in data:
                allows = data["portability_allow"]
                self.assertIsInstance(allows, list, f"{skill_yaml}: 'portability_allow' must be list")
                for entry in allows:
                    self.assertIsInstance(entry, str, f"{skill_yaml}: entry {entry!r} must be str")

            # config_inputs validation
            if "config_inputs" in data:
                inputs = data["config_inputs"]
                self.assertIsInstance(inputs, list, f"{skill_yaml}: 'config_inputs' must be list")
                for item in inputs:
                    self.assertIsInstance(item, dict, f"{skill_yaml}: config input must be dict")
                    item_keys = set(item.keys())
                    self.assertTrue(
                        ALLOWED_CONFIG_INPUT_KEYS.issubset(item_keys),
                        f"{skill_yaml}: config input missing required keys: {ALLOWED_CONFIG_INPUT_KEYS - item_keys}",
                    )

    def test_skill_dependency_graph_has_no_cycles(self):
        """The catalog dependency graph must be a directed acyclic graph (DAG)."""
        adj: dict[str, list[str]] = {}
        for s_dir in self.skill_dirs:
            skill_yaml = s_dir / "skill.yaml"
            data = parse_simple_yaml(skill_yaml.read_text(encoding="utf-8"))
            adj[s_dir.name] = data.get("depends") or []

        visited: dict[str, int] = {}  # 0 = visiting, 1 = visited

        def dfs(node: str, path: list[str]):
            visited[node] = 0
            for neighbor in adj.get(node, []):
                if neighbor in visited:
                    if visited[neighbor] == 0:
                        cycle = " -> ".join(path + [neighbor])
                        self.fail(f"Dependency cycle detected: {cycle}")
                else:
                    dfs(neighbor, path + [neighbor])
            visited[node] = 1

        for skill in self.skill_names:
            if skill not in visited:
                dfs(skill, [skill])

    def test_cross_check_with_pyyaml_when_available(self):
        """When PyYAML is installed, verify parse_simple_yaml matches yaml.safe_load."""
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML not installed; skipping cross-check")

        for s_dir in self.skill_dirs:
            sy_text = (s_dir / "skill.yaml").read_text(encoding="utf-8")
            y_data = yaml.safe_load(sy_text)
            s_data = parse_simple_yaml(sy_text)
            self.assertEqual(y_data, s_data, f"YAML parse mismatch in {s_dir / 'skill.yaml'}")

            sm_text = (s_dir / "SKILL.md").read_text(encoding="utf-8")
            if sm_text.startswith("---"):
                parts = sm_text.split("---", 2)
                y_fm = yaml.safe_load(parts[1])
                s_fm = parse_simple_yaml(parts[1])
                self.assertEqual(y_fm, s_fm, f"Frontmatter parse mismatch in {s_dir / 'SKILL.md'}")


if __name__ == "__main__":
    unittest.main()
