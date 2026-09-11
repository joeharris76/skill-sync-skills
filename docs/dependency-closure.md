# Dependency Closure Reference

Descriptive reference only. The `depends:` field in each skill's
`skill.yaml` remains the source of truth; this file restates the
transitive closure so a consumer's config can name the complete set.
It is not a resolver, and it changes no `depends:` field.

## Why this exists

The `skill-sync` TypeScript CLI was replaced by the vendored shell
rsync wrapper (`tools/skill-sync`), which has no dependency solver:
each consumer's config must name every skill explicitly. A skill that
is not named is not installed, appears in no receipt, and is left
behind as stale unmanaged content.

Motivating case (consumer side, September 2026): BenchBox's config
names top-level skills but receives `shared-agent-execution` only
transitively, through `bossmode`'s `depends:`. Under explicit
selection that transitive link installs nothing, so
`shared-agent-execution` would be missing from the install and its
receipt while stale copies linger.

## How to read this table

- **Direct** lists the skill's own `depends:` from its `skill.yaml`.
- **Transitive closure** is every dependency reachable through those
  entries (dependencies of dependencies included).
- **Explicit set** is the full list a consumer must name: the skill
  itself plus its transitive closure.
- `(none)` means the skill has no dependencies and is installed by
  naming it alone.

## Closures by skill

| Skill | Direct `depends:` | Transitive closure | Explicit set to list |
|---|---|---|---|
| benchbox | `shared-change-framework` | `shared-change-framework` | `benchbox`, `shared-change-framework` |
| blog | `shared-change-framework`, `shared-review-protocol` | `shared-change-framework`, `shared-review-protocol` | `blog`, `shared-change-framework`, `shared-review-protocol` |
| bossmode | `shared-agent-execution` | `shared-agent-execution` | `bossmode`, `shared-agent-execution` |
| code | `shared-change-framework`, `shared-investigation-framework`, `shared-review-protocol` | `shared-change-framework`, `shared-investigation-framework`, `shared-review-protocol` | `code`, `shared-change-framework`, `shared-investigation-framework`, `shared-review-protocol` |
| docs | `shared-change-framework`, `shared-investigation-framework`, `shared-review-protocol` | `shared-change-framework`, `shared-investigation-framework`, `shared-review-protocol` | `docs`, `shared-change-framework`, `shared-investigation-framework`, `shared-review-protocol` |
| memex-search | (none) | (none) | `memex-search` |
| session-takeover | `shared-change-framework`, `shared-investigation-framework`, `shared-review-protocol` | `shared-change-framework`, `shared-investigation-framework`, `shared-review-protocol` | `session-takeover`, `shared-change-framework`, `shared-investigation-framework`, `shared-review-protocol` |
| shared-agent-execution | (none) | (none) | `shared-agent-execution` |
| shared-change-framework | (none) | (none) | `shared-change-framework` |
| shared-investigation-framework | `shared-review-protocol` | `shared-review-protocol` | `shared-investigation-framework`, `shared-review-protocol` |
| shared-review-protocol | (none) | (none) | `shared-review-protocol` |
| substack | `shared-change-framework` | `shared-change-framework` | `shared-change-framework`, `substack` |
| test | `shared-change-framework`, `shared-investigation-framework` | `shared-change-framework`, `shared-investigation-framework`, `shared-review-protocol` | `shared-change-framework`, `shared-investigation-framework`, `shared-review-protocol`, `test` |
| tidy-perms | (none) | (none) | `tidy-perms` |
| todo | `shared-change-framework`, `shared-investigation-framework`, `shared-review-protocol` | `shared-change-framework`, `shared-investigation-framework`, `shared-review-protocol` | `shared-change-framework`, `shared-investigation-framework`, `shared-review-protocol`, `todo` |

## Staying current

This file is generated from the `skill.yaml` files. Do not edit the
table by hand. After changing any `depends:` list, regenerate:

```bash
uv run --with pyyaml docs/generate_dependency_closure.py --write
```

Verify freshness without writing:

```bash
uv run --with pyyaml docs/generate_dependency_closure.py --check
```
