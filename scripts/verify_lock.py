#!/usr/bin/env python3
"""Enforce the same-commit lock invariant for skill-sync-skills.

The lock is a tracked snapshot: ``skill-sync.lock`` records a sha256 and size
for every file of every managed skill. That is only meaningful if the lock and
the skill tree are committed *together*. A commit that edits a skill but keeps
the old lock, or that adds a file the lock has never seen, ships a snapshot that
describes something other than what is in the tree — and nothing downstream can
tell, because consumers trust the lock.

This checker makes that invariant mechanical. It fails when:

  * a skill declared in ``skill-sync.yaml`` is absent from the lock;
  * a skill present in the lock is not declared in the manifest;
  * a file recorded in the lock is missing from the tree;
  * a recorded sha256 or size disagrees with the file on disk;
  * a file exists under a locked skill's directory but the lock does not
    record it.

The last case is the one a hash comparison alone cannot catch: adding a file
without regenerating the lock leaves every recorded hash correct.

Use ``--write`` to refresh file metadata and ``lockedAt`` while preserving the
lock's provenance and install metadata. The writer refuses to change the set of
skills because adding or removing a skill requires a provenance-aware workflow.

Usage: uv run --with pyyaml scripts/verify_lock.py [--root DIR] [--write]
Exits 0 when the lock matches the tree, 1 otherwise.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import sys
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - depends on the interpreter
    sys.exit("verify_lock: run with `uv run --with pyyaml scripts/verify_lock.py`")

# Editor and OS droppings are never part of a skill's content.
IGNORED_NAMES = frozenset({".DS_Store"})
IGNORED_DIRS = frozenset({"__pycache__", ".git"})


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tracked_files(skill_dir: Path) -> set[str]:
    """Every content file under a skill, as lock-relative POSIX paths."""
    found: set[str] = set()
    for path in skill_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.name in IGNORED_NAMES:
            continue
        if IGNORED_DIRS.intersection(path.relative_to(skill_dir).parts):
            continue
        found.add(path.relative_to(skill_dir).as_posix())
    return found


def load_catalog(root: Path) -> tuple[Path, dict, list[str]]:
    """Load the lock and manifest, returning structural problems separately."""
    lock_path = root / "skill-sync.lock"
    manifest_path = root / "skill-sync.yaml"
    for required in (lock_path, manifest_path):
        if not required.is_file():
            return lock_path, {}, [f"missing {required.name} at {required}"]

    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    locked_skills = lock.get("skills") or {}
    declared_skills = manifest.get("skills") or []
    problems: list[str] = []

    for name in sorted(set(declared_skills) - set(locked_skills)):
        problems.append(f"{name}: declared in skill-sync.yaml but absent from the lock")
    for name in sorted(set(locked_skills) - set(declared_skills)):
        problems.append(f"{name}: present in the lock but not declared in skill-sync.yaml")

    return lock_path, lock, problems


def write_lock(root: Path) -> list[str]:
    """Refresh file metadata atomically; return problems without writing on error."""
    lock_path, lock, problems = load_catalog(root)
    if problems:
        return problems

    locked_skills = lock.get("skills") or {}
    refreshed_files: dict[str, dict[str, dict[str, str | int]]] = {}
    for name in sorted(locked_skills):
        skill_dir = root / "skills" / name
        if not skill_dir.is_dir():
            problems.append(f"{name}: locked but {skill_dir.relative_to(root)} does not exist")
            continue
        refreshed_files[name] = {
            relpath: {
                "sha256": sha256_of(skill_dir / relpath),
                "size": (skill_dir / relpath).stat().st_size,
            }
            for relpath in sorted(tracked_files(skill_dir))
        }

    if problems:
        return problems

    for name, files in refreshed_files.items():
        locked_skills[name]["files"] = files
    lock["lockedAt"] = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    temporary_path = lock_path.with_name(f".{lock_path.name}.tmp")
    try:
        temporary_path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary_path, lock_path)
    finally:
        temporary_path.unlink(missing_ok=True)

    return []


def verify(root: Path) -> list[str]:
    """Return a list of problems; empty means the lock matches the tree."""
    problems: list[str] = []

    lock_path, lock, problems = load_catalog(root)
    if problems and not lock:
        return problems
    locked_skills = lock.get("skills") or {}

    # 3/4/5. Every locked skill's files must match the tree exactly.
    for name in sorted(locked_skills):
        skill_dir = root / "skills" / name
        recorded = locked_skills[name].get("files") or {}

        if not skill_dir.is_dir():
            problems.append(f"{name}: locked but {skill_dir.relative_to(root)} does not exist")
            continue

        on_disk = tracked_files(skill_dir)

        for relpath in sorted(set(on_disk) - set(recorded)):
            problems.append(f"{name}/{relpath}: file is in the tree but not in the lock; regenerate the lock")

        for relpath in sorted(recorded):
            entry = recorded[relpath]
            target = skill_dir / relpath
            if not target.is_file():
                problems.append(f"{name}/{relpath}: recorded in the lock but missing from the tree")
                continue
            actual_size = target.stat().st_size
            if actual_size != entry.get("size"):
                problems.append(f"{name}/{relpath}: size {actual_size} != locked {entry.get('size')}")
            actual_sha = sha256_of(target)
            if actual_sha != entry.get("sha256"):
                problems.append(
                    f"{name}/{relpath}: sha256 {actual_sha[:12]}… != locked {str(entry.get('sha256'))[:12]}…"
                )

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="repository root (defaults to the checkout containing this script)",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="refresh file hashes, sizes, and lockedAt without changing skill provenance",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    if args.write:
        write_problems = write_lock(root)
        if write_problems:
            print(f"skill-sync lock was not written at {root} ({len(write_problems)} problem(s)):", file=sys.stderr)
            for problem in write_problems:
                print(f"  - {problem}", file=sys.stderr)
            print("\nResolve manifest, lock, or skill-directory structure before regenerating.", file=sys.stderr)
            return 1

    problems = verify(root)

    if problems:
        print(f"skill-sync lock is out of date with the tree at {root} ({len(problems)} problem(s)):", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        print("\nRegenerate the lock and commit it in the SAME commit as the skill changes.", file=sys.stderr)
        return 1

    skill_count = len(json.loads((root / "skill-sync.lock").read_text(encoding="utf-8")).get("skills") or {})
    print(f"skill-sync lock matches the tree: {skill_count} skill(s) verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
