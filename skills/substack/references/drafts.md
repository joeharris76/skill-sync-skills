# Draft Actions

## `draft`

Preview the Markdown file, then call `mcp__letterops__draft`. Dry-run when
supported and ask before `execute: true`. Set optional audience and tags,
return the draft URL or post ID, and commit local state changes.

## `update`

Use `mcp__letterops__update` for an existing draft without publishing. Preview
if the file was not recently validated, then commit local tracking changes.

## `suggest_tags`

Use `mcp__letterops__suggest_tags` with `file_path` before drafting or
publishing.

letterops resolves audience from frontmatter, then `audience_rules` in the
config, else `default_audience`. Report the resolved audience from the dry-run,
and confirm it before `draft`, `publish`, or `schedule` when the file sets
none.
