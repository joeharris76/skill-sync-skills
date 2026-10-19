from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import routing_sync

TEXT = "intro\n<!-- routing:begin -->\nstale\n<!-- routing:end -->\noutro\n"
ROLES = {"smol": "a/haiku:medium", "default": "a/sonnet:medium", "custom": "a/x:low"}
CHAINS = {"smol": ["b/luna:medium", "c/flash:medium"]}


class RoutingSyncTests(unittest.TestCase):
    def test_rendered_block_replaces_stale_text_and_is_stable(self):
        once = routing_sync.splice(TEXT, routing_sync.render(ROLES, CHAINS))
        self.assertNotIn("stale", once)
        self.assertEqual(once, routing_sync.splice(once, routing_sync.render(ROLES, CHAINS)))
        self.assertTrue(once.startswith("intro\n") and once.endswith("outro\n"))

    def test_rows_follow_role_order_and_list_fallbacks_in_order(self):
        rows = routing_sync.render(ROLES, CHAINS).splitlines()[2:]
        self.assertEqual([row.split("`")[1] for row in rows], ["default", "smol", "custom"])
        self.assertIn("`b/luna:medium` → `c/flash:medium`", rows[1])
        self.assertIn("| none |", rows[0])

    def test_model_kind_roles_are_excluded_from_the_chat_table(self):
        roles = {**ROLES, "judge": "typesafe/jev-1.14.0", "image": "openai/gpt-image-1"}
        rows = routing_sync.render(roles, CHAINS).splitlines()[2:]
        self.assertEqual([row.split("`")[1] for row in rows], ["default", "smol", "custom"])

    def test_a_changed_role_is_detected_as_drift(self):
        synced = routing_sync.splice(TEXT, routing_sync.render(ROLES, CHAINS))
        changed = {**ROLES, "smol": "a/haiku:low"}
        self.assertNotEqual(synced, routing_sync.splice(synced, routing_sync.render(changed, CHAINS)))

    def test_a_file_without_markers_is_refused(self):
        with self.assertRaises(SystemExit):
            routing_sync.splice("no markers", routing_sync.render(ROLES, CHAINS))


if __name__ == "__main__":
    unittest.main()
