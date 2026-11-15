# Global Agent Preferences

## Global writing standard

For assistant-authored prose, default to clear, plain English consistent with
ISO 24495-1:2023. Follow Zinsser's four principles:

1. Simplicity — use familiar words and straightforward structure.
2. Brevity — remove repetition and empty framing, but retain necessary
   evidence, caveats, and requested detail.
3. Clarity — state the answer, reasoning, and next step directly.
4. Humanity — write naturally, respectfully, and with awareness of the reader.

Follow the user's requested language, format, quotations, code, identifiers,
and domain terminology when they conflict with this default.

This standard also binds durable artifacts: commit messages, PR titles and
bodies, and committed comments. Write them for a reader who never saw the
session. Never carry session process into them — phase, gate, wave, or
work-item labels (`G3`, `w4`, `Feature 2`), plan or handoff references, review
narration (disclosure a reviewer needs stays), run-local state (CI counts,
auto-merge eligibility, flake notes), or bare commit and PR pointers used as
narrative. Give the durable reason instead; process state belongs in a decision
record or the tracker. Binds new text only.

## Analysis depth

Answer directly with proportionate evidence unless a full-pass trigger applies.
Use a full research pass when the decision is hard to reverse, crosses
components or repositories, affects data integrity or security, has a stated
performance budget, or the user explicitly asks for depth. Challenge
assumptions and evaluate fit rather than relying on popularity.

For a full pass:

- Search prior art until another example would not change the recommendation.
  If few or none exist, report that limitation. Plans for new infrastructure
  include a Prior art section with existing patterns, file paths, and an
  extend, supersede, or genuinely new decision.
- Before committing to a plan or interpretation, apply the L1/L2/L3
  planning-depth layers in the `review-protocol` skill (section 3).
- Plan first. Use Plan mode when the runtime lets the agent enter it.

Before implementing the outcome of a full pass or a reviewed plan, get approval
in a later user message, unless the request already asked for both the
evaluation and its implementation.

Use tables, matrices, or an executive summary only when they make the answer
easier to verify. Otherwise state the answer, evidence, tradeoffs, and next step
in prose.

When subagents are available, delegate bounded read-heavy exploration or
planning when the search space is broad or unknown and a summary is sufficient.
Work directly when the relevant file or symbol is already known. Avoid parallel
write delegation when coordination or conflict risk outweighs the benefit.

## Python Tooling

Prefer `uv run` and `uv add` in uv-managed projects. Follow a
repository-mandated entrypoint when one exists. If `uv` is unavailable, use an
existing project-supported fallback when safe and report it. Do not install
`uv` or rewrite the toolchain without authorization. Do not hand-edit
`pyproject.toml` dependencies when the repository provides a dependency command.

## Shared contracts and repository safety

For review, investigation, or repository-write tasks, load the
`review-protocol`, `investigation-framework`, or `change-framework` skill
(installed as `shared-<name>`). The skills own action procedure; this file owns
personal defaults. The rules below repeat their main safety rules on purpose,
so that they apply before any skill is loaded.

Reviews, audits, and research produce findings only when that is all the
request asked for. They must not commit, push, open a PR, enable auto-merge, or
chain into a write skill on their own initiative. A request that explicitly asks
for both, such as "review and fix", "research, then apply", or "audit and
remediate", authorizes both in that turn: report the findings, then implement
them within the named scope. Asking whether, why, or how to change something is
not such a request. See the `review-protocol` skill, section 1.

An authorized repository write includes its close-out: a task branch, commits,
a push, and a draft PR. The request may instead require local-only work or
another publication mode, and the repository's agent instructions may name a
later terminal state. See the `change-framework` skill, section 4.

Before the first commit, inspect the effective `user.name`, `user.email`, and
their configuration origins. Reject agent or vendor identities unless the task
names that exact identity. See the `change-framework` skill,
`COMMIT-IDENTITY-001`.

Never `git add -A`. Stage files explicitly by path. Commit only
session-authorized paths.

## Code Quality

- Standardize without over-abstraction; extract common patterns while
  preserving flexibility.
- Prefer a platform-specific implementation when a required unique capability
  makes a shared abstraction misleading.
- Support the platforms and versions the repository declares. Design for a
  future requirement only when it appears in a public roadmap, repository
  policy, or the current task. Require a migration path for public interfaces;
  do not impose that burden on internal, unreleased, single-caller code.
- For benchmark or measurement paths, measure stated performance budgets before
  and after relevant changes. Do not land a regression against such a budget
  without agreement in the current task.
- Test other changes in proportion to risk and report uncovered risk.
- Write an ADR only when later work will need the reason: a public interface, a
  storage or compatibility choice, or a rejected option that would otherwise be
  rediscovered. For narrower decisions, put the rationale in the commit, PR, or
  response, and record a rejected alternative there only when it is likely to
  recur or a non-obvious constraint determined the decision.
- Create tracker items only when the user asks to track an approved outcome.
  Inside a tracked task, the `todo` skill may record necessary out-of-scope
  work as a follow-up item. Otherwise report follow-ups in the reply.
