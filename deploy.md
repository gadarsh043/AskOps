# AskOps Deployment Guide

Deploy AskOps to Railway (backend) + Netlify (frontend). The whole process takes ~45 minutes.

---

## Overview

```
Netlify (web/)  ──HTTP──▶  Railway n8n  ──SQL──▶  Railway Postgres (pgvector)
                                   ▲
                        Copilot Studio (optional)
```

---

## Part 1: Railway — Postgres + n8n

### 1.1 Create a Railway project

1. Go to [railway.app](https://railway.app) and sign in (GitHub login recommended).
2. Click **New Project** → **Empty project**.
3. Name it **AskOps**.

### 1.2 Add Postgres (pgvector)

1. In the project, click **+ Add a Service** → **Database** → **PostgreSQL**.
   - Railway uses the standard Postgres image. We need pgvector, so use a custom image.
2. Click the Postgres service → **Settings** → **Image** → change to: `pgvector/pgvector:pg16`
3. Click **Deploy**.
4. Once deployed, go to **Variables** tab and note:
   - `POSTGRES_HOST` (e.g., `containers.railway.internal`)
   - `POSTGRES_PORT` (usually `5432`)
   - `POSTGRES_PASSWORD`
   - `POSTGRES_USER` (usually `postgres`)
   - `RAILWAY_POSTGRES_URL` — full connection string

### 1.3 Initialize the database

**Option A: Railway CLI**
```bash
# Install Railway CLI
brew install railway         # Mac
# or: npm install -g @railway/cli

# Login
railway login

# Connect to your project
railway link    # select AskOps project

# Run schema setup
railway run psql "$RAILWAY_POSTGRES_URL" -f db/roles.sql
railway run psql "$RAILWAY_POSTGRES_URL" -f db/schema.sql
railway run psql "$RAILWAY_POSTGRES_URL" -f db/migrations/001_add_webhook_url_to_workspaces.sql
railway run psql "$RAILWAY_POSTGRES_URL" -f db/migrations/002_peek_pto_by_token_raise.sql
railway run psql "$RAILWAY_POSTGRES_URL" -f db/migrations/003_fix_token_hash_lookup.sql
railway run psql "$RAILWAY_POSTGRES_URL" -f db/seed_demo.sql
```

**Option B: psql via TCP proxy**
1. In Railway Postgres settings → **Connect** → enable **Public Networking**.
2. Copy the external connection string.
3. Run:
   ```bash
   export PG_URL="<external connection string>"
   psql "$PG_URL" -f db/roles.sql
   psql "$PG_URL" -f db/schema.sql
   psql "$PG_URL" -f db/migrations/001_add_webhook_url_to_workspaces.sql
   psql "$PG_URL" -f db/migrations/002_peek_pto_by_token_raise.sql
   psql "$PG_URL" -f db/migrations/003_fix_token_hash_lookup.sql
   psql "$PG_URL" -f db/seed_demo.sql
   ```

**Seed the knowledge base:**
```bash
# Update DB connection in seed script for Railway
PGHOST=<host> PGPORT=<port> PGUSER=postgres PGPASSWORD=<pw> PGDATABASE=askops \
  python3 scripts/seed_sample_kb.py
```

### 1.4 Add n8n

1. In the Railway project, click **+ Add a Service** → **GitHub Repo** (or **Docker Image**).
2. Use Docker Image: `n8nio/n8n:1.97.1`
3. Click **Add Variables** and set:

   | Variable | Value |
   |----------|-------|
   | `N8N_ENCRYPTION_KEY` | `b1cd3c8bc4e4c47ee61bab9ce32477f18ccba4d97f18981220e12a12654e3f11` |
   | `DB_TYPE` | `postgresdb` |
   | `DB_POSTGRESDB_HOST` | (Railway internal host from step 1.2) |
   | `DB_POSTGRESDB_PORT` | `5432` |
   | `DB_POSTGRESDB_DATABASE` | `n8n` |
   | `DB_POSTGRESDB_USER` | `postgres` |
   | `DB_POSTGRESDB_PASSWORD` | (Railway Postgres password) |
   | `N8N_HOST` | `0.0.0.0` |
   | `N8N_PORT` | `5678` |
   | `WEBHOOK_URL` | `https://<your-n8n-railway-domain>` (set after deploy) |
   | `N8N_SECURE_COOKIE` | `false` |
   | `N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS` | `false` |
   | `TZ` | `America/New_York` |

4. Under **Settings** → **Networking** → enable **Public Domain**. Railway assigns a URL like `askops-n8n-production.up.railway.app`.
5. Set `WEBHOOK_URL` to `https://askops-n8n-production.up.railway.app` (use your actual URL).
6. Click **Deploy**.
7. Wait for n8n to start (~60 seconds). Open the URL to confirm the n8n UI loads.

### 1.5 Set Railway usage limit

1. In Railway dashboard → **Settings** → **Usage Limits** → set **Spending Limit** to `$5`.
2. This prevents surprise charges. Railway free tier gives $5/month credit.

---

## Part 2: Configure n8n on Railway

### 2.1 Create credentials in Railway n8n

Open `https://<your-n8n-railway-domain>` and sign up (create an account with any email).

Go to **Settings** → **Credentials** and create:

#### Postgres credential (AskOps Postgres)
- Type: **Postgres**
- Host: (Railway internal Postgres host)
- Database: `askops`
- User: `askops_app`
- Password: `403d9c05e839e54940bb24c767652598f3b9d59168e165feb2384be82570e41c`
- SSL: Enabled (required for Railway)

> The `askops_app` role was created by `db/roles.sql`. Confirm it exists:
> ```sql
> SELECT rolname FROM pg_roles WHERE rolname='askops_app';
> ```

#### Groq credential (AskOps Groq)
- Type: **HTTP Header Auth**
- Name: `Authorization`
- Value: `Bearer <GROQ_API_KEY from .env>`

#### Gemini credential (AskOps Gemini)
- Type: **HTTP Query Auth**
- Name: `key`
- Value: `<GEMINI_API_KEY from .env>`

#### Gmail SMTP credential (AskOps Gmail SMTP)
- Type: **SMTP**
- Host: `smtp.gmail.com`
- Port: `465`
- SSL: Yes
- User: `<GMAIL_USER from .env>`
- Password: `<GMAIL_SMTP from .env>` (Gmail app password)

### 2.2 Note credential IDs

After creating each credential, note its ID (visible in the URL when editing).

### 2.3 Update the build scripts with Railway credential IDs

Edit `scripts/build_mcp_workflow.py` and `scripts/build_api_workflows.py`:
```python
# Replace these with the Railway n8n credential IDs:
CRED      = {'postgres': {'id': '<RAILWAY_POSTGRES_CRED_ID>', 'name': 'AskOps Postgres'}}
GROQ_CRED = {'httpHeaderAuth': {'id': '<RAILWAY_GROQ_CRED_ID>', 'name': 'AskOps Groq'}}
GEMINI_CRED = {'httpQueryAuth': {'id': '<RAILWAY_GEMINI_CRED_ID>', 'name': 'AskOps Gemini'}}
SMTP_CRED = {'smtp': {'id': '<RAILWAY_SMTP_CRED_ID>', 'name': 'AskOps Gmail SMTP'}}

# Update BASE to Railway n8n URL:
BASE = 'https://<your-n8n-railway-domain>'
# Update API_KEY to Railway n8n API key
```

**Get Railway n8n API key:**
1. In Railway n8n → **Settings** → **API** → **Create API Key**.

### 2.4 Deploy workflows to Railway n8n

```bash
# Update BASE and API_KEY in scripts, then:
python3 scripts/build_mcp_workflow.py
python3 scripts/build_api_workflows.py

# Import the other workflows via CLI import:
# In Railway n8n: Workflows → ⋮ → Import from file
# Import: n8n/workflows/ingest.website.json
# Import: n8n/workflows/cron.cleanup.json
```

### 2.5 Re-add credentials in imported workflows

After importing `ingest.website.json` and `cron.cleanup.json`, open each workflow and reconnect the Postgres credential (the imported credential ID won't match Railway's).

### 2.6 Update webhook_url in the demo workspace

```sql
UPDATE workspaces 
SET webhook_url = 'https://<your-n8n-railway-domain>'
WHERE id = '00000000-0000-0000-0000-000000000001';
```

Run this via Railway's Postgres connect tab or psql.

### 2.7 Activate all workflows

In Railway n8n, make sure all 10 workflows are active (green toggle).

### 2.8 Test Railway n8n

```bash
# Replace URL and API_KEY with Railway values
N8N_URL=https://<your-n8n-railway-domain>
N8N_KEY=<railway-api-key>

curl -s -X POST "$N8N_URL/webhook/tool-get-my-profile" \
  -H "Content-Type: application/json" -d '{}' | python3 -m json.tool
```

Expected: Adarsh Gella's profile (session was set by seed_demo.sql).

---

## Part 3: Netlify — Frontend

### 3.1 Get a Netlify account

1. Go to [netlify.com](https://netlify.com) → Sign up with GitHub.

### 3.2 Push repo to GitHub (if not done)

```bash
git remote add origin https://github.com/gadarsh043/AskOps.git  # already done
git push origin master
```

### 3.3 Create Netlify site

**Option A: Netlify UI**
1. Netlify dashboard → **Add new site** → **Import an existing project**.
2. Connect GitHub → select the `AskOps` repo.
3. Build settings:
   - **Base directory**: (leave blank)
   - **Build command**: (leave blank — no build step)
   - **Publish directory**: `web`
4. Click **Deploy site**.
5. After deploy: **Site settings** → **Domain** → rename to `askops-demo` (or any available name).

**Option B: Netlify CLI**
```bash
npm install -g netlify-cli
netlify login
netlify deploy --dir=web --prod --site-name=askops-demo
```

### 3.4 Set the Railway n8n URL in Netlify

The frontend reads `window.ASKOPS_API` from `config.js`. For production, set it via Netlify environment injection:

1. Netlify site → **Site settings** → **Environment variables** → Add:
   - Key: `ASKOPS_API_URL`
   - Value: `https://<your-n8n-railway-domain>`

2. Update `web/config.js` to use this variable (already done):
   ```js
   window.ASKOPS_API = window.ASKOPS_API_URL || 'http://localhost:5678';
   ```

   > **Note:** Environment variables in Netlify are only injected at build time for frameworks with a build step. Since we're deploying static HTML, the simplest approach is to hardcode the Railway URL in `config.js` before deploying:
   ```js
   window.ASKOPS_API = 'https://<your-n8n-railway-domain>';
   ```

3. After updating `config.js`, push to GitHub or redeploy via Netlify CLI.

### 3.5 Verify frontend

Open `https://askops-demo.netlify.app/setup.html`:
1. Click **Fill everything with demo data**.
2. Click **Continue** → **Build Workspace** → **Go to Workspace**.
3. In workspace, type **"What is our PTO policy?"** → answer should appear.

---

## Part 4: Copilot Studio (optional — for the conversation layer)

> **Timing:** Copilot Studio free trial is 30 days. Start it close to your interview date.

### 4.1 Start trial

1. Go to [copilotstudio.microsoft.com](https://copilotstudio.microsoft.com).
2. Sign in with a Microsoft account (create one if needed).
3. Click **Start free trial**.
4. Create a new environment (default location is fine).

### 4.2 Create the AskOps agent

1. **New agent** → Name: `AskOps`
2. In **Instructions**, paste the full content of `copilot/instructions.md`.
3. Set language: English.
4. Disable all built-in topics except **Greeting** and **Escalate**.

### 4.3 Add tools (HTTP actions)

For each tool, create an HTTP action:

| Action name | Method | URL |
|-------------|--------|-----|
| search_kb | POST | `https://<railway-n8n>/webhook/tool-search-kb` |
| get_my_profile | POST | `https://<railway-n8n>/webhook/tool-get-my-profile` |
| get_pto_balance | POST | `https://<railway-n8n>/webhook/tool-get-pto-balance` |
| get_my_requests | POST | `https://<railway-n8n>/webhook/tool-get-my-requests` |
| request_pto | POST | `https://<railway-n8n>/webhook/tool-request-pto` |
| create_ticket | POST | `https://<railway-n8n>/webhook/tool-create-ticket` |
| get_ticket_status | POST | `https://<railway-n8n>/webhook/tool-get-ticket-status` |
| list_pending_pto | POST | `https://<railway-n8n>/webhook/tool-list-pending-pto` |
| decide_pto | POST | `https://<railway-n8n>/webhook/tool-decide-pto` |
| get_compensation | POST | `https://<railway-n8n>/webhook/tool-get-compensation` |
| escalate_to_human | POST | `https://<railway-n8n>/webhook/tool-escalate-to-human` |
| submit_feedback | POST | `https://<railway-n8n>/webhook/tool-submit-feedback` |

For tools with parameters (request_pto, create_ticket, etc.), map the input schema:
- `request_pto`: inputs `start_date` (string), `end_date` (string), `reason` (string)
- `create_ticket`: inputs `category`, `title`, `description`, `priority`
- `decide_pto`: inputs `code`, `decision`, `note`
- `get_compensation`: input `employee_name_or_code`
- `submit_feedback`: inputs `rating` (integer), `comment` (string, optional)
- `escalate_to_human`: input `summary`

### 4.4 Publish the web channel

1. Copilot Studio → **Channels** → **Custom website**.
2. Enable the channel (no authentication for demo).
3. Copy the **embed snippet** (iframe URL).
4. Paste the URL into the Copilot Studio tab in `workspace.html`:
   - Open workspace, click **Copilot Studio** tab
   - Paste URL into the input field and click **Load**
   - The iframe will load the Copilot Studio chat.

### 4.5 Test the Copilot flow

In the Copilot Studio chat:
1. Say **"Hi"** → greeting response.
2. Say **"What's my PTO balance?"** → calls `get_pto_balance`, shows days.
3. Say **"I want to request time off from Dec 24 to Dec 26"** → calls `request_pto`.
4. Say **"Show me my tickets"** → calls `get_ticket_status`.
5. As John Lee (HR), say **"Show all pending PTO"** → calls `list_pending_pto`.

---

## Part 5: Post-deploy verification

### 5.1 Full end-to-end test

1. Open `https://askops-demo.netlify.app`
2. Run through the demo flow:
   - Setup → Persona → Workspace
   - Chat: PTO balance, request PTO, check tickets
   - Receive approval email, approve via link
   - Switch to HR, view pending PTO, approve
   - View metrics dashboard

### 5.2 Update demo manager email

```sql
UPDATE workspaces 
SET demo_manager_email = 'your-interviewer@email.com'
WHERE id = '00000000-0000-0000-0000-000000000001';
```

This ensures PTO approval emails go to the right person during the interview.

### 5.3 Reset demo state

Before the interview:
```sql
-- Reset PTO balance
UPDATE employees SET pto_balance_days = 8 WHERE employee_code = 'EMP-042';
UPDATE employees SET pto_balance_days = 15 WHERE employee_code = 'EMP-007';

-- Clear test PTO requests (keep one for demo)
DELETE FROM pto_requests 
WHERE workspace_id = '00000000-0000-0000-0000-000000000001'
  AND created_at < now() - interval '1 hour';

-- Set session to Adarsh
SELECT set_active_session(
  '00000000-0000-0000-0000-000000000001'::uuid,
  (SELECT id FROM employees WHERE employee_code = 'EMP-042')
);
```

---

## Troubleshooting

### "Error in workflow" from n8n
Check the execution log: Railway n8n → Executions → find the failed run → click to see node-level errors.

### CORS errors in browser
n8n webhook nodes are configured with `allowedOrigins: *`. If you still see CORS errors, check that the workflow is active (green toggle) and the webhook path is correct.

### Email not arriving
1. Check Gmail app password is correct (re-generate if needed at myaccount.google.com → Security → App passwords).
2. Check spam folder.
3. Verify SMTP credential in n8n → test connection.
4. Check `demo_manager_email` in workspaces table is set correctly.

### PTO approval link "Invalid or Expired"
The token is single-use. If you already clicked Approve/Reject, the link is invalid. Submit a new PTO request to get a fresh link.

### Railway Postgres connection refused
Make sure the `askops_app` role exists (`db/roles.sql` must be run first). Check the password matches `.env`'s `APP_DB_PASSWORD`.

### search_kb returns no results
Run `python3 scripts/seed_sample_kb.py` to seed sample knowledge base chunks. Verify with:
```bash
psql_askops -c "SELECT COUNT(*) FROM chunks WHERE workspace_id='00000000-0000-0000-0000-000000000001';"
```
Expected: 10 chunks.

---

## Environment variable reference

| Variable | Used by | Value |
|----------|---------|-------|
| `POSTGRES_USER` | Docker Compose | `postgres` |
| `POSTGRES_PASSWORD` | Docker Compose | (see .env) |
| `APP_DB_PASSWORD` | n8n Postgres credential | (see .env) |
| `N8N_ENCRYPTION_KEY` | n8n | (see .env) — same value must be used on Railway |
| `WEBHOOK_URL` | n8n | Tunnel URL (local) or Railway n8n URL |
| `GROQ_API_KEY` | n8n Groq credential | (see .env) |
| `GEMINI_API_KEY` | n8n Gemini credential | (see .env) |
| `GMAIL_SMTP` | n8n SMTP credential | Gmail app password (see .env) |
| `GMAIL_USER` | n8n SMTP credential | `g.adarsh043@gmail.com` |
| `RAILWAY_TOKEN` | Railway CLI | (see .env) |

---

## Demo script (5 min)

1. **Intro (30s):** "AskOps is an AI-powered IT & HR service desk. I'll show you how it works for any company in under 5 minutes."

2. **Company setup (30s):** Open setup.html → "Fill with demo data" → Continue.

3. **Persona (20s):** Select Adarsh (employee) → enter your email → Build Workspace.

4. **Knowledge base demo (60s):** Ask "What's our remote work policy?" → Answer cites the sample policy. Ask again → cache hit (instant). Show the trace panel showing `search_kb: 142ms → cache hit: 0ms`.

5. **PTO request (60s):** Ask "I want to request Dec 24-26 off". System confirms balance check, creates request, sends approval email. Check inbox → click Review → Approve. Show the success page.

6. **Ticket (30s):** "My VPN keeps disconnecting" → Ticket created with IT team assignment.

7. **HR switch (60s):** Click John Lee → "Show all pending PTO" → list appears → "Approve PTO-0001" → approved. Try "Show Adarsh's salary" → shows $118,000.

8. **Dashboard (30s):** Open Dashboard tab → metrics: tool calls 60+, CSAT 4.8/5, tasks automated 23.

9. **Wrap (30s):** "Any company can be onboarded in under 2 minutes. The knowledge base, tools, and permissions all work without any code changes."
