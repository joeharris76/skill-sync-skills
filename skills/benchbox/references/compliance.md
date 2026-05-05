
# TPC Compliance Checker

Validate benchmark implementations comply with official TPC specifications.

## Instructions

1. **Identify TPC benchmark**: TPC-H, TPC-DS, or TPC-DI

2. **Review implementation** in `benchbox/core/{benchmark}/`:
   - `benchmark.py` - Main interface
   - `generator.py` - Data generation
   - `queries.py` - Query management
   - `schema.py` - Table schemas
   - Test implementations (power_test.py, throughput_test.py, maintenance_test.py)

3. **Check compliance areas**:

   **Query Compliance**:
   - All official queries present and numbered correctly
   - Templates match specification
   - Parameters generated per spec
   - Substitution values follow TPC rules

   **Data Generation**:
   - Scale factors supported correctly
   - Distribution follows specification
   - Referential integrity maintained
   - Official C tools used where required

   **Test Structure** (if applicable):
   - Power Test: Sequential execution, correct timing
   - Throughput Test: Parallel streams, isolation
   - Maintenance Test: RF1/RF2 refresh functions
   - Metrics: TPC formula compliance

   **Binary Integration**:
   - Platform-specific builds in `_binaries/tpc-{h,ds}/`
   - C wrapper integration
   - Output matches C tools

4. **Review compliance code**:
   - `benchbox/core/tpc_compliance.py`
   - `benchbox/core/tpc_validation.py`
   - `benchbox/core/tpc_patterns.py`

5. **Run validation tests** matching "compliance", "official", "validation"

6. **Report findings** with severity and line references

## Output Format

```markdown
## TPC Compliance: {benchmark}

### Query Compliance
| Query | Status | Issue |
|-------|--------|-------|
| Q1 | PASS/FAIL | {issue if any} |

### Data Generation
| Aspect | Status |
|--------|--------|
| Scale factors | PASS/FAIL |
| Distribution | PASS/FAIL |

### Findings

#### Critical (Spec Violations)
- {file:line}: {issue}

#### Enhancements (Optional Features)
- {suggestion}

### Recommendations
1. {priority action}
```

## Key Files

- `benchbox/core/tpc_compliance.py` - Compliance framework
- `benchbox/core/tpc_validation.py` - Validation rules
- `benchbox/core/tpc_patterns.py` - Pattern matching
- `benchbox/core/tpc_metrics.py` - Metrics calculation

## Notes

- TPC specifications are authoritative
- C tools output is reference implementation
- Compliance critical for valid results
- Document intentional deviations with justification
