#!/usr/bin/env python3
"""Verify the transitional catalog copy matches its pinned product source."""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "skills" / "skill-sync"
MANIFEST = ROOT / "deployment" / "global" / "skill-sync.yaml"
FILES = ("SKILL.md", "skill.yaml", "references/operations.md")


def main() -> int:
    config = yaml.safe_load(MANIFEST.read_text())
    product = next(source for source in config["sources"] if source["name"] == "product")
    base = (
        "https://raw.githubusercontent.com/joeharris76/skill-sync/"
        f"{product['ref']}/{product['subdir']}/skill-sync"
    )
    mismatches = []
    for relative in FILES:
        with urllib.request.urlopen(f"{base}/{relative}", timeout=30) as response:
            expected = response.read()
        if (SKILL_ROOT / relative).read_bytes() != expected:
            mismatches.append(relative)
    if mismatches:
        print(f"product bootstrap drift: {', '.join(mismatches)}", file=sys.stderr)
        return 1
    print(f"product bootstrap matches {product['ref']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
