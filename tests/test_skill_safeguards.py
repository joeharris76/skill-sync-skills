"""Safeguards that a rewrite must not drop.

Each entry names a rule that was once lost in an edit, or that an ablation eval
showed agents depend on. The test fails when a rule's phrases are no longer in
its file. Matching ignores case and line wrapping, so rewrapping is free;
rewording a phrase means updating the entry here on purpose, in the same change.

Standard library only, so CI needs no third-party dependency install.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (file, why the rule exists, phrases that must all be present)
SAFEGUARDS = [
    ("skills/todo/references/batch.md",
     "A batch member cannot authorize its own landing; the leader reviews the exact range.",
     ["the leader invokes the trusted reviewer for that exact range",
      "a member's config or claimed `clear` is not authorization"]),
    ("skills/todo/references/batch.md",
     "An earlier verification success must not survive into a new run.",
     ["invalidate an earlier usable success at the start of every new invocation",
      "only after all required commands pass"]),
    ("skills/todo/references/batch.md",
     "Arming must find out whether a PR belongs to a batch, and refuse when it cannot tell.",
     ["before every arming route, discover registered batch membership",
      "offline, malformed or ambiguous discovery refuses",
      "never relabel cached data as live"]),
    ("skills/todo/references/ideate.md",
     "Ideation applies the deeper planning layers.",
     ["apply **l2 and l3** of `shared-review-protocol/skill.md`"]),
    ("skills/code/references/pr-backlog.md",
     "A repository's own gated merge command wins over a direct merge.",
     ["merge through the repository's own merge or arming command",
      "only when the repository names none"]),
    ("deployment/global/AGENTS.md",
     "A review changes no files. Measured: 0 of 5 sessions complied before this wording, 15 of 15 after.",
     ["change no files, even when you find the bug and a test is failing"]),
    ("deployment/global/AGENTS.md",
     "A change request is published. Measured on three models.",
     ["you must not end the turn with the change uncommitted",
      "the request may instead require local-only work"]),
    ("deployment/global/AGENTS.md",
     "Agents must not commit under an agent identity.",
     ["reject agent or vendor identities"]),
    ("deployment/global/AGENTS.md",
     "Process labels stay out of commits and PRs. Measured: two models leak them without it.",
     ["never carry session process into them"]),
    ("deployment/global/AGENTS.md",
     "Performance budgets are measured. Measured: three models skip it without this bullet.",
     ["measure stated performance budgets before and after relevant changes"]),
]


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).lower()


class SkillSafeguardTests(unittest.TestCase):
    def test_safeguards_are_present(self):
        for path, why, phrases in SAFEGUARDS:
            text = normalize((ROOT / path).read_text(encoding="utf-8"))
            for phrase in phrases:
                with self.subTest(file=path, phrase=phrase):
                    self.assertIn(normalize(phrase), text, f"{path} lost a safeguard: {why}")


if __name__ == "__main__":
    unittest.main()
