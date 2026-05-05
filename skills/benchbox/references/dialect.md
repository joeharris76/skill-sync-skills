
# Dialect Translation Test

Verify SQL queries translate correctly across database dialects using sqlglot.

## Instructions

1. **Understand context**:
   - Source dialect (usually DuckDB)
   - Target platforms (Snowflake, BigQuery, Databricks, ClickHouse, Redshift, etc.)
   - Specific query or full benchmark

2. **Test single query**:

   ```python
   import sqlglot

   query = "SELECT * FROM table WHERE date > '2023-01-01'"
   dialects = ['duckdb', 'snowflake', 'bigquery', 'databricks', 'clickhouse']

   for dialect in dialects:
       try:
           translated = sqlglot.transpile(query, read='duckdb', write=dialect)[0]
           print(f"{dialect}: OK")
       except Exception as e:
           print(f"{dialect}: FAIL - {e}")
   ```

3. **Test benchmark queries**:
   ```python
   from benchbox.core.tpch import TPCH
   tpch = TPCH(scale_factor=1)
   for dialect in ['duckdb', 'snowflake', 'bigquery']:
       query = tpch.get_query(query_num=1, dialect=dialect)
       print(f"{dialect}:\n{query}")
   ```

4. **Check common translation issues**:

   | Category | Examples |
   |----------|----------|
   | Types | `BIGINT` vs `INT64`, `VARCHAR` vs `STRING` |
   | Functions | `DATE_ADD` vs `DATEADD`, `CONCAT` vs `\|\|` |
   | Syntax | `LIMIT` vs `TOP`, quote characters |
   | Casts | `::type` vs `CAST(x AS type)` |

5. **Test execution** if possible (create test table, verify results match)

6. **Report findings**

## Output Format

```markdown
## Dialect Translation: {query/benchmark}

### Results
| Platform | Status | Issue |
|----------|--------|-------|
| Snowflake | PASS | - |
| BigQuery | PASS | - |
| ClickHouse | FAIL | DATE_ADD unsupported |

### Issues Found
#### {Platform} - {Function/Syntax}
- **Original**: `{sql}`
- **Error**: {error}
- **Fix**: {suggestion}

### Recommendations
1. {action}
```

## Platform Characteristics

| Platform | Key Notes |
|----------|-----------|
| DuckDB | PostgreSQL-compatible, good source dialect |
| Snowflake | Case-insensitive, uppercase functions |
| BigQuery | Backticks for identifiers, StandardSQL |
| Databricks | Spark SQL, Delta Lake features |
| ClickHouse | Unique types, different function names |
| Redshift | PostgreSQL-based with limitations |

## Notes

- sqlglot is the translation engine (in dependencies)
- Not all SQL features translate perfectly
- BenchBox platform adapters handle many edge cases
- Test with actual database when possible
