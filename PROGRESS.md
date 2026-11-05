# Ask Ops: progress tracker

Status key: [ ] not started · [~] in progress · [x] done

## Phase 0: Foundation
- [x] Repo structure, CLAUDE.md, PROGRESS.md
- [x] Postgres schema with pgvector, access-controlled functions, metrics view (tested 2026-11-04)
- [x] Demo seed with personas (Adarsh Gella, John Lee)
- [x] Docker Compose mirroring Railway (Postgres + pgvector, n8n)
- [ ] `docker compose up -d` works on my machine; seed loads
- [x] Git repo pushed to GitHub (gadarsh043/AskOps, branch master) (2026-11-05)
- [x] n8n credentials on Railway: Postgres (askops_app), Groq (httpHeaderAuth), Gemini (httpQueryAuth), Gmail SMTP (2026-11-05)

## Phase 1: Tools (n8n MCP server), tested with curl before Copilot
- [ ] MCP Server Trigger workflow exposing tools
- [x] Shared sub-workflow: `current_identity()` + `tool_calls` logging + error mapping (embedded in every branch of unified workflow)
- [x] get_my_profile, get_pto_balance, get_my_requests
- [x] request_pto (balance + weekday + overlap check; pgcrypto token hash stored; email in Phase 2)
- [x] list_pending_pto, decide_pto (HR only; denial logged as `denied` via Postgres DO block)
- [x] create_ticket, get_ticket_status
- [x] get_compensation (employee gets `denied`; HR gets salary)
- [x] escalate_to_human, submit_feedback
- [x] All 11 tools consolidated into single `mcp.ask-ops` workflow (141 nodes, qhmoB9pZdLav12FB); 12 originals deleted; all verified end-to-end

## Phase 2: Email approval loop
- [x] Gmail App Password + SMTP credential (n8n credential ID: 8vmLF66qqfuLZu5m)
- [x] Approval email template (company name, request details, Review button) — best-effort: PTO request succeeds even if email fails
- [x] `api.pto-review` GET → HTML confirmation page (`peek_pto_by_token`); invalid/expired token → HTML error page
- [x] `api.pto-decide` POST → `decide_pto_by_token` → HTML result page (approved/rejected badge); single-use token (hash nulled after use)
- [x] Full flow tested locally: request_pto → email sent to g.adarsh043@gmail.com → /pto-review → Approve → DB status=approved → stale link returns error HTML
- [ ] Tested through the tunnel on a phone (tunnel URL must be set in workspaces.webhook_url)

## Phase 3: Knowledge ingestion
- [x] search_kb: Gemini embed → lookup_cache (semantic cache) → match_chunks → openai/gpt-oss-120b via Groq → cited answer; cache hit on 2nd query (tested 2026-11-05)
- [x] Sample policy generator: 4 sample docs × 2-3 chunks = 10 chunks seeded via scripts/seed_sample_kb.py; source_type='sample' (tested 2026-11-05)
- [x] Website crawl: ingest.website workflow — Jina Reader → Extract Chunks (Code) → Gemini embed → Store Chunk (Postgres) → Done (created 2026-11-05)
- [ ] Document upload ingestion (PDF/DOCX/TXT)
- [ ] Employee CSV upload with Groq column mapping + confirmation
- [ ] build_events emitted for every step
- [x] cron.cleanup calls delete_expired_workspaces() hourly (cron.cleanup workflow created 2026-11-05)

## Phase 4: Copilot Studio agent
- [ ] Start free trial (timed so 30 days cover the interview)
- [ ] Verify MCP connection to n8n (fallback: HTTP request node / custom connector)
- [x] Agent instructions in `copilot/instructions.md` (created 2026-11-05)
- [ ] Topics: greeting, PTO, ticket, escalation, end-of-conversation feedback
- [ ] Web channel published (no auth for demo)

## Phase 5: Router, cache, guardrails
- [x] Groq router: `tool.router` workflow — POST /webhook/tool-router → faq/action/sensitive/off_topic/smalltalk (2026-11-05)
- [x] Semantic cache writes for knowledge answers only (already in search_kb branch)
- [x] PII redaction before logging turns: `tool.log-turn` workflow with regex redaction of emails, phones, amounts (2026-11-05)
- [ ] Prompt-injection test: instructions planted in a scraped page are ignored

## Phase 6: Frontend (Netlify)
- [x] Page 1: company setup (URL + "Fill with demo data") — web/setup.html (2026-11-05)
- [x] Page 2: persona + manager email — web/persona.html (2026-11-05)
- [x] Build animation from build_events — web/build.html with polling (2026-11-05)
- [x] Chat page: Demo Chat (intent detection → tool calls) + Copilot Studio iframe tab + trace panel + persona switch — web/workspace.html (2026-11-05)
- [x] Metrics dashboard (workspace_metrics) — web/dashboard.html (2026-11-05)
- [x] netlify.toml with publish dir, redirects, security headers (2026-11-05)
- [x] 7 API workflows for frontend: api.build-status, api.set-persona, api.metrics, api.tool-trace, api.setup-workspace, tool.router, tool.log-turn (2026-11-05)

