-- =====================================================================
-- Ask Ops schema (Postgres 16 + pgvector)
-- Local:   runs automatically via db/init/01-init.sh on first start
-- Railway: psql "$DATABASE_URL" -v app_password='...' -f db/roles.sql
--          psql "$DATABASE_URL" -f db/schema.sql
-- Requires role askops_app to exist (db/roles.sql) for the GRANTs at the end.
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------
-- Workspaces: one per "company" set up on page 1. Auto-expire after 24h.
-- ---------------------------------------------------------------------
CREATE TABLE workspaces (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_name        text NOT NULL,
  website_url         text,
  extra_url           text,                       -- careers/benefits page, often on another domain
  industry            text,
  status              text NOT NULL DEFAULT 'building'
                        CHECK (status IN ('building', 'ready', 'failed')),
  demo_manager_email  text,                       -- real inbox that receives approval emails
  created_at          timestamptz NOT NULL DEFAULT now(),
  expires_at          timestamptz NOT NULL DEFAULT now() + interval '24 hours'
);

-- Real progress events that drive the build animation on the frontend.
CREATE TABLE build_events (
  id            bigserial PRIMARY KEY,
  workspace_id  uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  step          text NOT NULL,      -- crawl | extract | generate_policies | chunk | embed | seed_people | ready
  status        text NOT NULL CHECK (status IN ('started', 'progress', 'done', 'error')),
  message       text,
  progress      numeric(5,2) CHECK (progress BETWEEN 0 AND 100),
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX build_events_ws ON build_events (workspace_id, id);

-- ---------------------------------------------------------------------
-- People
-- Insert employees first with manager_id NULL, then set managers in a second pass.
-- ---------------------------------------------------------------------
CREATE TABLE employees (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id      uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  employee_code     text NOT NULL,
  full_name         text NOT NULL,
  email             text,
  title             text,
  department        text,
  access_role       text NOT NULL DEFAULT 'employee' CHECK (access_role IN ('employee', 'hr')),
  manager_id        uuid,
  hire_date         date,
  pto_balance_days  numeric(5,1) NOT NULL DEFAULT 0 CHECK (pto_balance_days >= 0),
  is_persona        boolean NOT NULL DEFAULT false,   -- selectable on page 2
  created_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (workspace_id, employee_code),
  UNIQUE (workspace_id, id),
  -- manager must be in the same workspace
  FOREIGN KEY (workspace_id, manager_id) REFERENCES employees (workspace_id, id)
);
CREATE INDEX employees_ws ON employees (workspace_id);
CREATE INDEX employees_manager ON employees (manager_id);

-- Salaries live in their own table. askops_app can INSERT here but never SELECT;
-- the only read path is get_compensation(), which enforces the HR role.
CREATE TABLE compensation (
  employee_id     uuid PRIMARY KEY REFERENCES employees(id) ON DELETE CASCADE,
  base_salary     numeric(12,2) NOT NULL CHECK (base_salary >= 0),
  currency        text NOT NULL DEFAULT 'USD',
  effective_date  date
);

-- The demo has no login: the setup page picks the active workspace + persona.
-- Tools read identity from here and NEVER from model-supplied arguments.
CREATE TABLE active_session (
  singleton     boolean PRIMARY KEY DEFAULT true CHECK (singleton),
  workspace_id  uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  employee_id   uuid NOT NULL,
  updated_at    timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (workspace_id, employee_id) REFERENCES employees (workspace_id, id)
);

-- ---------------------------------------------------------------------
-- Knowledge (RAG)
-- Embeddings: Gemini, 768 dimensions. Change vector(768) everywhere if the model changes.
-- ---------------------------------------------------------------------
CREATE TABLE documents (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id  uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  source_type   text NOT NULL CHECK (source_type IN ('website', 'upload', 'sample')),
  title         text NOT NULL,
  source_url    text,
  content       text NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX documents_ws ON documents (workspace_id);

CREATE TABLE chunks (
  id            bigserial PRIMARY KEY,
  document_id   uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  workspace_id  uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  chunk_index   int NOT NULL,
  content       text NOT NULL,
  embedding     vector(768) NOT NULL,
  metadata      jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX chunks_ws ON chunks (workspace_id);
CREATE INDEX chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops);

-- Semantic cache. Key = workspace + role + question meaning.
-- Only knowledge answers are cached; never balances, tickets or salaries.
CREATE TABLE semantic_cache (
  id                  bigserial PRIMARY KEY,
  workspace_id        uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  access_role         text NOT NULL CHECK (access_role IN ('employee', 'hr')),
  question            text NOT NULL,
  question_embedding  vector(768) NOT NULL,
  answer              text NOT NULL,
  sources             jsonb NOT NULL DEFAULT '[]'::jsonb,
  hit_count           int NOT NULL DEFAULT 0,
  created_at          timestamptz NOT NULL DEFAULT now(),
  expires_at          timestamptz NOT NULL DEFAULT now() + interval '6 hours'
);
CREATE INDEX semantic_cache_ws_role ON semantic_cache (workspace_id, access_role);
CREATE INDEX semantic_cache_hnsw ON semantic_cache USING hnsw (question_embedding vector_cosine_ops);

-- ---------------------------------------------------------------------
-- Work items
-- ---------------------------------------------------------------------
CREATE SEQUENCE pto_code_seq START 1001;

CREATE TABLE pto_requests (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code                 text NOT NULL UNIQUE DEFAULT ('PTO-' || nextval('pto_code_seq')),
  workspace_id         uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  employee_id          uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
  start_date           date NOT NULL,
  end_date             date NOT NULL,
  days                 numeric(4,1) NOT NULL CHECK (days > 0),
  reason               text,
  status               text NOT NULL DEFAULT 'pending'
                         CHECK (status IN ('pending', 'approved', 'rejected', 'cancelled')),
  approver_id          uuid REFERENCES employees(id),
  approval_token_hash  text UNIQUE,              -- sha256 hex of the emailed token; NULL once used
  token_expires_at     timestamptz,
  decided_at           timestamptz,
  decided_via          text CHECK (decided_via IN ('email', 'chat')),
  decision_note        text,
  created_at           timestamptz NOT NULL DEFAULT now(),
  CHECK (end_date >= start_date)
);
CREATE INDEX pto_requests_ws_status ON pto_requests (workspace_id, status);
CREATE INDEX pto_requests_employee ON pto_requests (employee_id);

CREATE SEQUENCE ticket_code_seq START 2001;

CREATE TABLE tickets (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code           text NOT NULL UNIQUE DEFAULT ('TCK-' || nextval('ticket_code_seq')),
  workspace_id   uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  employee_id    uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
  category       text NOT NULL CHECK (category IN ('it', 'hr', 'facilities', 'other')),
  title          text NOT NULL,
  description    text,
  priority       text NOT NULL DEFAULT 'normal' CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
  status         text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'in_progress', 'resolved', 'closed')),
  assigned_team  text,
  is_escalation  boolean NOT NULL DEFAULT false,
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now(),
  resolved_at    timestamptz
);
CREATE INDEX tickets_ws_status ON tickets (workspace_id, status);
CREATE INDEX tickets_employee ON tickets (employee_id);

