
# Benchmark Plan and Execute

Complete workflow for implementing new features, benchmarks, or major changes.

## Workflow

### Phase 1: Planning

1. **Understand requirements** thoroughly
2. **Research** existing implementations
3. **Identify** affected components
4. **List** all files that need changes
5. **Define** success criteria
6. **Estimate** complexity

**Create plan document**:

```markdown
## {Feature} Implementation Plan

### Overview
{What and why}

### Requirements
1. {requirement}

### Architecture
- New files: {list}
- Modified files: {list}
- Integration points: {list}

### Implementation Steps
1. **{Phase 1}** (Est: Xh)
   - {task}

### Testing Strategy
- Unit: {what}
- Integration: {what}

### Success Criteria
- [ ] Tests pass
- [ ] Docs complete
- [ ] Performance acceptable

### Risks
- {risk} → {mitigation}
```

2. **Save plan** to `_project/{feature}_implementation_plan.md`

3. **Present to user** for approval - NEVER implement without confirmation

### Phase 2: Implementation (after approval)

1. **Track progress** with TODO items
2. **Follow BenchBox patterns** (use existing code as templates)
3. **Test continuously** after each major change:
   ```bash
   make test-fast
   uv run -- python -m pytest tests/path/to/tests.py -v
   ```

### Phase 3: Finalization

1. **Quality checks**:
   ```bash
   make lint && make format && make typecheck && make test-all
   ```

2. **Update documentation**: Docstrings, README, examples

3. **Create completion summary** at `_project/{feature}_completion_summary.md`

4. **Update project TODOs**

## Output Format

**After planning**:
```markdown
## Implementation Plan Created

**Plan**: `_project/{name}_implementation_plan.md`

**Summary**:
- X new files
- Y modified files
- Estimated: N hours

**Phases**:
1. {phase} - {description}

**Ready to proceed?**
```

**After completion**:
```markdown
## Implementation Complete!

**Feature**: {name}
**Files**: X new, Y modified
**Tests**: All passing (N new, M total)
**Quality**: All checks passed

**Documentation**:
- Plan: `_project/{name}_plan.md`
- Summary: `_project/{name}_summary.md`

**Ready for**: Code review, commit
```

## Common Workflows

| Type | Key Steps |
|------|-----------|
| New Benchmark | Research spec, list queries, define schema, integrate C tools |
| Platform Adapter | Study docs, implement adapter, test connection/queries |
| Feature Enhancement | Analyze current, design improvements, maintain compatibility |
| Bug Fix | Reproduce, identify root cause, fix, add regression test |

## Best Practices

- **Plan**: Research thoroughly, break into phases, identify risks
- **Implement**: Track progress, test continuously, follow patterns
- **Test**: Write as you code, test success and error cases
- **Document**: As you code, explain "why" not just "what"

## Notes

- Planning prevents costly rework
- User approval required before major changes
- Continuous testing catches issues early
- Documentation is as important as code
