
# Compare Implementations

Compare benchmark implementations to identify inconsistencies and harmonization opportunities.

## Instructions

1. **Identify benchmarks to compare**: Often TPC-H vs TPC-DS, new vs established, or multi-benchmark pattern analysis

2. **Read core files** for each benchmark:
   - `benchbox/core/{benchmark}/benchmark.py`
   - `benchbox/core/{benchmark}/generator.py`
   - `benchbox/core/{benchmark}/queries.py`
   - `benchbox/core/{benchmark}/schema.py`
   - Runner implementations if present

3. **Compare structural patterns**:

   | Aspect | Check For |
   |--------|-----------|
   | Class | BaseBenchmark inheritance, method signatures, constructors |
   | Data Gen | Scale factors, binary integration, parallelism, output format |
   | Queries | Enumeration, parameterization, templates, dialect translation |
   | Schema | Table format, type mapping, constraints, multi-dialect support |
   | Runners | Unified API, connection handling, results, errors |

4. **Identify differences**:
   - Structural (class hierarchies)
   - Pattern inconsistencies
   - Feature gaps
   - API inconsistencies (names, signatures)
   - Quality variations (docs, types, errors)

5. **Categorize findings**:

   | Category | Impact |
   |----------|--------|
   | Critical | Breaks API consistency |
   | Important | Inconsistent patterns |
   | Enhancement | Nice-to-have |
   | Documentation | Missing/inconsistent docs |

6. **Suggest harmonization**: Better patterns, base class candidates, standardization, migration paths

7. **Create comparison report**

## Output Format

```markdown
## Comparison: {A} vs {B}

### Structural Similarities
- Both inherit from BaseBenchmark
- Both use X pattern for Y

### Key Differences

#### 1. {Category}
**{A}**: {description} - `{file:line}`
**{B}**: {description} - `{file:line}`
**Impact**: Critical/Important/Enhancement
**Recommendation**: {specific suggestion}

### Harmonization Opportunities
1. Move {X} to base class
2. Standardize {Y}
3. Adopt {Z} pattern from {A}

### Priority Actions
1. {most important}
2. {next priority}
```

## Key Files

- **Base**: `benchbox/core/base_benchmark.py`
- **Examples**: `benchbox/core/tpch/`, `benchbox/core/tpcds/`, `benchbox/core/ssb/`
- **Support**: `benchbox/core/platform_registry.py`, `benchbox/core/config_utils.py`

## Notes

- Focus on architectural patterns, not minor style
- Consider user-facing API impact
- Look for code duplication reduction
- Maintain backward compatibility
