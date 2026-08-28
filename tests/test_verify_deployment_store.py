from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import verify_deployment_store as verifier
from scripts.verify_deployment_store import default_lock_path, verify_managed_payload


def metadata(content: bytes) -> dict[str, str | int]:
    return {"sha256": hashlib.sha256(content).hexdigest(), "size": len(content)}


class VerifyDeploymentStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary.name)
        self.store = self.project / "store" / "skills"
        self.skill_file = self.store / "skill-sync" / "SKILL.md"
        self.skill_file.parent.mkdir(parents=True)
        self.skill_file.write_bytes(b"skill-sync\n")
        self.lock_path = self.project / "skill-sync.lock"
        self.lock = {
            "version": 1,
            "skills": {
                "skill-sync": {"files": {"SKILL.md": metadata(b"skill-sync\n")}}
            },
        }
        self.write_lock()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_lock(self) -> None:
        self.lock_path.write_text(json.dumps(self.lock), encoding="utf-8")

    def problems(self) -> list[str]:
        return verify_managed_payload(self.store, self.lock_path)

    def test_valid_payload_omits_only_exact_system_directory(self) -> None:
        system_file = self.store / ".system" / "imagegen" / "SKILL.md"
        system_file.parent.mkdir(parents=True)
        system_file.write_bytes(b"loader-owned\n")

        self.assertEqual(self.problems(), [])
        self.assertEqual(default_lock_path(self.store), self.lock_path)

        system_file.unlink()
        system_file.parent.rmdir()
        (self.store / ".system").rmdir()
        case_variant = self.store / ".System" / "imagegen" / "SKILL.md"
        case_variant.parent.mkdir(parents=True)
        case_variant.write_bytes(b"not loader-owned\n")
        self.assertTrue(any(".System" in problem for problem in self.problems()))

    def test_rejects_managed_file_drift_and_file_set_changes(self) -> None:
        mutations = {
            "missing": lambda: self.skill_file.unlink(),
            "modified": lambda: self.skill_file.write_bytes(b"changed\n"),
            "extra": lambda: (self.store / "skill-sync" / "EXTRA.md").write_bytes(b"extra\n"),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                original = self.skill_file.read_bytes()
                extra = self.store / "skill-sync" / "EXTRA.md"
                mutate()
                self.assertNotEqual(self.problems(), [])
                if extra.exists():
                    extra.unlink()
                if not self.skill_file.exists() or self.skill_file.read_bytes() != original:
                    self.skill_file.write_bytes(original)

    def test_rejects_unexpected_top_level_payload(self) -> None:
        rogue = self.store / "rogue" / "SKILL.md"
        rogue.parent.mkdir()
        rogue.write_bytes(b"rogue\n")

        problems = self.problems()

        self.assertTrue(any("unexpected managed" in problem for problem in problems))
        self.assertTrue(any("rogue" in problem for problem in problems))

    def test_rejects_symlinks_in_managed_payload(self) -> None:
        target = self.project / "outside"
        target.write_bytes(b"outside\n")
        (self.store / "skill-sync" / "LINK.md").symlink_to(target)

        self.assertTrue(any("symlink is not allowed" in problem for problem in self.problems()))

    def test_rejects_file_swapped_to_symlink_between_lstat_and_open(self) -> None:
        outside = self.project / "outside"
        outside.write_bytes(b"skill-sync\n")
        displaced = self.project / "displaced"
        real_open = os.open
        swapped = False

        def swap_before_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
            nonlocal swapped
            if path == "SKILL.md" and kwargs.get("dir_fd") is not None and not swapped:
                swapped = True
                self.skill_file.replace(displaced)
                self.skill_file.symlink_to(outside)
            return real_open(path, flags, *args, **kwargs)

        with mock.patch.object(verifier.os, "open", side_effect=swap_before_open):
            problems = self.problems()

        self.assertTrue(swapped)
        self.assertTrue(any("without following links" in problem for problem in problems))

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO creation is unavailable")
    def test_rejects_special_file_without_opening_it(self) -> None:
        fifo = self.store / "skill-sync" / "PIPE"
        os.mkfifo(fifo)

        problems = self.problems()

        self.assertTrue(any("special file is not allowed" in problem for problem in problems))

    def test_rejects_unsafe_lock_paths(self) -> None:
        cases = [
            ("skill", "../escape"),
            ("skill", "."),
            ("file", "../escape.md"),
            ("reserved", ".system/imagegen"),
        ]
        for label, unsafe_path in cases:
            with self.subTest(label=label):
                original = copy.deepcopy(self.lock)
                if label == "skill":
                    self.lock["skills"][unsafe_path] = self.lock["skills"].pop("skill-sync")
                elif label == "file":
                    files = self.lock["skills"]["skill-sync"]["files"]
                    files[unsafe_path] = files.pop("SKILL.md")
                else:
                    self.lock["skills"][unsafe_path] = self.lock["skills"].pop("skill-sync")
                self.write_lock()

                self.assertNotEqual(self.problems(), [])
                self.lock = original
                self.write_lock()

    def test_rejects_system_symlink_instead_of_hiding_it(self) -> None:
        target = self.project / "platform"
        target.mkdir()
        (self.store / ".system").symlink_to(target, target_is_directory=True)

        self.assertTrue(any("symlink is not allowed" in problem for problem in self.problems()))

    def test_rejects_symlinked_generated_lock(self) -> None:
        real_lock = self.project / "real.lock"
        self.lock_path.replace(real_lock)
        self.lock_path.symlink_to(real_lock)

        self.assertTrue(any("generated lock must be a real file" in problem for problem in self.problems()))


if __name__ == "__main__":
    unittest.main()
