
# Quality Check

Run all quality checks before committing code to ensure CI will pass.

## Instructions

1. **Run all checks in sequence**:

   ```bash
   make lint && make format && make typecheck && make test-fast
   ```

   Or individually:
   - `make lint` - Ruff lint check
   - `make format` - Ruff format check
   - `make typecheck` - Type checking (ty check)
   - `make test-fast` - Quick smoke tests

2. **Analyze each result**:

   | Check | Analysis |
   |-------|----------|
   | Lint | Errors (E), warnings (W), style issues. Auto-fix: `uv run ruff check --fix .` |
   | Format | Files needing reformatting. Applied by `make format` |
   | Typecheck | Type errors, missing hints. Fix with annotations or `# type: ignore[code]` |
   | Tests | Pass/fail counts, import errors, failures |

3. **Provide summary report**

## Output Format

```markdown
## Quality Check Results

### Status
| Check | Result | Issues |
|-------|--------|--------|
| Lint | PASS/FAIL | X issues |
| Format | PASS/FAIL | X files |
| Typecheck | PASS/FAIL | X errors |
| Tests | PASS/FAIL | X/Y passed |

### Issues Found
{grouped by category, prioritized}

### Recommendations
1. {priority fix}
2. {next fix}

### Ready to Commit?
{YES / NO - fix N issues}
```

## Extended Checks

For thorough verification:

```bash
make test-all              # All tests
make validate-imports      # Import structure
make dependency-check      # Lock file
```

## CI Requirements

- No ruff errors
- All files formatted with ruff
- No type checker errors
- All tests passing

## Notes

- Run before every commit
- Line length: 120 chars
- Type hints required for public APIs
- All code must be ruff-formatted
