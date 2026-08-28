from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import activate_global_store as activation


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "activate_global_store.py"


def write_lock(project: Path, store: Path) -> None:
    skills: dict[str, dict] = {}
    for skill_dir in sorted(path for path in store.iterdir() if path.name != ".system"):
        files: dict[str, dict[str, str | int]] = {}
        for path in sorted(skill_dir.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            content = path.read_bytes()
            files[path.relative_to(skill_dir).as_posix()] = {
                "sha256": hashlib.sha256(content).hexdigest(),
                "size": len(content),
            }
        skills[skill_dir.name] = {"files": files}
    (project / "skill-sync.lock").write_text(
        json.dumps({"version": 1, "skills": skills}, indent=2) + "\n",
        encoding="utf-8",
    )


def make_deployment(root: Path) -> tuple[Path, Path]:
    project = root / "deployment"
    store = project / "store" / "skills"
    (store / "skill-sync").mkdir(parents=True)
    (store / "skill-sync" / "SKILL.md").write_text("# Skill Sync\n", encoding="utf-8")
    write_lock(project, store)
    return project, store


class ActivateGlobalStoreTest(unittest.TestCase):
    def test_attests_then_repoints_symlinks_without_touching_system_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, store = make_deployment(root)
            system_file = store / ".system" / "imagegen" / "SKILL.md"
            system_file.parent.mkdir(parents=True)
            system_file.write_bytes(b"platform-owned\x00bytes\n")
            system_before = system_file.read_bytes()
            first = root / "claude" / "skills"
            second = root / "codex" / "skills"

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(store),
                    "--link",
                    str(first),
                    "--link",
                    str(second),
                    "--apply",
                ],
                check=True,
            )

            self.assertEqual(first.resolve(), store.resolve())
            self.assertEqual(second.resolve(), store.resolve())
            self.assertEqual(system_file.read_bytes(), system_before)

    def test_attestation_failure_does_not_change_existing_links(self) -> None:
        mutations = {
            "managed drift": lambda store: (store / "skill-sync" / "SKILL.md").write_text(
                "tampered\n", encoding="utf-8"
            ),
            "extra managed file": lambda store: (store / "skill-sync" / "EXTRA.md").write_text(
                "extra\n", encoding="utf-8"
            ),
            "ordinary top-level extra": lambda store: (
                (store / "rogue").mkdir(),
                (store / "rogue" / "SKILL.md").write_text("rogue\n", encoding="utf-8"),
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                _, store = make_deployment(root)
                previous = root / "previous"
                previous.mkdir()
                first = root / "claude" / "skills"
                second = root / "codex" / "skills"
                first.parent.mkdir(parents=True)
                second.parent.mkdir(parents=True)
                first.symlink_to(previous, target_is_directory=True)
                second.symlink_to(previous, target_is_directory=True)
                mutate(store)

                result = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPT),
                        str(store),
                        "--link",
                        str(first),
                        "--link",
                        str(second),
                        "--apply",
                    ],
                    capture_output=True,
                    text=True,
                )

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("managed payload attestation failed", result.stderr)
                self.assertEqual(os.readlink(first), str(previous))
                self.assertEqual(os.readlink(second), str(previous))

    def test_refuses_a_real_loader_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, store = make_deployment(root)
            link = root / "skills"
            link.mkdir()

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(store), "--link", str(link), "--apply"],
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("refusing to replace non-symlink", result.stderr)

    def test_invalid_second_loader_leaves_first_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, store = make_deployment(root)
            previous = root / "previous"
            previous.mkdir()
            first = root / "claude" / "skills"
            second = root / "codex" / "skills"
            first.parent.mkdir(parents=True)
            second.mkdir(parents=True)
            first.symlink_to(previous, target_is_directory=True)
            first_before = os.readlink(first)

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(store),
                    "--lock",
                    str(project / "skill-sync.lock"),
                    "--link",
                    str(first),
                    "--link",
                    str(second),
                    "--apply",
                ],
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(os.readlink(first), first_before)
            self.assertTrue(second.is_dir())
            self.assertFalse(second.is_symlink())

    def test_second_replacement_failure_rolls_back_first_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project, store = make_deployment(root)
            first = root / "loaders" / "first"
            second = root / "loaders" / "second"
            first.parent.mkdir()
            first.symlink_to("../prior-one", target_is_directory=True)
            second.symlink_to("../prior-two", target_is_directory=True)
            first_before = os.readlink(first)
            second_before = os.readlink(second)
            real_replace = os.replace
            failed = False

            def fail_second_once(source: object, destination: object) -> None:
                nonlocal failed
                if Path(destination) == second and not failed:
                    failed = True
                    real_replace(source, destination)
                    raise OSError("induced second replacement failure")
                real_replace(source, destination)

            with mock.patch.object(
                activation.os, "replace", side_effect=fail_second_once
            ):
                with self.assertRaisesRegex(
                    RuntimeError, "prior loader state restored"
                ):
                    activation.activate_store(
                        store,
                        project / "skill-sync.lock",
                        [first, second],
                        apply=True,
                    )

            self.assertTrue(failed)
            self.assertEqual(os.readlink(first), first_before)
            self.assertEqual(os.readlink(second), second_before)


if __name__ == "__main__":
    unittest.main()
