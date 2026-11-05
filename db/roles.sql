-- Creates the least-privilege role n8n uses for app data.
-- Run before schema.sql:  psql "$DATABASE_URL" -v app_password='...' -f db/roles.sql
SELECT format('CREATE ROLE askops_app LOGIN PASSWORD %L', :'app_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'askops_app')
\gexec
