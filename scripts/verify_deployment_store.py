#!/usr/bin/env python3
"""Attest managed skills while leaving loader-owned ``.system`` untraversed."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
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
DIRECTORY_OPEN_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
FILE_OPEN_FLAGS = os.O_RDONLY | os.O_NOFOLLOW


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


def _object_identity(value: os.stat_result) -> tuple[int, int, int]:
    return value.st_dev, value.st_ino, stat.S_IFMT(value.st_mode)


def _same_object(left: os.stat_result, right: os.stat_result) -> bool:
    return _object_identity(left) == _object_identity(right)


def _same_snapshot(left: os.stat_result, right: os.stat_result) -> bool:
    return _same_object(left, right) and (
        left.st_size,
        left.st_mtime_ns,
        left.st_ctime_ns,
    ) == (
        right.st_size,
        right.st_mtime_ns,
        right.st_ctime_ns,
    )


def _read_regular_file_at(
    directory_fd: int, name: str, before: os.stat_result, relative_name: str
) -> tuple[tuple[str, int] | None, list[str]]:
    """Hash one already-open regular file and prove the path still names its inode."""
    problems: list[str] = []
    try:
        file_fd = os.open(name, FILE_OPEN_FLAGS, dir_fd=directory_fd)
    except OSError as error:
        return None, [f"cannot open managed file {relative_name} without following links: {error}"]

    try:
        opened = os.fstat(file_fd)
        if not stat.S_ISREG(opened.st_mode) or not _same_object(before, opened):
            return None, [f"managed file changed inode or type while opening: {relative_name}"]

        digest = hashlib.sha256()
        size = 0
        while True:
            chunk = os.read(file_fd, 1 << 20)
            if not chunk:
                break
            size += len(chunk)
            digest.update(chunk)

        after_read = os.fstat(file_fd)
        if not _same_snapshot(opened, after_read):
            problems.append(f"managed file changed while reading: {relative_name}")
        try:
            after_path = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except OSError as error:
            problems.append(f"managed file changed after reading {relative_name}: {error}")
        else:
            if not _same_object(opened, after_path) or not stat.S_ISREG(after_path.st_mode):
                problems.append(f"managed file path changed inode or type: {relative_name}")
        return (digest.hexdigest(), size), problems
    finally:
        os.close(file_fd)


def _scan_directory(
    directory_fd: int,
    relative_directory: PurePosixPath,
    files: dict[str, tuple[str, int]],
    directories: set[str],
    problems: list[str],
) -> None:
    """Traverse from directory descriptors; every child open refuses symlinks."""
    try:
        entries = sorted(os.scandir(directory_fd), key=lambda entry: entry.name)
    except OSError as error:
        label = relative_directory.as_posix()
        problems.append(f"cannot traverse managed directory {label}: {error}")
        return

    for entry in entries:
        relative_path = (
            PurePosixPath(entry.name)
            if relative_directory == PurePosixPath(".")
            else relative_directory / entry.name
        )
        relative_name = relative_path.as_posix()
        try:
            entry_stat = os.stat(entry.name, dir_fd=directory_fd, follow_symlinks=False)
        except OSError as error:
            problems.append(f"cannot inspect managed path {relative_name}: {error}")
            continue

        if relative_directory == PurePosixPath(".") and entry.name == LOADER_OWNED_ROOT:
            # Type is checked with lstat semantics. Loader-owned contents are never
            # opened, traversed, hashed, sized, or otherwise read.
            if not stat.S_ISDIR(entry_stat.st_mode):
                problems.append(
                    f"loader-owned {LOADER_OWNED_ROOT} must be a real directory; "
                    "symlink is not allowed"
                )
            continue
        if stat.S_ISLNK(entry_stat.st_mode):
            problems.append(f"symlink is not allowed in managed payload: {relative_name}")
            continue
        if stat.S_ISREG(entry_stat.st_mode):
            payload, file_problems = _read_regular_file_at(
                directory_fd, entry.name, entry_stat, relative_name
            )
            problems.extend(file_problems)
            if payload is not None:
                files[relative_name] = payload
            continue
        if not stat.S_ISDIR(entry_stat.st_mode):
            problems.append(f"special file is not allowed in managed payload: {relative_name}")
            continue

        try:
            child_fd = os.open(entry.name, DIRECTORY_OPEN_FLAGS, dir_fd=directory_fd)
        except OSError as error:
            problems.append(
                f"cannot open managed directory {relative_name} without following links: {error}"
            )
            continue
        try:
            opened = os.fstat(child_fd)
            if not stat.S_ISDIR(opened.st_mode) or not _same_object(entry_stat, opened):
                problems.append(
                    f"managed directory changed inode or type while opening: {relative_name}"
                )
                continue
            directories.add(relative_name)
            _scan_directory(child_fd, relative_path, files, directories, problems)
            after_scan = os.fstat(child_fd)
            if not _same_snapshot(opened, after_scan):
                problems.append(f"managed directory changed while traversing: {relative_name}")
            try:
                after_path = os.stat(
                    entry.name, dir_fd=directory_fd, follow_symlinks=False
                )
            except OSError as error:
                problems.append(
                    f"managed directory changed after traversal {relative_name}: {error}"
                )
            else:
                if not _same_object(opened, after_path) or not stat.S_ISDIR(after_path.st_mode):
                    problems.append(
                        f"managed directory path changed inode or type: {relative_name}"
                    )
        finally:
            os.close(child_fd)


def _read_lock(lock_path: Path) -> tuple[Any | None, list[str]]:
    try:
        before = lock_path.lstat()
    except OSError as error:
        return None, [f"cannot inspect generated lock {lock_path}: {error}"]
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        return None, [f"generated lock must be a real file, not a symlink: {lock_path}"]
    try:
        lock_fd = os.open(lock_path, FILE_OPEN_FLAGS)
    except OSError as error:
        return None, [f"cannot open generated lock without following links {lock_path}: {error}"]
    try:
        opened = os.fstat(lock_fd)
        if not stat.S_ISREG(opened.st_mode) or not _same_object(before, opened):
            return None, [f"generated lock changed inode or type while opening: {lock_path}"]
        chunks: list[bytes] = []
        while True:
            chunk = os.read(lock_fd, 1 << 20)
            if not chunk:
                break
            chunks.append(chunk)
        after_read = os.fstat(lock_fd)
        if not _same_snapshot(opened, after_read):
            return None, [f"generated lock changed while reading: {lock_path}"]
        try:
            after_path = lock_path.lstat()
        except OSError as error:
            return None, [f"generated lock changed after reading {lock_path}: {error}"]
        if not _same_object(opened, after_path) or not stat.S_ISREG(after_path.st_mode):
            return None, [f"generated lock path changed inode or type: {lock_path}"]
        try:
            return json.loads(b"".join(chunks).decode("utf-8")), []
        except (UnicodeError, json.JSONDecodeError) as error:
            return None, [f"cannot read generated lock {lock_path}: {error}"]
    finally:
        os.close(lock_fd)


@dataclass
class AttestedStore:
    """An attested store whose root descriptor stays open through activation."""

    path: Path
    root_fd: int
    root_stat: os.stat_result
    expected_files: dict[str, tuple[str, int] | None]
    expected_dirs: set[str]

    def close(self) -> None:
        if self.root_fd >= 0:
            os.close(self.root_fd)
            self.root_fd = -1

    def __enter__(self) -> AttestedStore:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @property
    def identity(self) -> tuple[int, int, int]:
        return _object_identity(self.root_stat)

    def assert_path_identity(self) -> None:
        """Reject replacement of the path that will be exposed to loaders."""
        try:
            current = self.path.lstat()
        except OSError as error:
            raise RuntimeError(f"attested store path changed: {self.path}: {error}") from error
        if not stat.S_ISDIR(current.st_mode) or _object_identity(current) != self.identity:
            raise RuntimeError(f"attested store path changed inode or type: {self.path}")

    def check_payload(self) -> list[str]:
        """Recheck exact managed contents through the held root descriptor."""
        problems: list[str] = []
        try:
            scan_fd = os.open(".", DIRECTORY_OPEN_FLAGS, dir_fd=self.root_fd)
        except OSError as error:
            return [f"cannot reopen attested store descriptor: {error}"]
        try:
            opened = os.fstat(scan_fd)
            if _object_identity(opened) != self.identity:
                return ["attested store descriptor changed inode or type"]
            actual_files: dict[str, tuple[str, int]] = {}
            actual_dirs: set[str] = set()
            _scan_directory(
                scan_fd,
                PurePosixPath("."),
                actual_files,
                actual_dirs,
                problems,
            )
        finally:
            os.close(scan_fd)

        for relative_name in sorted(set(self.expected_files) - set(actual_files)):
            problems.append(f"managed file is missing: {relative_name}")
        for relative_name in sorted(set(actual_files) - set(self.expected_files)):
            problems.append(f"unexpected managed file: {relative_name}")
        for relative_name in sorted(self.expected_dirs - actual_dirs):
            problems.append(f"managed directory is missing: {relative_name}")
        for relative_name in sorted(actual_dirs - self.expected_dirs):
            problems.append(f"unexpected managed directory: {relative_name}")

        for relative_name in sorted(set(self.expected_files) & set(actual_files)):
            expected = self.expected_files[relative_name]
            if expected is None:
                continue
            expected_hash, expected_size = expected
            actual_hash, actual_size = actual_files[relative_name]
            if actual_size != expected_size:
                problems.append(
                    f"managed file size mismatch: {relative_name} ({actual_size} != {expected_size})"
                )
            if actual_hash != expected_hash:
                problems.append(f"managed file sha256 mismatch: {relative_name}")

        try:
            self.assert_path_identity()
        except RuntimeError as error:
            problems.append(str(error))
        return problems


def attest_managed_payload(
    store: Path, lock_path: Path
) -> tuple[AttestedStore | None, list[str]]:
    """Open and attest a store, returning a held root descriptor on success."""
    lock, lock_problems = _read_lock(lock_path)
    if lock_problems:
        return None, lock_problems
    expected_files, expected_dirs, problems = expected_payload(lock)
    if problems:
        return None, problems

    try:
        root_fd = os.open(store, DIRECTORY_OPEN_FLAGS)
    except OSError as error:
        return None, [f"store must be an openable real directory, not a symlink: {store}: {error}"]
    root_stat = os.fstat(root_fd)
    attestation = AttestedStore(
        path=store,
        root_fd=root_fd,
        root_stat=root_stat,
        expected_files=expected_files,
        expected_dirs=expected_dirs,
    )
    problems = attestation.check_payload()
    if problems:
        attestation.close()
        return None, problems
    return attestation, []


def verify_managed_payload(store: Path, lock_path: Path) -> list[str]:
    """Return attestation problems; an empty list means the managed payload matches."""
    attestation, problems = attest_managed_payload(store, lock_path)
    if attestation is not None:
        attestation.close()
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
