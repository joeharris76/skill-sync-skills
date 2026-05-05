
# Live Platform Test

Execute tests against real cloud database platforms.

## Instructions

1. **Check credentials**:

   ```bash
   ls -la .env
   env | grep -E '(DATABRICKS|SNOWFLAKE|BIGQUERY|AWS|AZURE)'
   ```

   **Required per platform**:
   - **Databricks**: `DATABRICKS_SERVER_HOSTNAME`, `DATABRICKS_HTTP_PATH`, `DATABRICKS_TOKEN`
   - **Snowflake**: `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_PASSWORD`, `SNOWFLAKE_WAREHOUSE`, `SNOWFLAKE_DATABASE`, `SNOWFLAKE_SCHEMA`
   - **BigQuery**: `BIGQUERY_PROJECT`, `GOOGLE_APPLICATION_CREDENTIALS`
   - **Redshift**: `REDSHIFT_HOST`, `REDSHIFT_PORT`, `REDSHIFT_DATABASE`, `REDSHIFT_USER`, `REDSHIFT_PASSWORD`

2. **Warn if credentials missing**: Direct user to `.env.example`

3. **Run platform tests**:

   ```bash
   # All platforms
   make test-live-all

   # Single platform
   make test-live-databricks
   make test-live-snowflake
   make test-live-bigquery
   ```

4. **Monitor execution**: Live tests are slower (5-15 min per platform) due to network, upload, remote execution

5. **Analyze results**:

   | Area | Check |
   |------|-------|
   | Connection | Credentials valid, permissions OK |
   | Data Gen | Generates, uploads, tables created |
   | Queries | No errors, dialect correct, results returned |
   | Cleanup | Tables dropped, resources released |

6. **Common issues**:

   | Category | Issues |
   |----------|--------|
   | Auth | Invalid creds, expired tokens, missing permissions |
   | Network | Firewall, VPN required, DNS, timeouts |
   | Permissions | Can't create tables/schemas |
   | Quota | Suspended account, quota exceeded |
   | SQL | Translation failed, unsupported functions |

7. **Report results**

8. **Cost warning**: Live tests incur cloud costs. Suggest small scale factors, cleanup, off-peak timing.

## Output Format

```markdown
## Live Platform Test Results

### {Platform}
- **Connection**: PASS/FAIL
- **Data Generation**: {size} in {time}
- **Query Execution**: {passed}/{total}
- **Avg Query Time**: {time}

### Summary
| Platform | Status | Issues |
|----------|--------|--------|
| Databricks | PASS | - |
| Snowflake | WARN | Query 15 syntax |
| BigQuery | FAIL | Credentials needed |

### Next Steps
1. {action}
```

## Test Files

- `tests/integration/platforms/test_databricks_live.py`
- `tests/integration/platforms/test_snowflake_live.py`
- `tests/integration/platforms/test_bigquery_live.py`

## Security

- Never commit `.env` to git
- Use environment variables for CI/CD
- Rotate credentials regularly
- Use minimal permissions

## Notes

- Live tests pre-approved in settings.local.json
- Tests should clean up after themselves
- Use test-specific schemas/databases
- Keep test data small
