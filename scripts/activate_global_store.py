#!/usr/bin/env python3
"""Atomically point global agent skill loaders at a verified deployment store."""

from __future__ import annotations

import argparse
import os
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("store", type=Path)
    parser.add_argument("--link", action="append", type=Path)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def replace_link(link: Path, store: Path) -> None:
    if os.path.lexists(link) and not link.is_symlink():
        raise RuntimeError(f"refusing to replace non-symlink: {link}")
    link.parent.mkdir(parents=True, exist_ok=True)
    temporary = link.with_name(f".{link.name}.skill-sync-{os.getpid()}")
    temporary.symlink_to(store, target_is_directory=True)
    os.replace(temporary, link)


def main() -> int:
    args = parse_args()
    store = args.store.expanduser().resolve()
    if not (store / "skill-sync" / "SKILL.md").is_file():
        raise RuntimeError(f"store lacks skill-sync/SKILL.md: {store}")

    links = args.link or [Path("~/.claude/skills"), Path("~/.codex/skills")]
    for raw_link in links:
        link = raw_link.expanduser()
        print(f"{link} -> {store}")
        if args.apply:
            replace_link(link, store)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
