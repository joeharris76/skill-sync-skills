#!/usr/bin/env python3
"""Keep the portable role routing in agent-execution equal to the live OMP config.

    routing_sync.py check [PATH ...]   exit 1 when any copy differs from OMP
    routing_sync.py apply              rewrite the catalog skill from OMP

OMP (`omp config get`) is the source of truth. `apply` edits only the catalog
skill; generated copies (BenchBox mirror, global store) are checked, then
refreshed by committing the catalog and re-running skill-sync.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "skills/shared-agent-execution/SKILL.md"
INSTALLED = (
    Path.home() / ".agents/skills/shared-agent-execution/SKILL.md",
    Path.home() / "Developer/BenchBox/.claude/skills/shared-agent-execution/SKILL.md",
)
ROLE_ORDER = ("default", "smol", "slow", "plan", "review", "research", "task", "commit", "vision", "advisor")
USE = {
    "default": "Common implementation and management.",
    "smol": "Simple, mechanical, and scouting work.",
    "slow": "Maximum complexity and special cases.",
    "plan": "Planning and high-capability analysis.",
    "review": "Independent review; filter the author family.",
    "research": "High-capability research and synthesis.",
    "task": "Common delegated implementation.",
    "commit": "Commit-message and changelog generation.",
    "vision": "Image-question helpers; not image generation.",
    "advisor": "Advisory second opinions when enabled.",
}
BLOCK = re.compile(r"(<!-- routing:begin -->\n).*?(<!-- routing:end -->)", re.DOTALL)


def render(roles: dict[str, str], chains: dict[str, list[str]]) -> str:
    names = [name for name in ROLE_ORDER if name in roles] + sorted(set(roles) - set(ROLE_ORDER))
    rows = ["| Role | Primary | Fallbacks, in order | Use for |", "| :--- | :--- | :--- | :--- |"]
    for name in names:
        fallbacks = " → ".join(f"`{item}`" for item in chains.get(name, [])) or "none"
        rows.append(f"| `{name}` | `{roles[name]}` | {fallbacks} | {USE.get(name, '')} |")
    return "\n".join(rows) + "\n"


def splice(text: str, rendered: str) -> str:
    if not BLOCK.search(text):
        raise SystemExit("routing markers not found")
    return BLOCK.sub(lambda match: match.group(1) + rendered + match.group(2), text, count=1)


def omp(key: str):
    done = subprocess.run(["omp", "config", "get", key, "--json"], capture_output=True, text=True, check=True)
    return json.loads(done.stdout)["value"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=("check", "apply"))
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args(argv)
    rendered = render(omp("modelRoles"), omp("retry.fallbackChains"))
    if args.action == "apply":
        CATALOG.write_text(splice(CATALOG.read_text(encoding="utf-8"), rendered), encoding="utf-8")
        print(f"updated {CATALOG}")
        return 0
    drift = 0
    for path in args.paths or [CATALOG, *(p for p in INSTALLED if p.exists())]:
        current = path.read_text(encoding="utf-8")
        if not BLOCK.search(current) or splice(current, rendered) != current:
            print(f"drift: {path}")
            drift = 1
    print("routing differs from OMP" if drift else "routing matches OMP")
    return drift


if __name__ == "__main__":
    sys.exit(main())