-- ---------------------------------------------------------------------
-- Observability
-- ---------------------------------------------------------------------
CREATE TABLE conversations (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id      uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  employee_id       uuid REFERENCES employees(id) ON DELETE CASCADE,
  external_id       text,                         -- Copilot Studio conversation id, if available
  started_at        timestamptz NOT NULL DEFAULT now(),
  last_activity_at  timestamptz NOT NULL DEFAULT now(),
  outcome           text CHECK (outcome IN ('resolved', 'escalated', 'abandoned')),
  feedback          smallint CHECK (feedback IN (-1, 1)),
  feedback_comment  text,
  UNIQUE (workspace_id, external_id)
);

CREATE TABLE turns (
  id                bigserial PRIMARY KEY,
  conversation_id   uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  role              text NOT NULL CHECK (role IN ('user', 'assistant')),
  content_redacted  text NOT NULL,                -- PII removed before insert
  route             text CHECK (route IN ('faq', 'action', 'sensitive', 'off_topic', 'smalltalk')),
  cache_hit         boolean NOT NULL DEFAULT false,
  latency_ms        int,
  created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX turns_conversation ON turns (conversation_id, id);

-- One row per tool call: feeds the "Behind the scenes" panel and the dashboard.
CREATE TABLE tool_calls (
  id               bigserial PRIMARY KEY,
  workspace_id     uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
  conversation_id  uuid REFERENCES conversations(id) ON DELETE CASCADE,
  employee_id      uuid REFERENCES employees(id) ON DELETE CASCADE,
  tool_name        text NOT NULL,
  input            jsonb NOT NULL DEFAULT '{}'::jsonb,
  output           jsonb,
  status           text NOT NULL CHECK (status IN ('success', 'error', 'denied')),
  error            text,
  latency_ms       int,
  created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX tool_calls_ws_recent ON tool_calls (workspace_id, id DESC);

-- =====================================================================
-- Functions
-- =====================================================================

-- Point the demo at a workspace + persona (called by the setup page).
CREATE OR REPLACE FUNCTION set_active_session(p_workspace_id uuid, p_employee_id uuid)
RETURNS void LANGUAGE sql AS $$
  INSERT INTO active_session (singleton, workspace_id, employee_id, updated_at)
  VALUES (true, p_workspace_id, p_employee_id, now())
  ON CONFLICT (singleton) DO UPDATE
    SET workspace_id = EXCLUDED.workspace_id,
        employee_id  = EXCLUDED.employee_id,
        updated_at   = now();
$$;

-- Who is "logged in" right now. Every tool starts with this.
CREATE OR REPLACE FUNCTION current_identity()
RETURNS TABLE (workspace_id uuid, employee_id uuid, full_name text, title text,
               access_role text, manager_id uuid, company_name text, demo_manager_email text)
LANGUAGE sql STABLE AS $$
  SELECT s.workspace_id, e.id, e.full_name, e.title, e.access_role, e.manager_id,
         w.company_name, w.demo_manager_email
  FROM active_session s
  JOIN employees e  ON e.id = s.employee_id
  JOIN workspaces w ON w.id = s.workspace_id;
$$;

-- Vector search over a workspace's knowledge.
CREATE OR REPLACE FUNCTION match_chunks(p_workspace_id uuid, p_query vector,
                                        p_count int DEFAULT 5, p_min_similarity float DEFAULT 0.5)
RETURNS TABLE (chunk_id bigint, document_id uuid, title text, source_type text,
               source_url text, content text, similarity float)
LANGUAGE sql STABLE AS $$
  SELECT c.id, d.id, d.title, d.source_type, d.source_url, c.content,
         1 - (c.embedding <=> p_query) AS similarity
  FROM chunks c
  JOIN documents d ON d.id = c.document_id
  WHERE c.workspace_id = p_workspace_id
    AND 1 - (c.embedding <=> p_query) >= p_min_similarity
  ORDER BY c.embedding <=> p_query
  LIMIT p_count;
$$;

-- Semantic cache lookup. Returns at most one hit and bumps its counter.
CREATE OR REPLACE FUNCTION lookup_cache(p_workspace_id uuid, p_role text, p_query vector,
                                        p_min_similarity float DEFAULT 0.92)
RETURNS TABLE (cache_id bigint, answer text, sources jsonb, similarity float)
LANGUAGE plpgsql AS $$
DECLARE
  v_id bigint;
BEGIN
  SELECT sc.id INTO v_id
  FROM semantic_cache sc
  WHERE sc.workspace_id = p_workspace_id
    AND sc.access_role = p_role
    AND sc.expires_at > now()
    AND 1 - (sc.question_embedding <=> p_query) >= p_min_similarity
  ORDER BY sc.question_embedding <=> p_query
  LIMIT 1;

  IF v_id IS NULL THEN
    RETURN;
  END IF;

  UPDATE semantic_cache SET hit_count = hit_count + 1 WHERE id = v_id;

  RETURN QUERY
    SELECT sc.id, sc.answer, sc.sources, 1 - (sc.question_embedding <=> p_query)
    FROM semantic_cache sc WHERE sc.id = v_id;
END $$;

-- Approve/reject atomically. Locks the row so a double click can't decide twice,
-- and deducts the balance only on approval.
CREATE OR REPLACE FUNCTION decide_pto(p_request_id uuid, p_decision text, p_via text,
                                      p_note text DEFAULT NULL)
RETURNS pto_requests LANGUAGE plpgsql AS $$
DECLARE
  r pto_requests;
BEGIN
  IF p_decision NOT IN ('approved', 'rejected') THEN
    RAISE EXCEPTION 'INVALID_DECISION: %', p_decision;
  END IF;

  SELECT * INTO r FROM pto_requests WHERE id = p_request_id FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'NOT_FOUND: PTO request does not exist';
  END IF;
  IF r.status <> 'pending' THEN
    RAISE EXCEPTION 'ALREADY_DECIDED: % is already %', r.code, r.status;
  END IF;

  IF p_decision = 'approved' THEN
    UPDATE employees
       SET pto_balance_days = pto_balance_days - r.days
     WHERE id = r.employee_id AND pto_balance_days >= r.days;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'INSUFFICIENT_BALANCE: not enough PTO for %', r.code;
    END IF;
  END IF;

  UPDATE pto_requests
     SET status = p_decision,
         decided_at = now(),
         decided_via = p_via,
         decision_note = p_note,
         approval_token_hash = NULL          -- email link becomes single-use
   WHERE id = p_request_id
  RETURNING * INTO r;

  RETURN r;
END $$;

-- Used by the email confirmation page. The raw token only ever exists in the email.
CREATE OR REPLACE FUNCTION decide_pto_by_token(p_token text, p_decision text, p_note text DEFAULT NULL)
RETURNS pto_requests LANGUAGE plpgsql AS $$
DECLARE
  v_id uuid;
BEGIN
  SELECT id INTO v_id
  FROM pto_requests
  WHERE approval_token_hash = encode(sha256(convert_to(p_token, 'UTF8')), 'hex')
    AND token_expires_at > now();

  IF v_id IS NULL THEN
    RAISE EXCEPTION 'INVALID_LINK: link is invalid, expired or already used';
  END IF;

  RETURN decide_pto(v_id, p_decision, 'email', p_note);
END $$;

-- Read a request by token without deciding (for the confirmation page's GET).
CREATE OR REPLACE FUNCTION peek_pto_by_token(p_token text)
RETURNS TABLE (code text, employee_name text, start_date date, end_date date,
               days numeric, reason text, status text)
LANGUAGE sql STABLE AS $$
  SELECT p.code, e.full_name, p.start_date, p.end_date, p.days, p.reason, p.status
  FROM pto_requests p
  JOIN employees e ON e.id = p.employee_id
  WHERE p.approval_token_hash = encode(sha256(convert_to(p_token, 'UTF8')), 'hex')
    AND p.token_expires_at > now();
$$;

-- The ONLY way to read salaries. SECURITY DEFINER lets it read a table that
-- askops_app cannot; the HR check happens inside the database.
CREATE OR REPLACE FUNCTION get_compensation(p_requester_id uuid, p_target_id uuid)
RETURNS TABLE (employee_code text, full_name text, title text,
               base_salary numeric, currency text, effective_date date)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM employees req
    JOIN employees tgt ON tgt.workspace_id = req.workspace_id
    WHERE req.id = p_requester_id
      AND tgt.id = p_target_id
      AND req.access_role = 'hr'
  ) THEN
    RAISE EXCEPTION 'ACCESS_DENIED: compensation data is restricted to HR'
      USING ERRCODE = '42501';
  END IF;

  RETURN QUERY
    SELECT e.employee_code, e.full_name, e.title, c.base_salary, c.currency, c.effective_date
    FROM employees e
    JOIN compensation c ON c.employee_id = e.id
    WHERE e.id = p_target_id;
END $$;

-- Called by an n8n cron workflow (hourly) to enforce the 24h data lifetime.
CREATE OR REPLACE FUNCTION delete_expired_workspaces()
RETURNS int LANGUAGE plpgsql AS $$
DECLARE
  n int;
BEGIN
  DELETE FROM semantic_cache WHERE expires_at < now();
  DELETE FROM workspaces WHERE expires_at < now();
  GET DIAGNOSTICS n = ROW_COUNT;
  RETURN n;
END $$;

-- =====================================================================
-- Dashboard metrics (the JD's success metrics)
-- =====================================================================
CREATE OR REPLACE VIEW workspace_metrics AS
SELECT
  w.id AS workspace_id,
  w.company_name,
  conv.total            AS conversations,
  conv.resolved,
  conv.escalated,
  conv.abandoned,
  CASE WHEN conv.total > 0
       THEN round(100.0 * conv.resolved / conv.total, 1) END            AS resolution_rate_pct,
  conv.thumbs_up,
  conv.thumbs_down,
  CASE WHEN conv.thumbs_up + conv.thumbs_down > 0
       THEN round(100.0 * conv.thumbs_up / (conv.thumbs_up + conv.thumbs_down), 1) END AS csat_pct,
  tc.calls              AS tool_calls,
  tc.errors             AS tool_errors,
  tc.denied             AS tool_denied,
  tc.avg_latency_ms,
  t.cache_hits,
  t.assistant_turns,
  CASE WHEN t.assistant_turns > 0
       THEN round(100.0 * t.cache_hits / t.assistant_turns, 1) END       AS cache_hit_rate_pct
FROM workspaces w
LEFT JOIN LATERAL (
  SELECT count(*)                                          AS total,
         count(*) FILTER (WHERE outcome = 'resolved')      AS resolved,
         count(*) FILTER (WHERE outcome = 'escalated')     AS escalated,
         count(*) FILTER (WHERE outcome = 'abandoned')     AS abandoned,
         count(*) FILTER (WHERE feedback = 1)              AS thumbs_up,
         count(*) FILTER (WHERE feedback = -1)             AS thumbs_down
  FROM conversations c WHERE c.workspace_id = w.id
) conv ON true
LEFT JOIN LATERAL (
  SELECT count(*)                                          AS calls,
         count(*) FILTER (WHERE status = 'error')          AS errors,
         count(*) FILTER (WHERE status = 'denied')         AS denied,
         round(avg(latency_ms))                            AS avg_latency_ms
  FROM tool_calls tc WHERE tc.workspace_id = w.id
) tc ON true
LEFT JOIN LATERAL (
  SELECT count(*) FILTER (WHERE tu.cache_hit)              AS cache_hits,
         count(*) FILTER (WHERE tu.role = 'assistant')     AS assistant_turns
  FROM turns tu JOIN conversations c ON c.id = tu.conversation_id
  WHERE c.workspace_id = w.id
) t ON true;

-- =====================================================================
-- Permissions for the app role used by n8n
-- =====================================================================
GRANT USAGE ON SCHEMA public TO askops_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO askops_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO askops_app;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO askops_app;

-- Salaries: write-only for the app. Reading goes through get_compensation().
REVOKE ALL ON compensation FROM askops_app;
GRANT INSERT ON compensation TO askops_app;
