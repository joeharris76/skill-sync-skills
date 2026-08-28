#!/usr/bin/env python3
"""Attest a generated skill-sync payload without traversing loader-owned .system."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from typing import Any


LOADER_OWNED_ROOT = ".system"
SHA256_RE = re.compile(r"[0-9a-f]{64}")


def default_lock_path(store: Path) -> Path:
    """Return the generated lock for a standard ``<project>/store/skills`` store."""
    if store.name != "skills" or store.parent.name != "store":
        raise ValueError(
            f"cannot infer lock for {store}; expected <project>/store/skills or pass --lock"
        )
    return store.parent.parent / "skill-sync.lock"


def safe_relative_path(value: object, label: str) -> tuple[PurePosixPath | None, str | None]:
    """Validate one normalized, relative POSIX path from the generated lock."""
    if not isinstance(value, str) or not value:
        return None, f"{label} must be a non-empty string"
    if "\x00" in value or "\\" in value:
        return None, f"{label} is not a safe POSIX path: {value!r}"

    path = PurePosixPath(value)
    if (
        path == PurePosixPath(".")
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.as_posix() != value
    ):
        return None, f"{label} is not a normalized relative path: {value!r}"
    return path, None


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expected_payload(lock: object) -> tuple[dict[str, tuple[str, int] | None], set[str], list[str]]:
    """Build the exact managed file and directory inventory declared by a lock."""
    problems: list[str] = []
    expected_files: dict[str, tuple[str, int] | None] = {}
    expected_dirs: set[str] = set()

    if not isinstance(lock, dict):
        return {}, set(), ["lock root must be a JSON object"]
    skills = lock.get("skills")
    if not isinstance(skills, dict):
        return {}, set(), ["lock must contain a skills object"]

    skill_paths: list[PurePosixPath] = []
    for skill_name, skill_entry in sorted(skills.items()):
        skill_path, error = safe_relative_path(skill_name, "skill name")
        if error:
            problems.append(error)
            continue
        assert skill_path is not None
        if skill_path.parts[0] == LOADER_OWNED_ROOT:
            problems.append(
                f"skill name uses reserved loader-owned namespace: {skill_name!r}"
            )
            continue
        skill_paths.append(skill_path)

        if not isinstance(skill_entry, dict) or not isinstance(skill_entry.get("files"), dict):
            problems.append(f"{skill_name}: lock entry must contain a files object")
            continue

        for depth in range(1, len(skill_path.parts) + 1):
            expected_dirs.add(PurePosixPath(*skill_path.parts[:depth]).as_posix())

        for relative_name, metadata in sorted(skill_entry["files"].items()):
            relative_path, error = safe_relative_path(
                relative_name, f"{skill_name} file path"
            )
            if error:
                problems.append(error)
                continue
            assert relative_path is not None
            payload_path = skill_path / relative_path
            payload_name = payload_path.as_posix()
            if payload_name in expected_files:
                problems.append(f"duplicate managed payload path: {payload_name}")
                continue

            parent = payload_path.parent
            while parent != PurePosixPath("."):
                expected_dirs.add(parent.as_posix())
                parent = parent.parent

            if not isinstance(metadata, dict):
                problems.append(f"{payload_name}: metadata must be an object")
                expected_files[payload_name] = None
                continue
            expected_hash = metadata.get("sha256")
            expected_size = metadata.get("size")
            if not isinstance(expected_hash, str) or SHA256_RE.fullmatch(expected_hash) is None:
                problems.append(f"{payload_name}: invalid sha256 in lock")
                expected_files[payload_name] = None
                continue
            if (
                not isinstance(expected_size, int)
                or isinstance(expected_size, bool)
                or expected_size < 0
            ):
                problems.append(f"{payload_name}: invalid size in lock")
                expected_files[payload_name] = None
                continue
            expected_files[payload_name] = (expected_hash, expected_size)

    for index, left in enumerate(skill_paths):
        for right in skill_paths[index + 1 :]:
            if left in right.parents or right in left.parents:
                problems.append(
                    f"overlapping skill directories are unsafe: {left.as_posix()} and {right.as_posix()}"
                )

    return expected_files, expected_dirs, problems


def actual_payload(store: Path) -> tuple[dict[str, Path], set[str], list[str]]:
    """Walk managed payload without statting or traversing exact top-level .system."""
    files: dict[str, Path] = {}
    directories: set[str] = set()
    problems: list[str] = []

    try:
        root_stat = store.lstat()
    except OSError as error:
        return {}, set(), [f"cannot inspect store {store}: {error}"]
    if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
        return {}, set(), [f"store must be a real directory, not a symlink: {store}"]

    stack: list[tuple[Path, PurePosixPath]] = [(store, PurePosixPath("."))]
    while stack:
        directory, relative_directory = stack.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as error:
            problems.append(f"cannot traverse {directory}: {error}")
            continue

        for entry in entries:
            relative_path = (
                PurePosixPath(entry.name)
                if relative_directory == PurePosixPath(".")
                else relative_directory / entry.name
            )
            relative_name = relative_path.as_posix()
            try:
                entry_stat = entry.stat(follow_symlinks=False)
            except OSError as error:
                problems.append(f"cannot inspect managed path {relative_name}: {error}")
                continue

            if (
                relative_directory == PurePosixPath(".")
                and entry.name == LOADER_OWNED_ROOT
                and stat.S_ISDIR(entry_stat.st_mode)
            ):
                continue
            if stat.S_ISLNK(entry_stat.st_mode):
                problems.append(f"symlink is not allowed in managed payload: {relative_name}")
            elif stat.S_ISDIR(entry_stat.st_mode):
                directories.add(relative_name)
                stack.append((Path(entry.path), relative_path))
            elif stat.S_ISREG(entry_stat.st_mode):
                files[relative_name] = Path(entry.path)
            else:
                problems.append(f"special file is not allowed in managed payload: {relative_name}")

    return files, directories, problems


def verify_managed_payload(store: Path, lock_path: Path) -> list[str]:
    """Return attestation problems; an empty list means the managed payload matches."""
    try:
        lock_stat = lock_path.lstat()
    except OSError as error:
        return [f"cannot inspect generated lock {lock_path}: {error}"]
    if stat.S_ISLNK(lock_stat.st_mode) or not stat.S_ISREG(lock_stat.st_mode):
        return [f"generated lock must be a real file, not a symlink: {lock_path}"]
    try:
        lock: Any = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return [f"cannot read generated lock {lock_path}: {error}"]

    expected_files, expected_dirs, problems = expected_payload(lock)
    actual_files, actual_dirs, actual_problems = actual_payload(store)
    problems.extend(actual_problems)

    for relative_name in sorted(set(expected_files) - set(actual_files)):
        problems.append(f"managed file is missing: {relative_name}")
    for relative_name in sorted(set(actual_files) - set(expected_files)):
        problems.append(f"unexpected managed file: {relative_name}")
    for relative_name in sorted(expected_dirs - actual_dirs):
        problems.append(f"managed directory is missing: {relative_name}")
    for relative_name in sorted(actual_dirs - expected_dirs):
        problems.append(f"unexpected managed directory: {relative_name}")

    for relative_name in sorted(set(expected_files) & set(actual_files)):
        metadata = expected_files[relative_name]
        if metadata is None:
            continue
        expected_hash, expected_size = metadata
        path = actual_files[relative_name]
        actual_size = path.stat().st_size
        if actual_size != expected_size:
            problems.append(
                f"managed file size mismatch: {relative_name} ({actual_size} != {expected_size})"
            )
        actual_hash = sha256_of(path)
        if actual_hash != expected_hash:
            problems.append(f"managed file sha256 mismatch: {relative_name}")

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("store", type=Path)
    parser.add_argument("--lock", type=Path)
    args = parser.parse_args()

    store = args.store.expanduser().absolute()
    try:
        lock_path = (
            args.lock.expanduser().absolute()
            if args.lock is not None
            else default_lock_path(store)
        )
    except ValueError as error:
        print(f"managed payload attestation failed: {error}", file=sys.stderr)
        return 1

    problems = verify_managed_payload(store, lock_path)
    if problems:
        print(
            f"managed payload attestation failed at {store} ({len(problems)} problem(s)):",
            file=sys.stderr,
        )
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print(f"managed payload matches generated lock: {store}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
