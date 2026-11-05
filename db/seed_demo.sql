-- Demo workspace for local testing of tools before the ingestion pipeline exists.
-- Run: docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d askops' < db/seed_demo.sql
-- Fixed UUIDs so workflows and curl tests can reference them. Safe to re-run.

BEGIN;

DELETE FROM workspaces WHERE id = '00000000-0000-0000-0000-000000000001';

INSERT INTO workspaces (id, company_name, website_url, industry, status, demo_manager_email, webhook_url, expires_at)
VALUES ('00000000-0000-0000-0000-000000000001', 'Northwind Labs', NULL, 'Software',
        'ready', 'your-email@example.com', 'http://localhost:5678', now() + interval '100 years');

-- Pass 1: people (managers set in pass 2)
INSERT INTO employees (id, workspace_id, employee_code, full_name, email, title, department,
                       access_role, hire_date, pto_balance_days, is_persona) VALUES
  ('00000000-0000-0000-0000-000000000101', '00000000-0000-0000-0000-000000000001', 'EMP-042',
   'Adarsh Gella', 'adarsh.gella@northwind.example', 'Software Engineer', 'Engineering',
   'employee', '2025-03-10', 8, true),
  ('00000000-0000-0000-0000-000000000102', '00000000-0000-0000-0000-000000000001', 'EMP-007',
   'John Lee', 'john.lee@northwind.example', 'HR Manager', 'People',
   'hr', '2019-06-01', 15, true),
  ('00000000-0000-0000-0000-000000000103', '00000000-0000-0000-0000-000000000001', 'EMP-015',
   'Maya Patel', 'maya.patel@northwind.example', 'Engineering Manager', 'Engineering',
   'employee', '2020-01-15', 12, false),
  ('00000000-0000-0000-0000-000000000104', '00000000-0000-0000-0000-000000000001', 'EMP-051',
   'Sara Kim', 'sara.kim@northwind.example', 'QA Engineer', 'Engineering',
   'employee', '2024-08-19', 10, false),
  ('00000000-0000-0000-0000-000000000105', '00000000-0000-0000-0000-000000000001', 'EMP-033',
   'Leo Martinez', 'leo.martinez@northwind.example', 'IT Support Specialist', 'IT',
   'employee', '2022-11-07', 9, false);

-- Pass 2: reporting lines
UPDATE employees SET manager_id = '00000000-0000-0000-0000-000000000103'
 WHERE id IN ('00000000-0000-0000-0000-000000000101', '00000000-0000-0000-0000-000000000104');
UPDATE employees SET manager_id = '00000000-0000-0000-0000-000000000102'
 WHERE id IN ('00000000-0000-0000-0000-000000000103', '00000000-0000-0000-0000-000000000105');

INSERT INTO compensation (employee_id, base_salary, currency, effective_date) VALUES
  ('00000000-0000-0000-0000-000000000101', 118000, 'USD', '2026-01-01'),
  ('00000000-0000-0000-0000-000000000102', 135000, 'USD', '2026-01-01'),
  ('00000000-0000-0000-0000-000000000103', 172000, 'USD', '2026-01-01'),
  ('00000000-0000-0000-0000-000000000104', 104000, 'USD', '2026-01-01'),
  ('00000000-0000-0000-0000-000000000105',  86000, 'USD', '2026-01-01');

INSERT INTO tickets (workspace_id, employee_id, category, title, description, priority, status, assigned_team)
VALUES ('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000101',
        'it', 'VPN disconnects every hour', 'Started after the latest client update.', 'normal',
        'in_progress', 'IT Support');

-- Start as Adarsh
SELECT set_active_session('00000000-0000-0000-0000-000000000001',
                          '00000000-0000-0000-0000-000000000101');

COMMIT;
