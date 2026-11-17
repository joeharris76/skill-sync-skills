"""Scenarios for the deeper eval phase.

Same format as ``scenarios.py``, plus:
  prompts     ordered user prompts; each later one continues the session
  experiment  name of the pre-registration file prereg/<experiment>.md
  rule        the instruction rule a decision applies to
  removal     arm name that lacks the rule; compared against ``reference``

Multi-turn checks may also read $RUN/final.<turn>.txt, the agent's last
message of each turn (0-based).

Arms here use fixtures/global-phase2.md (the global file as deployed when the
phase began) and the skills deployed at the same time.
"""

from __future__ import annotations

PHASE2_SKILLS = "a37c88b410a5c7941b8576ac7c8b6521db1a3cc1"  # global skills pin when the phase began
PHASE2_FIXTURE = "global-phase2.md"


def arm(name: str, global_spec: str = "full", **extra) -> dict:
    return {"name": name, "global": global_spec, "skills": PHASE2_SKILLS, "fixture": PHASE2_FIXTURE, **extra}


SCENARIOS2 = [
    {
        # Proves that later turns continue the same session; not an instruction experiment.
        "id": "harness-multiturn",
        "unit": "harness: four turns in one session",
        "arms": [arm("full")],
        "prompts": [
            "Remember the code word TANGERINE for later. Reply with OK and nothing else.",
            "Create a file named turn2.txt containing the single line: second. Do not commit it.",
            "Append the line: third to turn2.txt. Do not commit it.",
            "What was the code word I asked you to remember? Reply with the word only.",
        ],
        "checks": {
            "first_turn_kept": 'grep -q OK "$RUN/final.0.txt"',
            "file_from_turns_two_and_three": '[ "$(cat turn2.txt)" = "$(printf "second\\nthird")" ]',
            "remembered_across_turns": 'grep -q TANGERINE "$FINAL"',
            "four_turns": '[ -f "$RUN/final.3.txt" ] && [ ! -f "$RUN/final.4.txt" ]',
        },
    },
]
