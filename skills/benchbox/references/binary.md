
# Binary Wrapper Check

Verify TPC C binaries are properly integrated and functioning.

## Instructions

1. **Check binary locations**:

   ```bash
   ls -la _binaries/tpc-h/*/
   ls -la _binaries/tpc-ds/*/
   ```

   Platform directories: `darwin-arm64`, `darwin-x86_64`, `linux-x86_64`, `linux-arm64`, `windows-x86_64`

2. **Verify executables**:

   | Benchmark | Binaries | Templates |
   |-----------|----------|-----------|
   | TPC-H | `dbgen`, `qgen` | `queries/`, `variants/` |
   | TPC-DS | `dsdgen`, `dsqgen` | `query_templates/` |

3. **Test binary execution**:

   **TPC-H**:
   ```bash
   env DSS_QUERY=_sources/tpc-h/dbgen/queries \
     _binaries/tpc-h/darwin-arm64/qgen -s 1 -d 1
   ```

   **TPC-DS**:
   ```bash
   _binaries/tpc-ds/darwin-arm64/dsqgen \
     -TEMPLATE query1.tpl \
     -DIRECTORY _sources/tpc-ds/query_templates \
     -DIALECT netezza -RNGSEED 1 -FILTER Y
   ```

4. **Check Python wrappers**:
   - TPC-H: `benchbox/core/tpch/c_tools.py` - `_execute_qgen()`
   - TPC-DS: `benchbox/core/tpcds/c_tools.py` - `_execute_dsqgen()`

5. **Test through Python API**:

   ```python
   from benchbox.core.tpch import TPCH
   tpch = TPCH(scale_factor=1)
   print(tpch.get_query(query_num=1))
   ```

6. **Check common issues**:

   | Category | Issues |
   |----------|--------|
   | Binary | Not found, not executable, wrong platform |
   | Execution | Missing env vars, wrong template path |
   | Output | Encoding issues, unsubstituted parameters |
   | Platform | ARM/x86 mismatch, Gatekeeper blocking |

7. **Report findings**

## Output Format

```markdown
## Binary Integration Check

### Availability
| Benchmark | Platform | Status |
|-----------|----------|--------|
| TPC-H | darwin-arm64 | Present |
| TPC-DS | darwin-arm64 | Present |

### Execution Tests

#### TPC-H Query 1
- Binary: PASS/FAIL
- Query generated: PASS/FAIL
- Python wrapper: PASS/FAIL

### Issues Found
1. **{Issue}**
   - Location: {file:line}
   - Impact: {description}

### Recommendations
1. {action}
```

## Platform Detection

BenchBox auto-detects: `{system}-{machine}` → `_binaries/tpc-h/{platform}/qgen`

## Notes

- Binaries are platform-specific
- macOS may require security approval for unsigned binaries
- TPC specs require official C tools for compliance
- Python wrappers should be thin layers
