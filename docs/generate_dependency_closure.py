#!/usr/bin/env python3
"""Regenerate docs/dependency-closure.md from skill.yaml depends fields.

Source of truth: the `depends:` list in each tracked skill's skill.yaml.
The skill set is every git-tracked `skills/*/skill.yaml` (untracked authoring
work is excluded). Output: docs/dependency-closure.md, a descriptive reference
stating the full transitive closure each consumer must list explicitly now
that distribution no longer resolves dependencies.

Usage:
  python3 docs/generate_dependency_closure.py --write   # regenerate
  python3 docs/generate_dependency_closure.py --check   # fail if stale

Re-run whenever any skills/*/skill.yaml `depends:` list changes.
Requires pyyaml (e.g. `uv run --with pyyaml docs/generate_dependency_closure.py`).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:
    yaml = None

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "dependency-closure.md"


def tracked_skills(root: Path) -> list[str]:
    """Every catalog skill: the git-tracked `skills/*/skill.yaml` directories."""
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "skills/*/skill.yaml"],
        capture_output=True, text=True, check=True,
    ).stdout
    return sorted(line.split("/")[1] for line in out.splitlines() if line)


def load_direct_deps(root: Path) -> tuple[list[str], dict[str, list[str]]]:
    skills = tracked_skills(root)
    direct: dict[str, list[str]] = {}
    for name in skills:
        text = (root / "skills" / name / "skill.yaml").read_text(encoding="utf-8")
        if yaml is not None:
            doc = yaml.safe_load(text) or {}
            deps = doc.get("depends") or []
        else:
            deps = []
            in_depends = False
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith("depends:"):
                    in_depends = True
                    after = stripped[len("depends:"):].strip()
                    if after.startswith("[") and after.endswith("]"):
                        deps = [x.strip() for x in after[1:-1].split(",") if x.strip()]
                        break
                    continue
                if in_depends:
                    if line.startswith("  - ") or line.startswith(" - "):
                        deps.append(line.split("-", 1)[1].strip())
                    elif stripped and not stripped.startswith("#"):
                        break
        direct[name] = sorted(deps)
    return skills, direct


def transitive_closure(name: str, direct: dict[str, list[str]]) -> list[str]:
    seen: set[str] = set()
    stack = list(direct.get(name, []))
    while stack:
        dep = stack.pop()
        if dep in seen:
            continue
        seen.add(dep)
        stack.extend(direct.get(dep, []))
    return sorted(seen)


def render(skills: list[str], direct: dict[str, list[str]]) -> str:
    lines = [
        "# Dependency Closure Reference",
        "",
        "Descriptive reference only. The `depends:` field in each skill's",
        "`skill.yaml` remains the source of truth; this file restates the",
        "transitive closure so a consumer's config can name the complete set.",
        "It is not a resolver, and it changes no `depends:` field.",
        "",
        "## Why this exists",
        "",
        "The `skill-sync` TypeScript CLI was replaced by the vendored shell",
        "rsync wrapper (`tools/skill-sync`), which has no dependency solver:",
        "each consumer's config must name every skill explicitly. A skill that",
        "is not named is not installed, appears in no receipt, and is left",
        "behind as stale unmanaged content.",
        "",
        "Motivating case (consumer side, September 2026): BenchBox's config",
        "names top-level skills but receives `shared-agent-execution` only",
        "transitively, through `bossmode`'s `depends:`. Under explicit",
        "selection that transitive link installs nothing, so",
        "`shared-agent-execution` would be missing from the install and its",
        "receipt while stale copies linger.",
        "",
        "## How to read this table",
        "",
        "- **Direct** lists the skill's own `depends:` from its `skill.yaml`.",
        "- **Transitive closure** is every dependency reachable through those",
        "  entries (dependencies of dependencies included).",
        "- **Explicit set** is the full list a consumer must name: the skill",
        "  itself plus its transitive closure.",
        "- `(none)` means the skill has no dependencies and is installed by",
        "  naming it alone.",
        "",
        "## Closures by skill",
        "",
        "| Skill | Direct `depends:` | Transitive closure | Explicit set to list |",
        "|---|---|---|---|",
    ]
    for name in skills:
        closure = transitive_closure(name, direct)
        explicit = sorted({name} | set(closure))
        fmt = lambda xs: "`" + "`, `".join(xs) + "`" if xs else "(none)"  # noqa: E731
        lines.append(f"| {name} | {fmt(direct[name])} | {fmt(closure)} | {fmt(explicit)} |")
    lines += [
        "",
        "## Staying current",
        "",
        "This file is generated from the `skill.yaml` files. Do not edit the",
        "table by hand. After changing any `depends:` list, regenerate:",
        "",
        "```bash",
        "uv run --with pyyaml docs/generate_dependency_closure.py --write",
        "```",
        "",
        "Verify freshness without writing:",
        "",
        "```bash",
        "uv run --with pyyaml docs/generate_dependency_closure.py --check",
        "```",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    skills, direct = load_direct_deps(ROOT)
    rendered = render(skills, direct)
    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.is_file() else ""
        if current != rendered:
            print(f"{OUTPUT.relative_to(ROOT)} is stale; regenerate with --write", file=sys.stderr)
            return 1
        print(f"{OUTPUT.relative_to(ROOT)} is current")
        return 0
    OUTPUT.write_text(rendered, encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
