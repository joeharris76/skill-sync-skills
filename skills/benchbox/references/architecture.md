
# Architecture Review

Analyze code architecture to ensure it follows BenchBox patterns and best practices.

## Instructions

1. **Identify scope**: Single benchmark, platform adapter, new module, or full system review

2. **Review against core patterns**:

   **Benchmark Structure**:
   ```
   benchbox/core/{benchmark}/
   ├── __init__.py       # Exports main class
   ├── benchmark.py      # Inherits BaseBenchmark
   ├── generator.py      # Data generation
   ├── queries.py        # Query management
   ├── schema.py         # Table schemas
   └── runner.py         # Optional runner API
   ```

3. **Check BaseBenchmark inheritance**:
   - `get_queries()`, `get_query(query_num)`
   - `get_schema()`, `generate_data()`
   - Properties: `name`, `version`, `description`

4. **Verify platform adapter integration**:
   - Uses `PlatformAdapter` base class
   - Implements: `execute_query()`, `get_connection()`
   - Registered in `platform_registry.py`

5. **Review patterns**:

   | Pattern | Good | Bad |
   |---------|------|-----|
   | Connections | Platform adapters | Direct connections |
   | SQL | sqlglot translation | Hard-coded dialect |
   | Errors | Comprehensive handling | Missing handlers |
   | Naming | snake_case | Mixed styles |
   | Types | Full hints | Missing hints |

6. **Check code quality**: Type hints, docstrings, error handling

7. **Look for anti-patterns**: Direct DB connections, hard-coded SQL, duplicate code, tight coupling

8. **Review integration points**: platform_registry, config_utils, connection, schemas, results

9. **Check technical debt**: TODO comments, hacks, deprecated patterns

10. **Generate architecture report**

## Output Format

```markdown
## Architecture Review: {Component}

### Compliance

✅ **Strengths**:
- Properly inherits from BaseBenchmark
- Complete type hints

⚠️ **Areas for Improvement**:
- Missing docstrings in 3 methods

❌ **Issues**:
- Does not use platform adapter

### Detailed Findings

#### 1. {Issue} (Critical/Important/Enhancement)
**Location**: {file:line}
**Issue**: {description}
**Current**: `{code}`
**Should be**: `{code}`
**Impact**: {impact}

### Architecture Score: X/10

| Aspect | Score |
|--------|-------|
| Structure | X/10 |
| Patterns | X/10 |
| Quality | X/10 |
| Integration | X/10 |

### Priority Actions
1. **HIGH**: {action}
2. **MEDIUM**: {action}
```

## Key Files

- `benchbox/core/base_benchmark.py` - Base class
- `benchbox/core/tpch/` - Reference implementation
- `benchbox/platforms/base.py` - Platform adapter base
- `benchbox/core/config_utils.py` - Configuration

## Notes

- Focus on architectural issues, not style
- Compare to established benchmarks
- Prioritize by user impact
- Suggest concrete improvements
