# Phase 3 pre-registration amendments

These amendments apply to every `phase3-<family>.md` file. They were made
before any scored run of the families they cover.

## Dial levels (frozen)

`phase3-dials.json` maps each `<family>--<variant>` to the dial level its
scored runs use. Levels come from a Sonnet pilot of 8 sessions per level, run
in the `minus-skill` arm only; pilot sessions are discarded. The rule picks
the level whose `minus-skill` pass rate is nearest 50%. For a family with
several decision checks, that rate is the mean of the checks' pass rates.
Ties go to the level with the lower `minus-skill` pass rate, then to the
lower dial.

The tie rule was amended after the first pilot. The original rule sent ties
straight to the lower dial, and it chose a level where `minus-skill` passed
every session (code-config: 100% at d1 against 0% at d2). That makes a test
unable to show a drop.

The file covers the review, investigation, repository-convention,
change-framework and takeover-resumption families. The todo and takeover
families are added in a later commit, before their scored runs.

## Sample

Each counting model runs 36 sessions per arm per family: 12 per variant at
its frozen dial, with arms interleaved. The family files say 70. The change
follows measured session costs (Opus $0.20–0.50 and Fable $0.43–1.05 per
session).

Phase 3 can delete nothing while GPT Sol is unavailable, since Sol counts for
every skill tested. Keep and harmful bands are decided as registered. Most
equivalence results at this sample will be inconclusive; they can be topped
up to 70 when Sol runs.

## Models

GPT Sol is unavailable: a weekly ChatGPT limit, and no Bedrock access. Phase
3 runs only the Claude models that count for each family's skills. Families
whose skills count no Claude model wait for Sol and get no scored runs:

- the takeover families;
- the four investigation-framework families;
- test-config;
- docs-conventions.
