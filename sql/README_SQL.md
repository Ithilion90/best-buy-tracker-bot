# PostgreSQL Setup

## 1. Create Role & Database
Run as superuser (e.g. `psql -U postgres`):

```sql
\i sql/01_role_db.sql
```

## 2. Create Schema & Tables
Switch into the database:

```sql
\c tracker
\i sql/02_schema.sql
```

## 3. (Optional) Triggers
```sql
\i sql/03_triggers_optional.sql
```

## 4. Environment
Add to `.env`:
```
DATABASE_URL=postgres://tracker:changeme@localhost:5432/tracker
```

## 5. Verify
```sql
\dt
SELECT * FROM users LIMIT 1;
```

## 6. Notes
- Uses dedicated schema `app` via search_path.
- Adjust password before production.
- For metrics/monitoring you can add extensions: `CREATE EXTENSION IF NOT EXISTS pg_stat_statements;`.
- Existing SQLite data is not auto-migrated.
