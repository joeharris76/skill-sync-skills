"""Deployment-template gate for the rsync-based skill-sync transport.

This replaces the retired same-commit lock invariant (``skill-sync.yaml`` /
``skill-sync.lock`` + ``scripts/verify_lock.py``) and the generated-store
attesters (``scripts/verify_deployment_store.py``,
``scripts/activate_global_store.py``). Two halves:

1. Static: ``deployment/global/skill-sync.conf`` is well-formed, pins full
   commit SHAs that resolve in this repository's history, selects only
   tracked catalog skills, and cannot express a global/home or
   symlink-traversing target.
2. Behavioral: the vendored wrapper (``tools/skill-sync``) runs a real
   preview/apply/check/verify cycle, and ``verify`` fails nonzero when a
   managed file is modified, added, removed, mode-changed, or symlinked.

Standard library only, so CI needs no dependency install.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONF = ROOT / "deployment" / "global" / "skill-sync.conf"
WRAPPER = ROOT / "tools" / "skill-sync"

HAVE_TOOLCHAIN = shutil.which("git") and shutil.which("rsync")

SHA_RE = re.compile(r"[0-9a-f]{40}")
SKILL_RE = re.compile(r"[A-Za-z0-9._-]+")

# Untracked authoring work. It must never be selected for distribution, and
# no clean-SHA pin may ever be asked to vouch for its uncommitted bytes.
UNTRACKED_WORK = {"memex-search"}


def parse_conf(text: str):
    """Parse the small skill-sync grammar into (targets, groups)."""
    targets: list[str] = []
    groups: list[dict] = []
    current: dict | None = None
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if "=" not in line:
            raise AssertionError(f"line {lineno}: expected `key = value`, got {line!r}")
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key == "target":
            if current is not None:
                raise AssertionError(f"line {lineno}: `target` must precede every `source`")
            targets.append(value)
        elif key == "source":
            current = {"source": value, "rev": None, "dir": "skills", "skills": []}
            groups.append(current)
        elif key in ("rev", "dir", "skill"):
            if current is None:
                raise AssertionError(f"line {lineno}: `{key}` must follow a `source` line")
            if key == "skill":
                current["skills"].append(value)
            else:
                current[key] = value
        else:
            raise AssertionError(f"line {lineno}: unknown key {key!r}")
    return targets, groups


class DeploymentConfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.targets, cls.groups = parse_conf(CONF.read_text(encoding="utf-8"))

    def test_targets_are_project_relative(self):
        self.assertTrue(self.targets, "no `target` lines in skill-sync.conf")
        for target in self.targets:
            self.assertTrue(target, "empty target")
            self.assertFalse(os.path.isabs(target), f"target must be relative: {target}")
            self.assertFalse(target.startswith("~"), f"target must not use $HOME: {target}")
            parts = target.split("/")
            self.assertNotIn("..", parts, f"target must not contain `..`: {target}")
            self.assertNotIn(".claude", parts[:1], f"must not target a loader dir: {target}")
            self.assertFalse(target.startswith("store/.system"),
                             "must not target loader-owned `.system`")

    def test_every_group_pins_a_full_sha_with_dir_and_skills(self):
        self.assertTrue(self.groups, "no `source` groups in skill-sync.conf")
        seen: set[str] = set()
        for group in self.groups:
            self.assertTrue(group["rev"], f"source {group['source']} has no `rev`")
            self.assertTrue(SHA_RE.fullmatch(group["rev"] or ""),
                            f"`rev` must be a full commit SHA: {group['rev']!r}")
            self.assertTrue(group["skills"], f"source {group['source']} selects no skills")
            for skill in group["skills"]:
                self.assertTrue(SKILL_RE.fullmatch(skill), f"invalid skill name: {skill!r}")
                self.assertNotIn(skill, seen, f"skill {skill!r} is listed more than once")
                seen.add(skill)
        self.assertFalse(seen & UNTRACKED_WORK,
                         f"untracked authoring work must not be selected: {seen & UNTRACKED_WORK}")

    def test_catalog_group_selects_only_tracked_skills(self):
        catalog = [g for g in self.groups if Path(g["source"]).name == "skill-sync-skills"]
        self.assertEqual(len(catalog), 1, "expected exactly one catalog source group")
        group = catalog[0]
        for skill in group["skills"]:
            payload = ROOT / group["dir"] / skill
            self.assertTrue(payload.is_dir(), f"selected catalog skill is missing: {payload}")
        # The pin must resolve inside this repository's own history, so the
        # recorded SHA can only vouch for committed bytes.
        resolved = subprocess.run(
            ["git", "cat-file", "-e", f"{group['rev']}^{{commit}}"],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(resolved.returncode, 0,
                         f"catalog rev {group['rev']} is not present in this checkout; "
                         "fetch it or re-pin through review")

    def test_product_group_owns_only_the_operator_skill(self):
        product = [g for g in self.groups
                   if Path(g["source"]).name == "skill-sync"]
        self.assertEqual(len(product), 1, "expected exactly one product source group")
        self.assertEqual(product[0]["skills"], ["skill-sync"],
                         "the product repository owns only the operator skill")


@unittest.skipUnless(HAVE_TOOLCHAIN, "needs git and rsync on PATH")
class WrapperCycleTests(unittest.TestCase):
    """Real preview/apply/check/verify cycle with the vendored wrapper."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary.name) / "deployment"
        self.project.mkdir()
        # The catalog checkout itself is the source: `git archive` of HEAD
        # exports committed bytes only, so untracked authoring work can never
        # leak into the payload.
        (self.project / "skill-sync.conf").write_text(
            "target = store/skills\n"
            "\n"
            f"source = {ROOT}\n"
            "rev = HEAD\n"
            "dir = skills\n"
            "skill = blog\n",
            encoding="utf-8",
        )
        self.target = self.project / "store" / "skills"
        self.manifest = self.target / "skill-sync.manifest"

    def tearDown(self):
        self.temporary.cleanup()

    def run_wrapper(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["sh", str(WRAPPER), *args, "-C", str(self.project)],
            capture_output=True, text=True,
        )

    def test_preview_apply_check_verify(self):
        preview = self.run_wrapper("preview")
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertIn("A store/skills/blog/SKILL.md", preview.stdout)
        self.assertFalse(self.target.exists(), "preview must not modify the project")

        apply = self.run_wrapper("apply")
        self.assertEqual(apply.returncode, 0, apply.stderr)
        self.assertTrue((self.target / "blog" / "SKILL.md").is_file())

        check = self.run_wrapper("check")
        self.assertEqual(check.returncode, 0, check.stderr + check.stdout)

        verify = self.run_wrapper("verify")
        self.assertEqual(verify.returncode, 0, verify.stderr)

        # A second check after the apply is committed must still be clean.
        second = self.run_wrapper("check")
        self.assertEqual(second.returncode, 0, second.stderr + second.stdout)

    def mutate_and_reverify(self, mutate) -> str:
        self.assertEqual(self.run_wrapper("apply").returncode, 0)
        self.assertEqual(self.run_wrapper("verify").returncode, 0)
        mutate()
        failed = self.run_wrapper("verify")
        self.assertNotEqual(failed.returncode, 0, "verify must fail on a mutated payload")
        return failed.stderr + failed.stdout

    def test_verify_rejects_modified_file(self):
        payload = self.target / "blog" / "SKILL.md"

        def mutate():
            payload.write_text(payload.read_text(encoding="utf-8") + "\nlocal edit\n",
                               encoding="utf-8")

        self.assertIn("blog/SKILL.md", self.mutate_and_reverify(mutate))

    def test_verify_rejects_added_file(self):
        def mutate():
            (self.target / "blog" / "extra.md").write_text("unrecorded\n", encoding="utf-8")

        self.assertIn("extra.md", self.mutate_and_reverify(mutate))

    def test_verify_rejects_removed_file(self):
        def mutate():
            (self.target / "blog" / "skill.yaml").unlink()

        self.assertIn("skill.yaml", self.mutate_and_reverify(mutate))

    def test_verify_rejects_mode_change(self):
        payload = self.target / "blog" / "SKILL.md"

        def mutate():
            payload.chmod(payload.stat().st_mode | stat.S_IXUSR)

        self.assertIn("blog/SKILL.md", self.mutate_and_reverify(mutate))

    def test_verify_rejects_symlink(self):
        payload = self.target / "blog" / "SKILL.md"

        def mutate():
            payload.unlink()
            payload.symlink_to("/etc/hostname")

        self.assertIn("blog/SKILL.md", self.mutate_and_reverify(mutate))

    def test_check_notices_config_change(self):
        self.assertEqual(self.run_wrapper("apply").returncode, 0)
        conf = self.project / "skill-sync.conf"
        conf.write_text(conf.read_text(encoding="utf-8") + "skill = docs\n", encoding="utf-8")
        pending = self.run_wrapper("check")
        self.assertEqual(pending.returncode, 3, pending.stdout + pending.stderr)
        self.assertIn("store/skills/docs/SKILL.md", pending.stdout)


if __name__ == "__main__":
    unittest.main()
