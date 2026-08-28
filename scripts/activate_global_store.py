#!/usr/bin/env python3
"""Atomically point global agent skill loaders at a verified deployment store."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from verify_deployment_store import default_lock_path, verify_managed_payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("store", type=Path)
    parser.add_argument("--lock", type=Path)
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
    store_path = args.store.expanduser().absolute()
    lock_path = (
        args.lock.expanduser().absolute()
        if args.lock is not None
        else default_lock_path(store_path)
    )
    problems = verify_managed_payload(store_path, lock_path)
    if problems:
        details = "\n".join(f"  - {problem}" for problem in problems)
        raise RuntimeError(f"managed payload attestation failed:\n{details}")

    store = store_path.resolve()
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
