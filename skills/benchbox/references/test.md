
# Benchmark Test Runner

Run benchmark-specific tests quickly based on the user's request.

## Instructions

1. **Identify benchmark** from request:

   | Benchmark | Command |
   |-----------|---------|
   | TPC-H | `make test-tpch` |
   | TPC-DS | `make test-tpcds` |
   | TPC-DI | `uv run -- python -m pytest -k tpcdi -v` |
   | Read Primitives | `make test-read-primitives` |
   | SSB | `uv run -- python -m pytest -k ssb -v` |
   | ClickBench | `uv run -- python -m pytest -k clickbench -v` |
   | AmpLab | `uv run -- python -m pytest -k amplab -v` |
   | H2ODB | `uv run -- python -m pytest -k h2odb -v` |

2. **Run appropriate test command** using Bash tool

3. **Analyze results**:
   - Count passing/failing tests
   - Identify failure patterns
   - Check for import errors, data generation issues, query problems

4. **Report summary**:
   - Total tests run
   - Pass/fail breakdown
   - Quick summary of failures
   - Suggested next steps

## Speed Options

For faster testing:
- `make test-fast` - Quick smoke tests
- `make test-dev` - Fast development cycle
- Specific test files instead of full suites

## Output Format

```markdown
## Test Results: {benchmark}

### Summary
- **Tests**: {total} | **Passed**: {passed} | **Failed**: {failed}
- **Duration**: {time}

### Failures (if any)
| Test | Error | Location |
|------|-------|----------|
| test_name | AssertionError | file.py:45 |

### Next Steps
- `/test-fix {test}` for failures
- `/test-coverage` for gaps
```

## Notes

- Tests located in `tests/unit/` and `tests/integration/`
- Some tests require data generation (slow)
- Fast tests skip data generation where possible
- Markers: `fast`, `unit`, `integration`, `tpch`, `tpcds`
