# Ask Ops: progress tracker

Status key: [ ] not started · [~] in progress · [x] done

## Phase 0: Foundation
- [x] Repo structure, CLAUDE.md, PROGRESS.md
- [x] Postgres schema with pgvector, access-controlled functions, metrics view (tested 2026-11-04)
- [x] Demo seed with personas (Adarsh Gella, John Lee)
- [x] Docker Compose mirroring Railway (Postgres + pgvector, n8n)
- [ ] `docker compose up -d` works on my machine; seed loads
- [ ] Git repo created and pushed to GitHub
- [ ] n8n credentials added: Postgres (askops_app), Groq, Gemini, Gmail SMTP

## Phase 1: Tools (n8n MCP server), tested with curl before Copilot
- [ ] MCP Server Trigger workflow exposing tools
- [ ] Shared sub-workflow: `current_identity()` + `tool_calls` logging + error mapping
- [ ] get_my_profile, get_pto_balance, get_my_requests
- [ ] request_pto (balance + policy check, token, email)
- [ ] list_pending_pto, decide_pto (HR only)
- [ ] create_ticket, get_ticket_status
- [ ] get_compensation (verify employee gets `denied`)
- [ ] escalate_to_human, submit_feedback

## Phase 2: Email approval loop
- [ ] Gmail App Password + SMTP credential
- [ ] Approval email template (company name, request details, Review button)
- [ ] `api.pto-review` GET → confirmation page (peek_pto_by_token)
- [ ] `api.pto-decide` POST → decide_pto_by_token → result page
- [ ] Tested through the tunnel on a phone

## Phase 3: Knowledge ingestion
- [ ] search_kb: Gemini embedding → lookup_cache → match_chunks → cited answer
- [ ] Sample policy generator (company-branded, tagged SAMPLE)
- [ ] Website crawl: homepage + sitemap, keyword scoring, top ~15 pages via Jina
- [ ] Document upload ingestion (PDF/DOCX/TXT)
- [ ] Employee CSV upload with Groq column mapping + confirmation
- [ ] build_events emitted for every step
- [ ] cron.cleanup calls delete_expired_workspaces() hourly

## Phase 4: Copilot Studio agent
- [ ] Start free trial (timed so 30 days cover the interview)
- [ ] Verify MCP connection to n8n (fallback: HTTP request node / custom connector)
- [ ] Agent instructions in `copilot/instructions.md`
- [ ] Topics: greeting, PTO, ticket, escalation, end-of-conversation feedback
- [ ] Web channel published (no auth for demo)

## Phase 5: Router, cache, guardrails
- [ ] Groq router: faq / action / sensitive / off_topic / smalltalk
- [ ] Semantic cache writes for knowledge answers only
- [ ] PII redaction before logging turns
- [ ] Prompt-injection test: instructions planted in a scraped page are ignored

## Phase 6: Frontend (Netlify)
- [ ] Page 1: company setup (upload or sample per section)
- [ ] Page 2: persona + manager email
- [ ] Build animation from build_events
- [ ] Chat page: Copilot web chat + Behind-the-scenes trace panel + persona switch
- [ ] Metrics dashboard (workspace_metrics)

## Phase 7: Deploy
- [ ] Railway: Postgres (pgvector image) + n8n, same N8N_ENCRYPTION_KEY
- [ ] Run roles.sql + schema.sql on Railway; import workflows; re-add credentials
- [ ] Railway usage limit set (stay inside $5)
- [ ] Netlify deploy pointing at Railway n8n URL
- [ ] Copilot Studio tools pointed at Railway n8n

## Phase 8: Demo polish
- [ ] Test sheet: 30+ scenarios incl. edge cases and access denials
- [ ] Architecture diagram + one-page user guide
- [ ] Demo script (5–7 min) and backup screen recording
- [ ] Dry run end to end on the deployed version

## Decision log

| Date | Decision | Why |
|---|---|---|
| 2026-11-04 | Use case: Ask Ops, an IT/HR service desk agent | Covers nearly every JD bullet; universal pain point |
| 2026-11-04 | Copilot Studio for conversation; own RAG in n8n + pgvector | Copilot knowledge sources can't be swapped at runtime per company |
| 2026-11-04 | Railway Postgres + pgvector instead of Supabase | Supabase free projects used up; one DB serves n8n + app + logs |
| 2026-11-04 | Own logging + Netlify dashboard, no self-hosted Langfuse | Langfuse self-hosting is too heavy for the $5 Railway plan |
| 2026-11-04 | Demo identity via personas in `active_session` | No login in demo; production would use Entra ID |
| 2026-11-04 | Salaries in a separate table, write-only for the app role | Access enforced by the database, not the prompt |
| 2026-11-04 | Gmail SMTP with App Password for approval emails | Free; real email to a real inbox |
| 2026-11-04 | Approval via GET confirm page + POST decision | Email link scanners prefetch GET links |
| 2026-11-04 | Gemini embeddings, 768 dims | Free tier; Supabase built-in embeddings no longer available |
| 2026-11-04 | Build locally with Docker Compose, then deploy | Same images as Railway; workflows move as JSON |
| 2026-11-04 | Claude Code as coding agent | Reads CLAUDE.md, works with Docker/psql from terminal |

## Risks and open questions

- Copilot Studio trial is 30 days: start it late enough to cover the interview; pay-as-you-go is the fallback.
- Copilot Studio MCP support: confirm it connects to n8n's MCP Server Trigger; fallback is HTTP request nodes.
- Free-tier limits (Groq, Gemini, Jina): confirm current limits before the demo.
- Gemini embedding model name and dimension option: confirm (`gemini-embedding-001` with output dimension 768).
- Tunnel URL changes on every run: WEBHOOK_URL must be updated for email links during local testing.
- Big sites (e.g. amazon.com) may block scraping: fallback to sample-only must look intentional.
- Railway $5 credit: n8n + Postgres running 24/7 should fit; watch usage weekly.
