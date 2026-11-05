# Ask Ops

An IT/HR service desk agent for any company: Copilot Studio for conversation,
n8n for tools and workflows, Postgres + pgvector for knowledge, data and logs.

Project context and rules: `CLAUDE.md` · Progress and decisions: `PROGRESS.md`

## Run locally

**Prerequisites:** Docker Desktop, Git, and `cloudflared` (`brew install cloudflared`) for tunnels.

This project starts **Postgres only**. Your existing n8n instance (running externally
on port 5678) connects to it. The n8n service in `docker-compose.yml` is kept for
Railway parity — start it with `docker compose --profile local-n8n up -d` only if
you need a fresh standalone n8n.

1. **Configure:**
   ```bash
   cp .env.example .env
   openssl rand -hex 32   # run once per secret, paste into .env
   chmod +x scripts/*.sh db/init/*.sh
   ```

2. **Start Postgres:**
   ```bash
   docker compose up -d
   docker compose logs postgres | grep "askops database ready"
   ```

3. **Load demo data:**
   ```bash
   ./scripts/seed-demo.sh
   ```

4. **Check it, as the same restricted role n8n uses:**
   ```bash
   ./scripts/psql.sh
   ```
   ```sql
   SELECT full_name, access_role FROM current_identity();   -- Adarsh Gella, employee
   SELECT * FROM compensation;                              -- permission denied (correct)
   ```

5. **Add credentials in n8n** at http://localhost:5678:
   - **Postgres (AskOps app data):** host `host.docker.internal`, port `5432`,
     database `askops`, user `askops_app`, password = `APP_DB_PASSWORD` from `.env`
   - **SMTP (Gmail):** host `smtp.gmail.com`, port `465`, SSL on,
     user = your Gmail address, password = Gmail App Password
     (Google Account → Security → 2-Step Verification → App passwords)
   - **Groq** and **Gemini:** API keys
   - **n8n API key:** Settings → n8n API → Create key → paste into `.env` as `N8N_API_KEY`

## Tunnel (for Copilot Studio and approval emails)

Copilot Studio and email recipients can't reach `localhost`.
```bash
./scripts/tunnel.sh                    # prints https://<random>.trycloudflare.com
# put that URL in WEBHOOK_URL in .env
```

## Moving workflows between local and Railway

```bash
./scripts/export-workflows.sh   # n8n → n8n/workflows/*.json (commit these)
./scripts/import-workflows.sh   # n8n/workflows/*.json → n8n
```
Credentials don't travel with workflows. Re-create them once on Railway, and use
the same `N8N_ENCRYPTION_KEY` there.

## Reset everything

```bash
docker compose down -v && docker compose up -d && ./scripts/seed-demo.sh
```
