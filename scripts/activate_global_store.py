#!/usr/bin/env python3
"""Atomically point global agent skill loaders at a verified deployment store."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import stat

try:
    from .verify_deployment_store import (
        AttestedStore,
        attest_managed_payload,
        default_lock_path,
    )
except ImportError:  # Direct script execution.
    from verify_deployment_store import (  # type: ignore[no-redef]
        AttestedStore,
        attest_managed_payload,
        default_lock_path,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("store", type=Path)
    parser.add_argument("--lock", type=Path)
    parser.add_argument("--link", action="append", type=Path)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


@dataclass(frozen=True)
class LoaderState:
    path: Path
    prior_target: str | None

    @property
    def existed(self) -> bool:
        return self.prior_target is not None


def _loader_state(path: Path) -> LoaderState:
    try:
        current = path.lstat()
    except FileNotFoundError:
        return LoaderState(path=path, prior_target=None)
    except OSError as error:
        raise RuntimeError(f"cannot inspect loader target {path}: {error}") from error
    if not stat.S_ISLNK(current.st_mode):
        raise RuntimeError(f"refusing to replace non-symlink: {path}")
    try:
        return LoaderState(path=path, prior_target=os.readlink(path))
    except OSError as error:
        raise RuntimeError(f"cannot read loader symlink {path}: {error}") from error


def preflight_loaders(links: list[Path]) -> tuple[list[LoaderState], list[Path]]:
    """Validate every target and parent before any filesystem change."""
    if len(set(links)) != len(links):
        raise RuntimeError("duplicate loader targets are not allowed")
    for index, left in enumerate(links):
        for right in links[index + 1 :]:
            if left in right.parents or right in left.parents:
                raise RuntimeError(f"overlapping loader targets are unsafe: {left} and {right}")

    states: list[LoaderState] = []
    missing_parents: set[Path] = set()
    for link in links:
        states.append(_loader_state(link))
        parent = link.parent
        while True:
            try:
                parent_stat = parent.lstat()
            except FileNotFoundError:
                missing_parents.add(parent)
                if parent == parent.parent:
                    raise RuntimeError(f"cannot find an existing loader parent for {link}")
                parent = parent.parent
                continue
            except OSError as error:
                raise RuntimeError(f"cannot inspect loader parent {parent}: {error}") from error
            if not stat.S_ISDIR(parent_stat.st_mode) and not parent.is_dir():
                raise RuntimeError(f"loader parent must be a real directory: {parent}")
            break

    return states, sorted(missing_parents, key=lambda path: len(path.parts))


def _assert_loader_state(state: LoaderState) -> None:
    current = _loader_state(state.path)
    if current.prior_target != state.prior_target:
        raise RuntimeError(f"loader target changed after preflight: {state.path}")


def _temporary_link_path(link: Path) -> Path:
    for suffix in range(1000):
        candidate = link.with_name(
            f".{link.name}.skill-sync-{os.getpid()}-{suffix}"
        )
        if not os.path.lexists(candidate):
            return candidate
    raise RuntimeError(f"cannot allocate temporary loader link beside {link}")


def _atomic_symlink(link: Path, target: str) -> None:
    temporary = _temporary_link_path(link)
    try:
        temporary.symlink_to(target, target_is_directory=True)
        os.replace(temporary, link)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def replace_link(state: LoaderState, store: Path) -> None:
    _assert_loader_state(state)
    _atomic_symlink(state.path, str(store))


def _loader_exposes_attested_store(
    link: Path, store: Path, attestation: AttestedStore
) -> None:
    current = _loader_state(link)
    if current.prior_target != str(store):
        raise RuntimeError(f"loader does not point to the attested store path: {link}")
    try:
        exposed_fd = os.open(link, os.O_RDONLY | os.O_DIRECTORY)
    except OSError as error:
        raise RuntimeError(f"cannot open loader target {link}: {error}") from error
    try:
        exposed = os.fstat(exposed_fd)
        identity = (exposed.st_dev, exposed.st_ino, stat.S_IFMT(exposed.st_mode))
        if identity != attestation.identity:
            raise RuntimeError(f"loader does not expose the attested store identity: {link}")
    finally:
        os.close(exposed_fd)


def _rollback_loader(state: LoaderState, store: Path) -> None:
    current = _loader_state(state.path)
    if current.prior_target != str(store):
        raise RuntimeError(f"cannot safely roll back replaced loader: {state.path}")
    if state.existed:
        assert state.prior_target is not None
        _atomic_symlink(state.path, state.prior_target)
    else:
        state.path.unlink()


def _rollback_changed_loaders(states: list[LoaderState], store: Path) -> list[str]:
    """Restore every target that differs from its preflight snapshot."""
    problems: list[str] = []
    for state in reversed(states):
        try:
            current = _loader_state(state.path)
            if current.prior_target == state.prior_target:
                continue
            if current.prior_target != str(store):
                raise RuntimeError(
                    f"loader changed to an unexpected state during activation: {state.path}"
                )
            _rollback_loader(state, store)
        except Exception as error:
            problems.append(str(error))
    return problems


def _remove_created_parents(created: list[Path]) -> list[str]:
    problems: list[str] = []
    for parent in reversed(created):
        try:
            parent.rmdir()
        except FileNotFoundError:
            continue
        except OSError as error:
            problems.append(f"cannot restore absent loader parent {parent}: {error}")
    return problems


def _raise_attestation(problems: list[str]) -> None:
    details = "\n".join(f"  - {problem}" for problem in problems)
    raise RuntimeError(f"managed payload attestation failed:\n{details}")


def activate_store(store: Path, lock_path: Path, links: list[Path], apply: bool) -> None:
    """Attest, preflight, and activate all loaders as one rollback-safe operation."""
    states, planned_parents = preflight_loaders(links)
    attestation, problems = attest_managed_payload(store, lock_path)
    if problems:
        _raise_attestation(problems)
    assert attestation is not None

    with attestation:
        if "skill-sync/SKILL.md" not in attestation.expected_files:
            raise RuntimeError("generated lock lacks skill-sync/SKILL.md")
        for link in links:
            print(f"{link} -> {store}")
        if not apply:
            return

        created_parents: list[Path] = []
        try:
            for parent in planned_parents:
                parent.mkdir()
                created_parents.append(parent)
            for state in states:
                attestation.assert_path_identity()
                current_problems = attestation.check_payload()
                if current_problems:
                    _raise_attestation(current_problems)
                replace_link(state, store)
                _loader_exposes_attested_store(state.path, store, attestation)
            attestation.assert_path_identity()
            final_problems = attestation.check_payload()
            if final_problems:
                _raise_attestation(final_problems)
            for state in states:
                _loader_exposes_attested_store(state.path, store, attestation)
        except Exception as error:
            rollback_problems = _rollback_changed_loaders(states, store)
            rollback_problems.extend(_remove_created_parents(created_parents))
            if rollback_problems:
                details = "\n".join(f"  - {problem}" for problem in rollback_problems)
                raise RuntimeError(
                    f"activation failed and rollback was incomplete: {error}\n{details}"
                ) from error
            raise RuntimeError(f"activation failed; prior loader state restored: {error}") from error


def main() -> int:
    args = parse_args()
    store = args.store.expanduser().absolute()
    lock_path = (
        args.lock.expanduser().absolute()
        if args.lock is not None
        else default_lock_path(store)
    )
    raw_links = args.link or [Path("~/.claude/skills"), Path("~/.codex/skills")]
    links = [link.expanduser().absolute() for link in raw_links]
    activate_store(store, lock_path, links, args.apply)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
