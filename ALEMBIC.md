# Alembic For Paylink

## Current Position

The database already exists. Alembic is introduced with a baseline revision:

- `20260325_000001_baseline_existing_schema`
- `20260325_000002_runtime_technical_tables`

The baseline marks the existing schema as the starting point. The next revision captures technical tables and schema updates that were previously created at runtime.

## Commands

From `backend/`:

```bash
alembic current
alembic upgrade head
alembic revision --autogenerate -m "describe schema change"
alembic revision -m "manual sql change"
```

## Important Rules

- Do not create new tables at app startup when the change can be migrated.
- Move `ensure_*_schema` helpers into Alembic progressively.
- Put SQL functions, views, and triggers in migrations with `op.execute(...)`.
- Apply migrations to `staging` first, then `production`.

## Recommended Next Steps

1. Stamp the existing staging and prod databases with the baseline revision.
2. Upgrade staging to `head`.
3. After all environments are upgraded, gradually remove runtime schema creation from application startup.