## Phase 7: Deploy
- [x] Railway: Postgres (native, pgvector built-in) + n8n 1.97.1 (2026-11-05)
- [x] roles.sql + schema.sql + seed_demo.sql applied on Railway; askops_app grants applied (2026-11-05)
- [x] 10 workflows imported and activated on Railway n8n (mcp.ask-ops, ingest.website, cron.cleanup, 7 api/tool workflows) (2026-11-05)
- [x] Credentials created on Railway: Postgres, Groq, Gemini, Gmail SMTP (2026-11-05)
- [x] Sample KB seeded on Railway (10 chunks across 4 docs) (2026-11-05)
- [x] Netlify site deployed at https://ask-ops.netlify.app pointing at Railway n8n (2026-11-05)
- [x] CORS confirmed: Railway n8n returns access-control-allow-origin: https://ask-ops.netlify.app (2026-11-05)
- [x] End-to-end smoke test passed: profile ✓, balance ✓, requests ✓, compensation DENIED ✓, search_kb ✓, metrics ✓ (2026-11-05)
- [x] Live demo confirmed: https://ask-ops.netlify.app chat answered PTO policy question from Railway KB (2026-11-05)
- [ ] Railway usage limit set (stay inside $5 credit)
- [ ] Update workspaces.demo_manager_email to interviewer's real email before interview
- [ ] Copilot Studio tools pointed at Railway n8n (optional — Demo Chat works without it)

## Phase 8: Demo polish
- [x] Test sheet: 34 test cases covering all tools, email flow, search_kb, ingestion, dashboard — test.md (2026-11-05)
- [x] Deploy guide: Railway + Netlify + Copilot Studio steps — deploy.md (2026-11-05)
- [x] Demo script: 5-min walkthrough in deploy.md (2026-11-05)
- [ ] Architecture diagram
- [x] Dry run end to end on deployed version at https://ask-ops.netlify.app (2026-11-05)

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
| 2026-11-05 | HR access checks in Postgres DO blocks, not Code nodes | n8n's sandbox strips everything before the first `:` from thrown Error messages, so `CODE:` prefixes in Code node throws are lost; DO blocks preserve the full message in `item.json.message` |
| 2026-11-05 | pgcrypto enabled at DB init for PTO token generation | n8n Code nodes block `require('crypto')`; `gen_random_bytes(32)` in a SQL CTE is the only sandboxed option |
| 2026-11-05 | Use `json_agg` in SQL for list queries | n8n skips Code nodes with 0 input items, breaking the pipeline; aggregating in SQL guarantees exactly 1 output row |
| 2026-11-05 | Consolidate all tools into one `mcp.ask-ops` workflow | Easier to demo on one canvas; `scripts/build_mcp_workflow.py` regenerates it; webhook paths unchanged so curl tests still work |
| 2026-11-05 | SQL templates referencing original user input must use `$('Normalize Input N')` not `$json` | After Get Identity runs, `$json` = identity row (no user fields); node references access any prior node's output |
| 2026-11-05 | `webhook_url` stored in `workspaces` table, not an env var | n8n Code node sandbox blocks env var reads; each workspace's approval email links need the right base URL for tunnel vs local |
| 2026-11-05 | HTML webhook branches use `respondToWebhook` with `responseMode: 'responseNode'`; `respondWith: 'text'` → param is `responseBody` not `body` | n8n source confirms `responseBody` is the parameter name for text/HTML responses |
| 2026-11-05 | `peek_pto_by_token` and `decide_pto_by_token` must use `decode(p_token, 'hex')` not `convert_to(p_token, 'UTF8')` | Token in email link is hex-encoded raw bytes; hashing the hex string chars produces a different hash than hashing the original bytes |
| 2026-11-05 | `peek_pto_by_token` changed from SQL to plpgsql to raise `INVALID_LINK` on 0 rows | n8n Postgres node with 0-row result skips all downstream nodes, so `respondToWebhook` is never reached; raising an exception routes to the error output path |
| 2026-11-05 | search_kb branch built manually (not via build_branch) with IF nodes for cache hit and no-chunks routing | Standard build_branch() assumes linear flow; IF nodes need manual connection mapping; added Prep Embed 14 node to merge query + identity before Gemini HTTP call |
| 2026-11-05 | psql() in seed scripts must strip "INSERT 0 1" suffix from RETURNING output | n8n `-t -A` flags emit UUID + "INSERT 0 1" on the same stdout stream; using the full value as doc_id causes UUID cast failure on chunk inserts (silently, with returncode=0) |
| 2026-11-05 | Groq model changed from `llama-3.3-70b-versatile` to `openai/gpt-oss-120b` | llama-3.3-70b-versatile not available on this Groq API key; available models are openai/gpt-oss-120b, qwen/qwen3.x-27b, allam-2-7b, whisper |

## Risks and open questions

- Copilot Studio trial is 30 days: start it late enough to cover the interview; pay-as-you-go is the fallback.
- Copilot Studio MCP support: confirm it connects to n8n's MCP Server Trigger; fallback is HTTP request nodes.
- Free-tier limits (Groq, Gemini, Jina): confirm current limits before the demo.
- Gemini embedding model name and dimension option: `gemini-embedding-001` with outputDimensionality 768. ✓
- Tunnel URL changes on every run: WEBHOOK_URL must be updated for email links during local testing.
- Big sites (e.g. amazon.com) may block scraping: fallback to sample-only must look intentional.
- Railway $5 credit: n8n + Postgres running 24/7 should fit; watch usage weekly.
- tool.router returns parse-error fallback (classification=faq, confidence=0.5) when Groq response can't be parsed as JSON — the classification is correct but confidence is wrong. Acceptable for demo; fix by stripping markdown code fences before JSON.parse if needed.
