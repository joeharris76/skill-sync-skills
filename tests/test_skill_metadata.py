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
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"

sys.path.insert(0, str(ROOT))
from docs.generate_dependency_closure import parse_deps_from_yaml

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
    if val.startswith("[") and val.endswith("]"):
        inner = val[1:-1].strip()
        if not inner:
            return []
        return [parse_val(item.strip()) for item in inner.split(",") if item.strip()]
    if val.isdigit():
        return int(val)
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        return val[1:-1]
    return val


def parse_simple_yaml(text: str) -> dict:
    """Parse the clean subset of YAML used by skill.yaml and SKILL.md frontmatter.

    Supports top-level key-values, lists of scalars, mappings of scalar booleans,
    and lists of small dictionaries (e.g. config_inputs).
    Rejects malformed lines, unquoted colons in scalars, and invalid list items.
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
            raw_val = line.lstrip()[2:].strip()
            if current_list is None:
                current_list = []
                root[current_key] = current_list

            is_quoted = (raw_val.startswith('"') and raw_val.endswith('"')) or (
                raw_val.startswith("'") and raw_val.endswith("'")
            )
            # Quoted items are scalar strings; unquoted items with ": " or ending with ":" are dicts
            if not is_quoted and (": " in raw_val or raw_val.endswith(":")):
                k, _, v = raw_val.partition(":")
                val_to_parse = v.strip()
                if not (val_to_parse.startswith('"') or val_to_parse.startswith("'")):
                    val_to_parse = val_to_parse.split("#", 1)[0].strip()
                item_dict = {k.strip(): parse_val(val_to_parse)}
                current_list.append(item_dict)
                current_dict_in_list = item_dict
            else:
                val_to_parse = raw_val
                if not is_quoted:
                    val_to_parse = val_to_parse.split("#", 1)[0].strip()
                current_list.append(parse_val(val_to_parse))
                current_dict_in_list = None
            i += 1
            continue

        # Nested keys inside a dict inside a list (e.g. config_inputs item properties)
        if indent >= 4 and current_dict_in_list is not None and ":" in stripped:
            k, _, v = stripped.partition(":")
            k = k.strip()
            v = v.strip()
            if " " in k:
                raise ValueError(f"Invalid key containing space on line {i+1}: {k!r}")
            if not (v.startswith('"') or v.startswith("'")):
                if ": " in v:
                    raise ValueError(f"Unquoted ': ' in scalar value on line {i+1}: {v!r}")
                v = v.split("#", 1)[0].strip()
            current_dict_in_list[k] = parse_val(v)
            i += 1
            continue

        # Nested mapping under current_key (e.g. targets: claude: true)
        if indent >= 2 and current_key is not None and isinstance(root.get(current_key), dict) and ":" in stripped:
            k, _, v = stripped.partition(":")
            k = k.strip()
            v = v.strip()
            if " " in k:
                raise ValueError(f"Invalid key containing space on line {i+1}: {k!r}")
            if not (v.startswith('"') or v.startswith("'")):
                if ": " in v:
                    raise ValueError(f"Unquoted ': ' in scalar value on line {i+1}: {v!r}")
                v = v.split("#", 1)[0].strip()
            root[current_key][k] = parse_val(v)
            i += 1
            continue

        # Top-level or sub-level key
        if ":" in stripped:
            k, _, v = stripped.partition(":")
            k = k.strip()
            v = v.strip()
            if " " in k or k.startswith("-"):
                raise ValueError(f"Invalid key on line {i+1}: {k!r}")
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
                if not (v.startswith('"') or v.startswith("'")):
                    if ": " in v:
                        raise ValueError(f"Unquoted ': ' in scalar value on line {i+1}: {v!r}")
                    v = v.split("#", 1)[0].strip()
                root[k] = parse_val(v)
            i += 1
            continue

        raise ValueError(f"Malformed or unrecognized YAML syntax on line {i+1}: {line!r}")
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
        try:
            res = subprocess.run(
                ["git", "ls-files", "skills/*/skill.yaml"],
                cwd=ROOT, capture_output=True, text=True, check=True,
            )
            cls.skill_names = {line.split("/")[1] for line in res.stdout.splitlines() if line}
            cls.skill_dirs = sorted([SKILLS_DIR / name for name in cls.skill_names])
        except Exception:
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
                    extra_keys = item_keys - ALLOWED_CONFIG_INPUT_KEYS
                    self.assertEqual(
                        extra_keys,
                        set(),
                        f"{skill_yaml}: config input contains unexpected keys: {extra_keys}",
                    )
                    missing_keys = ALLOWED_CONFIG_INPUT_KEYS - item_keys
                    self.assertEqual(
                        missing_keys,
                        set(),
                        f"{skill_yaml}: config input missing required keys: {missing_keys}",
                    )
                    self.assertIsInstance(item["key"], str, f"{skill_yaml}: config input 'key' must be str")
                    self.assertTrue(item["key"], f"{skill_yaml}: config input 'key' cannot be empty")
                    self.assertIn(
                        item["type"],
                        {"string", "number", "boolean"},
                        f"{skill_yaml}: config input 'type' must be string/number/boolean, got {item['type']!r}",
                    )
                    self.assertIsInstance(item["description"], str, f"{skill_yaml}: config input 'description' must be str")
                    self.assertTrue(item["description"], f"{skill_yaml}: config input 'description' cannot be empty")

    def test_dependency_closure_document_is_synchronized(self):
        """docs/dependency-closure.md must match generate_dependency_closure.py output."""
        gen_script = ROOT / "docs" / "generate_dependency_closure.py"
        res = subprocess.run(
            [sys.executable, str(gen_script), "--check"],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        self.assertEqual(
            res.returncode,
            0,
            f"docs/dependency-closure.md is stale or out of sync with skill.yaml:\n{res.stdout}\n{res.stderr}\n"
            "Run: python3 docs/generate_dependency_closure.py --write",
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

    def test_parse_simple_yaml_inline_list_and_edge_cases(self):
        """Test parser handles inline lists, empty lists, numbers, and boolean literals."""
        sample = (
            "depends: [shared-change-framework, shared-review-protocol]\n"
            "tags: []\n"
            "targets:\n"
            "  claude: true\n"
            "  codex: false\n"
        )
        parsed = parse_simple_yaml(sample)
        self.assertEqual(
            parsed["depends"], ["shared-change-framework", "shared-review-protocol"]
        )
        self.assertEqual(parsed["tags"], [])
        self.assertEqual(parsed["targets"], {"claude": True, "codex": False})

    def test_generator_parser_matches_metadata_parser(self):
        """The fallback parser in docs/generate_dependency_closure.py must agree with test parser."""
        for s_dir in self.skill_dirs:
            sy_text = (s_dir / "skill.yaml").read_text(encoding="utf-8")
            from_gen = parse_deps_from_yaml(sy_text)
            from_test = sorted(parse_simple_yaml(sy_text).get("depends") or [])
            self.assertEqual(
                from_gen,
                from_test,
                f"Dependency parser mismatch in {s_dir / 'skill.yaml'}: {from_gen} vs {from_test}",
            )

        # Test various YAML edge-case formats
        fixture_4space = (
            "depends:\n"
            "    - first\n"
            "    - 'second' # inline comment\n"
            "    - \"third\"\n"
        )
        self.assertEqual(parse_deps_from_yaml(fixture_4space), ["first", "second", "third"])

    def test_parse_simple_yaml_rejects_malformed_syntax(self):
        """YAML parser must reject malformed lines and unquoted colons in values."""
        with self.assertRaises(ValueError):
            parse_simple_yaml("malformed line without colon")

        with self.assertRaises(ValueError):
            parse_simple_yaml("name: invalid\ndescription: unquoted: colon in value")

        with self.assertRaises(ValueError):
            parse_simple_yaml("invalid key with space: true")

        # Quoted strings containing colons in list items must remain scalar strings
        sample_quoted = "items:\n  - \"foo: bar\"\n  - 'another: item'\n"
        parsed = parse_simple_yaml(sample_quoted)
        self.assertEqual(parsed["items"], ["foo: bar", "another: item"])


if __name__ == "__main__":
    unittest.main()

