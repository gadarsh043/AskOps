# AskOps: Complete Explanation

> Everything about how this project works — from first principles. If you've never touched AI, databases, or workflow automation before, this document will walk you through it all.

---

## Table of Contents

1. [What is AskOps?](#1-what-is-askops)
2. [The Big Picture — How Everything Connects](#2-the-big-picture)
3. [Tech Stack — Every Tool Explained](#3-tech-stack)
4. [The Database — Postgres + pgvector](#4-the-database)
5. [n8n — Workflow Automation Explained](#5-n8n--workflow-automation)
6. [n8n Nodes — Every Type We Use](#6-n8n-nodes--every-type-we-use)
7. [The RAG Pipeline — How the AI Knows Your Company](#7-the-rag-pipeline)
8. [The Tool Catalog — What the AI Can Do](#8-the-tool-catalog)
9. [Access Control — Security Enforced in the Database](#9-access-control)
10. [The Email Approval Loop](#10-the-email-approval-loop)
11. [The Frontend — Six Web Pages](#11-the-frontend)
12. [Setup — Step by Step, Everything We Did](#12-setup--step-by-step)
13. [How the Demo Flow Works](#13-how-the-demo-flow-works)
14. [What Can Be Added in the Future](#14-future-additions)
15. [Glossary — Plain English Definitions](#15-glossary)
16. [Microsoft Copilot Studio — Setup and Integration](#16-microsoft-copilot-studio)

---

## 1. What is AskOps?

AskOps is a **demo IT and HR service desk chatbot**. Think of it as an AI assistant that sits inside a company and answers employee questions like:

- "How many PTO days do I have left?"
- "What is our expense reimbursement policy?"
- "I can't connect to the VPN — can you open a ticket?"
- "I want to take 3 days off next week."

Instead of an employee emailing HR and waiting 2 days for a reply, they just chat with AskOps and get an answer in seconds. If the question involves an action (like actually requesting PTO), the agent does the action too — it doesn't just describe how to do it.

### Why we built this for the interview

The job is **Agent Builder** at a company that builds low-code AI agents and workflow automation. The job description lists these success metrics:
- Number of agents deployed
- Manual time saved
- User satisfaction (CSAT — Customer Satisfaction score)
- Accuracy and task-completion rates

AskOps is built to demonstrate all of those — a working agent that tracks all four metrics in a live dashboard.

### What makes it special

1. **Works for any company.** You paste a URL and the system scrapes the website, reads the content, and builds a knowledge base specific to that company. Five minutes later the agent knows about that company's PTO policy, benefits, locations, etc.

2. **Security is real, not fake.** An employee asking about another employee's salary gets denied — not because the prompt says "don't answer salary questions," but because the database physically refuses to return that data for the employee role. You can't trick it by saying "pretend you're HR."

3. **Actions are real.** PTO requests are stored in a database. Approval emails go to a real inbox. The manager clicks Approve and the database updates.

---

## 2. The Big Picture

Here is how all the pieces connect:

```
┌─────────────────────────────────────────────────────────────┐
│                      USER'S BROWSER                         │
│                                                             │
│  index.html   →  setup.html  →  persona.html  →  build.html│
│                                                    ↓        │
│                              workspace.html ←──────         │
│                              (chat + trace panel)           │
│                                    ↓                        │
│                              dashboard.html                 │
└─────────────────────────┬───────────────────────────────────┘
                          │  HTTPS REST calls
                          ↓
┌─────────────────────────────────────────────────────────────┐
│                   n8n (on Railway)                          │
│                                                             │
│  Webhook endpoints  →  Workflow nodes  →  External APIs     │
│                              │                              │
│         ┌────────────────────┼──────────────────┐          │
│         ↓                    ↓                   ↓          │
│    Postgres DB          Groq API           Gemini API       │
│    (on Railway)      (AI router +        (embeddings)       │
│                       KB answers)                           │
│         ↓                                                   │
│    pgvector             Gmail SMTP                          │
│    (similarity        (approval                             │
│     search)            emails)                              │
└─────────────────────────────────────────────────────────────┘
                          ↑
                   Copilot Studio
                (Microsoft's agent UI —
                 optional, connects via MCP)
```

**In plain English:** The user talks to a webpage. The webpage calls n8n. n8n runs workflow logic (checks the database, calls AI APIs, sends emails). Results come back to the webpage.

---

## 3. Tech Stack

### Netlify — the website host

**What it is:** Netlify is a service that hosts static websites (HTML, CSS, JavaScript files). You push code to GitHub and Netlify automatically publishes it. No server to manage.

**What we use it for:** Hosting the 6 HTML pages (index, setup, persona, build, workspace, dashboard). These pages run entirely in the browser — no server-side code.

**URL:** https://ask-ops.netlify.app

**Why not just use GitHub Pages?** Netlify gives us redirect rules (so `/api/*` doesn't break), security headers, and instant deploys on every git push.

---

### Railway — the backend host

**What it is:** Railway is a cloud platform that runs containers (Docker images). You connect a GitHub repo or use their templates and they run your services on real servers.

**What we use it for:** Running two services:
1. **Postgres 16 + pgvector** — the database
2. **n8n 1.97.1** — the workflow automation engine

**URL:** https://n8n-production-20f8.up.railway.app

**Cost:** Railway gives $5 of free credit per month. Our two services (Postgres + n8n) stay within that.

**Why Railway instead of running locally?** A local server only works when your laptop is open. Railway runs 24/7 so the demo works from any device.

---

### n8n — the workflow engine

**What it is:** n8n (pronounced "n-eight-n") is an open-source workflow automation tool. Think of it like Zapier or Make (Integromat), but self-hosted and much more powerful because you can write actual JavaScript code inside it.

**What we use it for:** n8n is the brain of the backend. Every time the frontend wants to do something (ask a question, check PTO balance, create a ticket), it calls an n8n webhook. n8n runs a workflow that hits the database, calls AI APIs, and returns results.

**Why not just write a backend in Python/Node?** n8n gives us a visual canvas to build on. Every workflow is a JSON file that can be exported, imported, and versioned in git. For a demo of an "Agent Builder" role, using a visual workflow tool is itself part of the demo — it shows the low-code approach.

---

### Postgres 16 — the database

**What it is:** PostgreSQL (Postgres) is one of the world's most popular open-source relational databases. Data is stored in tables (like spreadsheets) with rows and columns. You query it with SQL.

**What we use it for:** Storing everything — employees, PTO requests, support tickets, knowledge base chunks, conversation logs, metrics.

**Why Postgres specifically?** Because it has an extension called **pgvector** that lets us store and search AI vector embeddings directly in the database. We don't need a separate vector database service.

---

### pgvector — vector similarity search

**What it is:** pgvector is a Postgres extension that adds a new column type called `vector`. A vector is a list of numbers (like `[0.12, -0.34, 0.89, ...]`) that represents the "meaning" of a piece of text in a way that math can work with.

**What we use it for:** When a user asks a question, we convert the question into a vector. We then search the database for chunks of text whose vectors are closest (most similar) to the question's vector. This is how the AI finds relevant information from the company's knowledge base.

**What is HNSW?** HNSW (Hierarchical Navigable Small World) is an index type for vector search. Without an index, searching 10,000 vectors would compare every single one. HNSW builds a graph structure that finds the closest vectors in milliseconds.

---

### Docker and Docker Compose — local development

**What Docker is:** Docker runs applications inside "containers." A container is like a lightweight virtual machine — it packages the app and all its dependencies so it runs the same way on any computer.

**What Docker Compose is:** A tool that runs multiple Docker containers together. Our `docker-compose.yml` file defines two containers: `postgres` (the database) and `n8n` (the workflow engine). One command (`docker compose up -d`) starts both.

**Why use it locally?** The Docker images we use locally are the same ones Railway uses in production. If it works locally, it works on Railway.

---

### Groq — fast AI inference

**What it is:** Groq is a company that runs large language models (LLMs) extremely fast using special hardware. They have a free API tier.

**What we use it for:** Three things:
1. **Router:** Classifying every user message into one of 5 categories (faq, action, sensitive, off_topic, smalltalk) so the system knows how to handle it.
2. **Knowledge base answers:** Generating the final answer from retrieved document chunks using `openai/gpt-oss-120b`.
3. **Company name extraction:** When we scrape a website, Groq extracts the company name, industry, and locations from the text.
4. **Sample policy generation:** Creating realistic-sounding company policy documents (PTO, IT security, expenses, etc.) branded to the specific company.

**Model we use:** `openai/gpt-oss-120b` (the original target was `llama-3.3-70b-versatile` but it wasn't available on our API key, so we switched).

---

### Gemini — embeddings

**What it is:** Google's AI platform. We only use one specific feature: the text embedding API.

**What embeddings are:** When you give a sentence to an embedding model, it returns a list of 768 numbers. Similar sentences produce similar number lists. The sentence "I want to take Thursday off" and "I'd like to request PTO" will produce vectors that are close together in 768-dimensional space.

**What we use it for:** Converting every document chunk and every user question into a 768-dimensional vector, so we can do similarity search in pgvector.

**Model:** `gemini-embedding-001` with `outputDimensionality: 768`.

**Why 768 dimensions?** It's a balance — more dimensions = more precise but slower and uses more storage. 768 is the native output of the model.

---

### Jina Reader — web scraping

**What it is:** A free API that takes a URL and returns the page content as clean Markdown text. You call `https://r.jina.ai/https://your-url.com` and get back readable text instead of raw HTML.

**What we use it for:** Scraping the company website and sitemap in the knowledge ingestion pipeline. Jina handles JavaScript-rendered pages and strips ads, navigation, and other noise.

**Why not use curl or a custom scraper?** Jina is free, requires zero setup, and handles most websites cleanly. Building a custom scraper for a demo would take days.

---

### Gmail SMTP — email

**What it is:** Gmail's outgoing email server. We authenticate with an **App Password** (a 16-character password specific to this app, not your regular Gmail password).

**What we use it for:** Sending the PTO approval email to the manager. When an employee submits a PTO request, the manager gets an email with an "Approve" and "Reject" button.

**Why SMTP instead of a service like SendGrid?** SMTP with a Gmail app password is completely free and delivers to real inboxes. For a demo, it's perfect.

---

### Copilot Studio — the AI agent (optional)

**What it is:** Microsoft's low-code AI agent builder. You define the agent's personality, instructions, and tools, and it generates a web chat widget you can embed on a website.

**What we use it for:** As an alternative to the custom "Demo Chat" we built. The workspace has two tabs: "Demo Chat" (our own implementation) and "Copilot Studio" (the embedded iframe from Microsoft's platform).

**Why optional?** Copilot Studio is on a 30-day free trial. The demo works without it using the Demo Chat tab. For the interview, the Copilot tab shows the professional agent UI.

---

## 4. The Database

### Why Postgres

Postgres is the best free database for projects that need:
- Relational data (employees have managers, PTO requests belong to employees, etc.)
- Strong data integrity (constraints that prevent invalid data, like `CHECK (pto_balance_days >= 0)`)
- Extensions (we need pgvector for AI search)
- Role-based security (the database can literally refuse to show certain data to certain users)

### What is a "volume" in Docker/Railway?

When Docker runs a Postgres container, the data lives inside the container. If the container restarts, everything is gone — that's a problem for a database.

A **volume** is a persistent storage location that lives outside the container. The container mounts the volume at a specific path (`/var/lib/postgresql/data`). When the container restarts, it re-mounts the same volume and all data is still there.

In `docker-compose.yml`:
```yaml
volumes:
  - pgdata:/var/lib/postgresql/data   # named volume: persists across restarts
```

On Railway, volumes work the same way — Railway provides persistent disk storage and mounts it into the Postgres container.

### Database: "askops" vs "n8n"

We have **two separate databases** on the same Postgres server:

| Database | Purpose |
|---|---|
| `n8n` | n8n's internal storage (its own workflows, credentials, executions) |
| `askops` | All app data (employees, PTO, tickets, knowledge base, logs) |

They're completely separate. n8n never touches `askops` directly — it uses SQL queries via its Postgres credential.

### The database role: `askops_app`

We created a special database user called `askops_app`. It has limited permissions:
- Can read and write most tables
- **Cannot read the `compensation` table at all** (salaries)
- **Cannot call most functions directly** (must go through the SECURITY DEFINER functions)

This is the user n8n connects as. Even if someone hacked n8n, they couldn't read salary data because the database user literally doesn't have SELECT permission on that table.

### Tables Overview

#### `workspaces`
One row per company demo session. Stores the company name, website URL, manager email, and when the workspace expires (24 hours after creation).

```
id (uuid)  |  company_name  |  website_url  |  status  |  demo_manager_email  |  expires_at
```

#### `employees`
One row per person. Stores name, title, department, manager reference, PTO balance, and which role they have (`employee` or `hr`).

```
id  |  workspace_id  |  employee_code  |  full_name  |  access_role  |  pto_balance_days
```

#### `compensation`
Salaries. The `askops_app` role cannot SELECT from this table. Only the `get_compensation()` SQL function (which runs with higher privileges) can read it, and it checks the HR role first.

#### `active_session`
One row (a "singleton" table). Records who is currently using the demo.
```
singleton  |  workspace_id  |  employee_id  |  updated_at
```
This is how the AI knows who you are without a login system. Every tool call starts by reading this table.

#### `documents` and `chunks`
The knowledge base. A document is one source (a web page, an uploaded file, or a generated sample policy). A chunk is a piece of a document (~800 tokens). Each chunk has an `embedding` column (768-dimensional vector).

#### `pto_requests`
One row per PTO request. Has codes like `PTO-1001`. Stores the status (`pending`, `approved`, `rejected`), token hash for email approval, and who decided it.

#### `tickets`
Support tickets. Codes like `TCK-2001`. Categories: `it`, `hr`, `facilities`, `other`. Priorities: `low`, `normal`, `high`, `urgent`.

#### `semantic_cache`
Stores previous knowledge base answers. When a new question is semantically similar (cosine distance < 0.15) to a cached question, we return the cached answer without calling Groq again. Cache key = workspace + role + question meaning.

#### `conversations` and `turns`
Every chat session and every message. PII (emails, phone numbers, amounts) is redacted before storing in `turns.content_redacted`.

#### `tool_calls`
Every tool call the agent makes is logged here with status (`success`, `error`, `denied`) and latency. This feeds the metrics dashboard.

#### `workspace_metrics` (view)
Not a table — a SQL VIEW that aggregates data from `tool_calls`, `conversations`, `turns`, etc. The dashboard page reads from this single view.

### SQL Functions (SECURITY DEFINER)

Some operations are sensitive enough that we don't expose them as plain SQL — we wrap them in Postgres functions that run with higher privileges than the calling user.

| Function | What it does |
|---|---|
| `current_identity(p_workspace_id)` | Returns the active employee's id, name, role, and workspace from `active_session`. Every tool calls this first. |
| `set_active_session(workspace_id, employee_id)` | Sets the persona for the demo. Called by the persona page. |
| `get_compensation(name_or_code)` | Returns salary. Checks `access_role = 'hr'` first. If called by an employee, raises `ACCESS_DENIED`. |
| `match_chunks(workspace_id, query_embedding, k, threshold)` | Runs the vector similarity search. Returns top-k chunks whose cosine distance to the query is below the threshold. |
| `delete_expired_workspaces()` | Called by the hourly cron job. Deletes workspaces past their `expires_at`. Cascades to all related data. |
| `peek_pto_by_token(token)` | Looks up a PTO request by its email token. Called when the manager opens the approval link. |
| `decide_pto_by_token(token, decision, note)` | Approves or rejects a PTO request via the email link. Nulls the token hash after use (single-use). |

---

## 5. n8n — Workflow Automation

### What a workflow is

A workflow is a visual flowchart made of **nodes** connected by **arrows**. Each node does one thing. Data flows from left to right through the arrows.

```
[Trigger] → [Node A] → [Node B] → [Node C] → [Response]
```

When the trigger fires (e.g., a webhook call arrives), n8n runs all the nodes in order and sends the final result back.

### How data moves between nodes

Each node receives an array of **items** (JSON objects). It processes them and passes new items to the next node. Every node can reference the output of any previous node using `$('Node Name').first().json.fieldName`.

For example, after a Postgres query node called "Get Identity", the next node can read:
```js
const role = $('Get Identity').first().json.access_role;  // "employee" or "hr"
```

### Our workflows

We have 10 workflows on Railway n8n:

| Workflow | Purpose |
|---|---|
| `mcp.ask-ops` | The main tool server — 11 tools, 141 nodes, runs everything |
| `ingest.website` | Scrapes a URL and builds the knowledge base |
| `cron.cleanup` | Runs hourly, deletes expired workspaces |
| `api.setup-workspace` | Called by the setup page — creates a workspace, starts ingestion |
| `api.set-persona` | Called by the persona page — sets the active session |
| `api.build-status` | Called by the build page — returns current build events |
| `api.metrics` | Called by the dashboard — returns workspace_metrics data |
| `api.tool-trace` | Called by the workspace page — returns recent tool_calls |
| `tool.router` | Classifies a user message into faq/action/sensitive/off_topic/smalltalk |
| `tool.log-turn` | Logs a conversation turn with PII redaction |

### The main workflow: `mcp.ask-ops` (141 nodes)

This one workflow contains all 11 tools. Each tool is a "branch" — a horizontal chain of nodes. The branches are stacked vertically on the canvas.

```
MCP Server Trigger (outputs 0–10)
  │
  ├─ Output 0 → [Branch 1: get_my_profile]
  ├─ Output 1 → [Branch 2: get_pto_balance]
  ├─ Output 2 → [Branch 3: get_my_requests]
  ├─ Output 3 → [Branch 4: get_compensation]
  ├─ Output 4 → [Branch 5: create_ticket]
  ├─ Output 5 → [Branch 6: get_ticket_status]
  ├─ Output 6 → [Branch 7: request_pto]
  ├─ Output 7 → [Branch 8: list_pending_pto]
  ├─ Output 8 → [Branch 9: decide_pto]
  ├─ Output 9 → [Branch 10: escalate_to_human]
  └─ Output 10 → [Branch 11: submit_feedback]
```

Each branch has the same structure:

```
Webhook N ──┐
            ├→ Normalize Input N → Get Identity N → [Tool Logic] → Format Output N
MCP Out N ──┘                                   ↘ Handle Error N → Return Error N
                                        → Prepare Log N → Log Tool Call N → Return Output N
```

**Why both a Webhook and an MCP trigger?** The MCP trigger connects to Copilot Studio. The Webhook lets us test each tool with `curl` commands during development.

---

## 6. n8n Nodes — Every Type We Use

### Webhook (Trigger)
**What it does:** Listens at a URL path. When something calls that URL with an HTTP POST request, it fires and passes the request body as the first item.

**Example:** `POST https://n8n-production-20f8.up.railway.app/webhook/tool-get-pto-balance`

**We use it for:** One webhook per tool branch, so we can test tools with curl. Also used for all the API endpoints the frontend calls.

---

### MCP Server Trigger (Trigger)
**What it does:** Exposes tools over the Model Context Protocol (MCP). An AI agent (like Copilot Studio) connects to this trigger and can call any of the 11 tools by name.

**We use it for:** The main entry point for Copilot Studio to call our tools.

**MCP = Model Context Protocol.** A standard protocol (created by Anthropic) that lets AI agents discover and call external tools in a structured way. It's like a USB standard — the agent doesn't need to know the tool implementation details, just the name and schema.

---

### Code (JavaScript)
**What it does:** Runs JavaScript code on the current items. Can transform data, make calculations, or construct new objects.

**We use it for:** Almost all the "brain" logic:
- Normalizing inputs from either the Webhook or MCP trigger into a consistent format
- Formatting the response (turning a database row into a friendly message)
- Building SQL parameter objects
- Computing business logic (e.g., counting weekdays between two dates for PTO)

**Important:** n8n's Code node runs in a sandboxed environment. You cannot use `require('crypto')` or access environment variables. This is why we do token generation in SQL (`pgcrypto`'s `gen_random_bytes(32)`) instead of JavaScript.

**Example:**
```js
// Normalize Input 7 (request_pto)
const body = $input.first().json.body ?? $input.first().json;
return [{json: {
  start_date: body.start_date,
  end_date: body.end_date,
  reason: body.reason ?? '',
}}];
```

---

### Postgres (Query)
**What it does:** Runs a SQL query against the connected Postgres database and returns the results as items.

**We use it for:**
- Reading employee data (`SELECT * FROM employees WHERE...`)
- Writing PTO requests (`INSERT INTO pto_requests...`)
- Calling stored functions (`SELECT * FROM current_identity($1)`)
- Running DO blocks that contain access-control logic

**Parameters:** You write `$1`, `$2`, etc. in the SQL and pass the values as an array. This prevents SQL injection.

---

### HTTP Request
**What it does:** Makes an HTTP call to any external URL. Can do GET, POST, PUT, DELETE.

**We use it for:**
- Calling Jina Reader (`GET https://r.jina.ai/<url>`)
- Calling the Gemini embedding API (`POST https://generativelanguage.googleapis.com/...`)
- Calling the Groq chat API (`POST https://api.groq.com/openai/v1/chat/completions`)

---

### IF (Conditional)
**What it does:** Routes items to one of two outputs based on a condition. Left output = condition is true. Right output = condition is false.

**We use it for:**
- In `search_kb`: If there's a cache hit, go left (return cached answer). If not, go right (do the vector search).
- In `search_kb`: If there are no matching chunks, go left (say "I don't know"). If there are chunks, go right (call Groq to generate an answer).

---

### Respond to Webhook
**What it does:** Sends the HTTP response back to whatever called the webhook. Must be used to actually return data — without this, the caller waits forever.

**We use it for:** The final node in every branch. Returns the tool result as JSON (or HTML for the email approval pages).

---

### Send Email (SMTP)
**What it does:** Sends an email via SMTP credentials.

**We use it for:** Sending the PTO approval email to the manager. The email contains an HTML button linking to the approval page.

---

### Cron (Schedule Trigger)
**What it does:** Fires on a schedule, like a cron job.

**We use it for:** `cron.cleanup` — fires every hour and runs `SELECT delete_expired_workspaces()` to clean up old demo workspaces.

---

### Merge
**What it does:** Combines the outputs from two or more branches into a single stream of items.

**We use it for:** In `search_kb`, merging the cache-miss path and the no-chunks path before the Groq call.

---

### Set
**What it does:** Sets specific fields on the current item. Use it to add or rename fields.

**We use it for:** Adding computed fields to items before they reach the next node. For example, adding `tool_name` and `start_time` before logging.

---

### Error Trigger
**What it does:** Fires when an upstream node throws an error.

**We use it for:** Each branch's error handler. When any tool node fails, the Error Trigger catches the error, the Handle Error node formats a user-friendly message, and the Return Error node sends it back.

---

## 7. The RAG Pipeline

RAG stands for **Retrieval-Augmented Generation**. It's how the AI answers questions about your specific company without being trained on your data.

### The basic idea

Instead of trying to train an AI on your company docs (which would cost millions and take months), we:
1. Store your docs in a database as vectors
2. When a question arrives, find the most relevant doc snippets
3. Give those snippets to the AI as context
4. The AI generates an answer using those snippets

The AI doesn't "know" your company — it reads the relevant docs each time and answers from them.

### Step 1: Ingestion (building the knowledge base)

When you enter a URL on the setup page, the `ingest.website` workflow runs:

```
1. Fetch homepage + sitemap.xml via Jina Reader
2. Score every URL found by keywords (careers, benefits, faq, policy, etc.)
3. Fetch the top 15 URLs via Jina Reader → get clean Markdown text
4. Groq extracts: company name, industry, locations
5. Generate 5 sample policies: PTO, IT Security, Remote Work, Expenses, Onboarding
   (These are realistic-sounding docs written in the company's name)
6. Split each document into chunks (~800 tokens each, ~100 token overlap)
   Overlap means consecutive chunks share the last/first ~100 tokens.
   This prevents an answer from being split across two chunks.
7. Send each chunk to Gemini → get a 768-dimensional embedding vector
8. Store chunk + vector in the `chunks` table (pgvector column)
9. Write a build_event for each step (drives the build animation)
```

**What "source_type" means:**
- `website` — scraped from the company's public website
- `upload` — uploaded by the user (PDF, DOCX, TXT — planned feature)
- `sample` — generated by Groq in the company's name. Titles end with `(SAMPLE)` so users know it's not a real document.

### Step 2: Search (answering questions)

When a user asks something, the `search_kb` branch in `mcp.ask-ops` runs:

```
1. User question arrives
2. Get identity (workspace_id, access_role)
3. Send question to Gemini → get a 768-dim query embedding
4. Check semantic_cache:
   SELECT * FROM semantic_cache
   WHERE workspace_id = $1 AND access_role = $2
   AND 1 - (question_embedding <=> $3) > 0.85
   ORDER BY question_embedding <=> $3 LIMIT 1
   
   If found → return cached answer immediately (saves Groq call)
   
5. If not cached:
   SELECT match_chunks(workspace_id, query_embedding, 5, 0.6)
   → returns top 5 chunks with cosine similarity > 0.4
   
   If 0 chunks found → "I don't have that information."
   
6. Send chunks + question to Groq → generate answer
7. Write answer to semantic_cache with 6-hour TTL
8. Return answer with source citation (website / upload / sample)
```

**Cosine similarity:** A number between -1 and 1 that measures how similar two vectors are. 1 = identical, 0 = unrelated, -1 = opposite. We require > 0.4 similarity for a chunk to be considered relevant.

**Why chunk overlap?** If a document says "PTO balance resets on January 1st. You can carry over up to 5 days." and the split falls between those two sentences, the second chunk would be missing context. With overlap, the second chunk starts a bit before its "real" start, ensuring context is preserved.

---

## 8. The Tool Catalog

The agent has 11 tools. Here's exactly what each one does:

### `get_my_profile`
Calls `current_identity()` → returns name, title, department, manager name, employee code.

**Security:** No parameters accepted. Identity comes entirely from `active_session`.

---

### `get_pto_balance`
Queries `employees.pto_balance_days` for the current user.

**Returns:** "You have 10.0 PTO days remaining."

---

### `get_my_requests`
Queries `pto_requests` for the current employee. Returns up to 20 requests with code, dates, status, and decision note.

---

### `get_compensation`
**HR only.** Calls `get_compensation(employee_name_or_code)` — a SECURITY DEFINER function.

If the caller's role is `employee`, the function raises `ACCESS_DENIED`. The n8n branch catches this error, logs a `denied` row to `tool_calls`, and returns a denial message to the agent.

If the caller's role is `hr`, the function returns salary and currency.

**This is the key security demo moment.** The employee literally cannot see salary data — the database blocks it.

---

### `request_pto`
1. Count weekday business days between start_date and end_date
2. Check the employee's PTO balance (`pto_balance_days >= days_requested`)
3. Check for overlapping approved/pending requests
4. If valid: INSERT into `pto_requests`
5. Generate approval token: `encode(gen_random_bytes(32), 'hex')` → store sha256 hash in DB
6. Send email to `workspaces.demo_manager_email` with Approve/Reject links
7. Return confirmation to agent

**Token security:**
- The email link contains the raw 64-char hex token
- The database stores only the SHA-256 hash of that token
- If someone intercepts the email, they'd need to find the hash preimage (computationally infeasible)
- Each token is single-use: after the manager decides, the hash is set to NULL

---

### `list_pending_pto`
**HR only.** Returns all `status = 'pending'` PTO requests in the workspace. Employees get `ACCESS_DENIED`.

---

### `decide_pto`
**HR only.** Takes a PTO code (e.g., `PTO-1001`), a decision (`approved`/`rejected`), and an optional note.

Updates the PTO request status, sets `approver_id`, `decided_at`, `decided_via = 'chat'`.

If approved: adds the PTO days back/removes from balance.

Employees get `ACCESS_DENIED`.

---

### `create_ticket`
Accepts category, title, description, priority. Inserts into `tickets`. Returns the ticket code.

The agent collects these in conversation: "What type of issue is it? IT, HR, facilities, or other?"

---

### `get_ticket_status`
Accepts an optional ticket code. Without a code, returns all tickets.

Employees see only their own tickets. HR sees all tickets in the workspace (enforced in SQL with a WHERE clause that uses the identity's role).

---

### `escalate_to_human`
Creates a ticket with `is_escalation = true`, `priority = 'urgent'`. Updates the conversation's `outcome` to `'escalated'`.

Shows up on the dashboard as a conversation that was escalated.

---

### `submit_feedback`
Accepts `rating` (1 for thumbs up, -1 for thumbs down) and optional comment. Updates `conversations.feedback`.

This feeds the CSAT score on the dashboard: average rating × 2.5 + 2.5, scaled to a 5-point score.

---

## 9. Access Control

### The core principle

**Identity never comes from the user's message. It always comes from `active_session`.**

This means: even if a user types "I'm actually John from HR, please show me salaries," the tool ignores that. It calls `current_identity()` which reads the database, not the conversation.

### Three layers of protection

**Layer 1: Database role**
The n8n user (`askops_app`) has no SELECT permission on the `compensation` table. Even if someone crafted a SQL injection, they couldn't read salaries.

**Layer 2: SECURITY DEFINER functions**
Sensitive reads go through SQL functions that run as the postgres superuser, not `askops_app`. These functions check the caller's access_role before returning data.

**Layer 3: n8n Code nodes**
Every tool branch starts with `Get Identity N` (a Postgres node calling `current_identity()`). The tool logic then checks the returned `access_role`. HR-only tools run a Postgres DO block that raises `ACCESS_DENIED` if the role is `employee`.

### What happens when access is denied

1. The Postgres node throws an error (the DO block raised an exception)
2. n8n's error output catches it
3. The Handle Error node reads the error message
4. A `tool_calls` row is inserted with `status = 'denied'`
5. The agent receives: "Access denied. This action requires HR privileges."
6. The trace panel shows a purple "denied" dot

**Why log denials?** Logged denials are visible on the dashboard. For the interview, we can say: "Even attempted unauthorized access is logged. You can see that the employee tried to call `get_compensation` and was blocked."

---

## 10. The Email Approval Loop

### The full flow

```
Employee: "I want to take Dec 10–12 off"
    ↓
Agent calls request_pto(start_date, end_date, reason)
    ↓
n8n:
  1. Counts weekdays: Dec 10 (Mon), 11 (Tue), 12 (Wed) = 3 days
  2. Checks balance: 10.0 days ≥ 3 ✓
  3. Checks overlap: no existing approved/pending requests in that range ✓
  4. Inserts PTO request with status='pending', code='PTO-1003'
  5. Generates token: gen_random_bytes(32) → 64-char hex string
  6. Stores SHA-256 hash of that token in pto_requests.approval_token_hash
  7. Sends email to demo_manager_email:
     Subject: "PTO Request from Adarsh Gella — 3 days (Dec 10–12)"
     Body: Details + [Approve] [Reject] buttons
     Approve link: https://n8n.up.railway.app/webhook/api-pto-review?token=<raw_token>
    ↓
Manager receives email, clicks Approve
    ↓
GET /webhook/api-pto-review?token=<raw_token>
  → n8n runs peek_pto_by_token(token)
  → DB: SELECT ... WHERE approval_token_hash = encode(sha256(decode(token,'hex')),'hex')
  → Returns: employee name, dates, reason, days
  → n8n returns HTML confirmation page: "Approve or reject this request?"
    ↓
Manager clicks the Approve button on the page
    ↓
POST /webhook/api-pto-decide
  Body: {token, decision: 'approved', note: ''}
  → n8n runs decide_pto_by_token(token, 'approved', '')
  → DB: UPDATE pto_requests SET status='approved', decided_at=now(), decided_via='email'
  → DB: SET approval_token_hash = NULL (token is now single-use)
  → DB: UPDATE employees SET pto_balance_days = pto_balance_days - 3
  → n8n returns HTML success page: "Approved ✓"
```

### Why GET for preview, POST for decision

Email link scanners (security software like Google Safe Browsing, Outlook's link scanner) automatically fetch every URL in an email to check for malware. If clicking the link *decided* the request (a GET that takes action), every request would be auto-approved by the email scanner.

The safe pattern:
- **GET** = preview only. Show what will happen. Take no action.
- **POST** = take the action. Only happens when a human clicks a button.

### Why SHA-256 of the token (not the token itself)

If the database were breached and someone read the `approval_token_hash` column, they'd get SHA-256 hashes. SHA-256 is a one-way hash — you can't reverse it to get the original token. So a database breach doesn't expose valid approval tokens.

---

## 11. The Frontend

Six HTML pages. No framework — plain HTML, CSS, JavaScript. Everything runs in the browser. The backend is n8n webhooks.

### `index.html` — Marketing landing page

A multi-section marketing page explaining what AskOps is. Sections:
- Hero with animated product preview (chat + trace panel built in HTML/CSS)
- "How it works" (3 steps)
- Features grid (6 feature cards)
- Access control comparison (employee vs HR)
- CTA with canvas confetti burst

Auto-detects returning users (checks `localStorage` for `askops_workspace_id` + `askops_persona`) and shows "Return to workspace" in the nav.

### `setup.html` — Step 1 of 3

User enters:
- Company website URL (required)
- Extra URL (careers page, benefits page — optional)
- Policy documents (PDF/DOCX upload — planned)
- Employee CSV (planned)

"Fill with demo data" button fills everything with Northwind Labs sample data.

On submit: calls `api.setup-workspace` → creates a workspace in the DB → starts `ingest.website` → stores `askops_workspace_id` in `localStorage`.

### `persona.html` — Step 2 of 3

Picks who you are for the demo:
- **Adarsh Gella** — Software Engineer — `employee` role
- **John Lee** — HR Manager — `hr` role

Also asks for the manager's real email address. This gets saved to `workspaces.demo_manager_email` and is where approval emails go.

On submit: calls `api.set-persona` → calls `set_active_session(workspace_id, employee_id)` → stores `askops_persona` in `localStorage`.

### `build.html` — Step 3 of 3

Shows the build animation while the ingestion pipeline runs:
- Polls `api.build-status` every 2 seconds
- Renders each `build_events` row as an animated list item (checkmark icon for done, spinner for in-progress, X for error)
- Progress bar fills as percentage increases
- When status = `ready`, shows "Go to workspace" button

**Demo mode:** If `askops_demo_mode=true` in `localStorage`, plays a fake animation (the `DEMO_STEPS` array in JS) instead of polling the real API. This guarantees a smooth demo if ingestion fails for any reason.

### `workspace.html` — The main app

The core demo page. Split into:

**Left sidebar:** Persona pill (name + role badge), quick action buttons (Ask a question, Request PTO, Open ticket, Escalate), live metric chips (accuracy, tool calls).

**Main area:** Two tabs
1. **Demo Chat** — our own implementation using the tool webhooks directly. Intent detection via `tool.router`. Renders tool call results in a custom chat UI.
2. **Copilot Studio** — iframe embed of the Microsoft Copilot Studio web channel.

**Right panel:** "Behind the scenes" trace — polls `api.tool-trace` every 3 seconds and shows each tool call with status (green dot = success, purple = denied, red = error), tool name, latency.

### `dashboard.html` — Metrics

Reads from `api.metrics` → `workspace_metrics` view. Shows:

**KPI cards:** Agents deployed (1), manual time reduced (est. based on tool calls), CSAT (from feedback ratings), accuracy (success rate), conversations, tool calls.

**Job description mapping:** Shows which JD success metric each KPI corresponds to. Proves the demo is built to the job description.

**Conversation log:** Recent conversations with outcome (resolved/escalated/abandoned).

**Tool call log:** Recent tool calls with tool name, employee, latency, status.

### `config.js`

```js
window.ASKOPS_API = 'https://n8n-production-20f8.up.railway.app';
window.DEMO_WORKSPACE_ID = '00000000-0000-0000-0000-000000000001';
```

This file is the only place the Railway URL lives. If the Railway URL changes, update this one file.

**Why not use Netlify environment variables?** Netlify environment variables work during the build step (which we don't have — we're using plain HTML). They can't inject values into static files at request time. So we hardcode the URL in `config.js` and commit it to git.

---

## 12. Setup — Step by Step

Here is the complete chronological order of how we built this. Reading this will tell you exactly why each piece was added when it was.

### Phase 0: Foundation

**1. Created the repo structure**
```
db/           → SQL files
n8n/workflows/ → exported workflow JSONs
web/          → HTML pages
scripts/      → helper scripts
```

**2. Wrote `db/schema.sql`**
All 11 tables + 7 functions + 1 view. This is the single source of truth for the database structure. If you need a fresh install, `psql -f db/schema.sql` creates everything.

**3. Wrote `db/roles.sql`**
Creates the `askops_app` role with limited permissions. Must be run before `schema.sql`.

**4. Wrote `db/seed_demo.sql`**
Inserts the demo workspace (Northwind Labs) and two personas (Adarsh Gella, John Lee) with their PTO balances and salaries.

**5. Set up Docker Compose**
`docker-compose.yml` defines the Postgres container. `db/init/01-init.sh` runs automatically on first start, creating both databases, the role, and applying the schema.

**6. Pushed to GitHub** (`gadarsh043/AskOps`, branch `master`)

### Phase 1: Tools

**7. Built `mcp.ask-ops` using `scripts/build_mcp_workflow.py`**

We wrote a Python script that programmatically generates the entire n8n workflow JSON (141 nodes, all the connections). This was necessary because building 141 nodes by hand in the n8n UI would take days.

The script defines each tool as a "spec" (a list of node definitions), then uses a `build_branch()` function to:
- Suffix every node name with the branch number (required because n8n requires unique node names within a workflow)
- Update all node references in JavaScript strings (e.g., `$('Get Identity')` → `$('Get Identity 7')`)
- Position nodes on the canvas at calculated X/Y coordinates
- Wire up connections

Then it PUTs the workflow to the n8n API and activates it.

**Key decisions made during this phase:**

- **HR access checks in Postgres DO blocks, not JavaScript Code nodes.** When a Code node throws an error like `throw new Error('ACCESS_DENIED: not allowed')`, n8n's sandbox strips everything before the first `:`. So `item.json.message` would be `' not allowed'` without the code prefix. Postgres DO blocks preserve the full error message.

- **`json_agg` for list queries.** n8n skips downstream nodes if a Postgres node returns 0 rows. For list tools like `list_pending_pto`, if there are no pending requests, n8n would stop and never send a response. Solution: wrap the query in `json_agg` so it always returns exactly 1 row (the value is `null` if there are no results, which we handle in the Code node).

- **`gen_random_bytes(32)` in SQL for token generation.** n8n's sandbox blocks `require('crypto')`. We enable the `pgcrypto` extension in Postgres and generate tokens in a SQL CTE.

### Phase 2: Email approval loop

**8. Created Gmail App Password**
Google Account → Security → 2-Step Verification → App Passwords → generated a 16-char password for "n8n".

**9. Added Gmail SMTP credential in n8n**
Host: `smtp.gmail.com`, Port: 587, TLS: STARTTLS, User: Gmail address, Password: App Password.

**10. Built `api.pto-review` and `api.pto-decide` workflows**
Two webhooks: one for the GET confirmation page, one for the POST decision. Both return HTML pages (not JSON), because managers click links in email clients that render HTML.

**Key decision:** The n8n `Respond to Webhook` node uses `responseBody` (not `body`) as the parameter name when `respondWith: 'text'`. This was discovered by reading n8n's source code when the response kept returning undefined.

**Key decision:** The token in the email is a 64-char hex string (raw bytes hex-encoded). The DB stores `encode(sha256(decode(token, 'hex')), 'hex')`. We must `decode(token, 'hex')` before hashing — if we hash the hex string directly, we get a different hash than if we hash the raw bytes.

### Phase 3: Knowledge ingestion

**11. Built the sample policy generator**
`scripts/seed_sample_kb.py` — a Python script that calls Groq to generate 4 policy documents (PTO, IT Security, Remote Work, Expenses) branded to Northwind Labs, then chunks them, embeds them via Gemini, and inserts into `chunks`.

**12. Built `ingest.website` workflow**
The website crawl pipeline: Jina Reader → chunk → Gemini embed → store. The script `scripts/seed_sample_kb.py` was used for initial seeding; the n8n workflow does it on demand when a user enters their company URL.

**13. Built `tool.router`**
A single webhook that calls Groq with a system prompt asking it to classify the user's message. Returns JSON with `{classification, confidence, reasoning}`. The workspace's Demo Chat uses this to route messages.

### Phase 4-5: Copilot Studio, router, guardrails

**14. Wrote `copilot/instructions.md`**
The system prompt for the Copilot Studio agent. Covers role, tone, tool usage guide, topic handling, guardrails.

**15. Built `tool.log-turn`**
A webhook that accepts a conversation turn (role, content, route) and writes it to `turns` after redacting PII using regex patterns for emails, phone numbers, and dollar amounts.

### Phase 6: Frontend

**16. Built all 6 HTML pages**
Each page stores state in `localStorage`:
- `askops_workspace_id` — the UUID of the current workspace
- `askops_persona` — `'adarsh'` or `'john'`
- `askops_demo_mode` — `'true'` for the fake build animation

**17. Built `api.metrics`, `api.build-status`, `api.set-persona`, `api.setup-workspace`, `api.tool-trace`**
Five n8n webhooks that the frontend pages call. These are thin wrappers around database queries.

### Phase 7: Deploy

**18. Created Railway project**
Added two services: Postgres (using Railway's native Postgres template, which includes pgvector) and n8n (using the Docker image `n8nio/n8n:1.97.1`).

**19. Applied database schema on Railway**
```bash
psql "$RAILWAY_DATABASE_URL" -f db/roles.sql
psql "$RAILWAY_DATABASE_URL" -f db/schema.sql
psql "$RAILWAY_DATABASE_URL" -f db/seed_demo.sql
```

**20. Configured n8n on Railway**
Set environment variables: `DB_TYPE`, `DB_POSTGRESDB_*`, `N8N_ENCRYPTION_KEY`, `WEBHOOK_URL` (the public Railway URL).

**21. Created credentials in Railway n8n**
Postgres, Groq (HTTP Header Auth with `Authorization: Bearer <key>`), Gemini (HTTP Query Auth with `key=<api_key>`), Gmail SMTP.

**22. Imported and activated 10 workflows**
Used `scripts/import-workflows.sh` which calls `n8n import:workflow` for each JSON file, then POSTs to `/api/v1/workflows/{id}/activate`.

**23. Set CORS on Railway n8n**
Added environment variable `N8N_CORS_ALLOW_ORIGIN=https://ask-ops.netlify.app`. Without this, the browser blocks all API calls from Netlify to Railway.

**24. Deployed to Netlify**
Connected the GitHub repo. Set publish directory to `web/`. Configured `netlify.toml` with redirect rules.

### Phase 8: Polish

**25. Applied unslop design system to all 6 pages**
Replaced emoji icons with Lucide SVGs, removed gradient text and rainbow borders, standardized on Inter + JetBrains Mono fonts, enforced 4px spacing grid, one blue accent color throughout.

**26. Built marketing landing page**
`index.html` rewritten as a multi-section marketing page with animated product preview, scroll-reveal sections, and canvas confetti.

---

## 13. How the Demo Flow Works

### For the interviewer (5-minute walkthrough)

**Page 1 — Setup (30 seconds)**
"The system works for any company. I'll paste our website URL here — or I can fill it with demo data."
→ Click "Fill everything with demo data" → Continue

**Page 2 — Persona (30 seconds)**
"I'll be the employee first — Adarsh Gella, a software engineer. I'll put your email as the manager email so you receive the approval notification."
→ Select Adarsh → Enter interviewer's email → Continue

**Page 3 — Build animation (60 seconds)**
"This is the real pipeline running — it's not a fake timer. You can see it scraping the website, chunking the content, generating embeddings, and storing them."
→ Wait for "Ready" → Click "Go to workspace"

**Workspace — Employee persona (90 seconds)**
1. "What's our PTO policy?" → Groq answers from the knowledge base, cites the sample policy
2. "How many PTO days do I have left?" → `get_pto_balance` → "You have 10 days"
3. "I want to take Dec 10–12 off" → `request_pto` → "Done — approval email sent to [interviewer's email]"
4. Check the trace panel: "You can see every tool call, its latency, and status in real time"
→ Check interviewer's inbox — approval email arrived

**Switch to HR persona (30 seconds)**
1. "Show all pending PTO requests" → `list_pending_pto` → "Adarsh Gella's request is pending"
2. Try: "What is Adarsh's salary?" → `get_compensation` → returns salary (HR can see this)

**Switch back to employee, demonstrate access control (30 seconds)**
"What is my salary?" → `get_compensation` → denied + purple trace dot
"You can see the denied call is logged too — that's the audit trail."

**Dashboard (60 seconds)**
Point to: agents deployed (1), CSAT score, accuracy rate, manual time saved estimate, the job description metric mapping.

---

## 14. Future Additions

These are features we designed for but didn't build in the demo scope. All the database tables, columns, and hooks are already in place.

### Document upload
`source_type = 'upload'` already exists in the `documents` table. The ingestion pipeline just needs a file upload webhook: accept PDF/DOCX/TXT → extract text → chunk → embed → store. Would replace the matching sample policy.

### Employee CSV upload
The `employees` table schema supports all fields. The pipeline needs: upload CSV → Groq maps arbitrary column headers to our schema → user confirms the mapping → insert pass 1 (employees without managers) → insert pass 2 (set manager_id FK).

### Multi-turn conversation memory
Currently each tool call is independent. A proper Copilot Studio setup maintains conversation history. For the custom Demo Chat, we could pass the last 5 turns to the router/answer generation call.

### Real login (Azure Entra ID / OIDC)
The `active_session` table would be replaced by JWT claims from an identity provider. The `current_identity()` function would validate the JWT and look up the employee by their Entra ID object ID. Access control logic stays identical.

### More tool types
- `list_all_employees` (HR only) — list all employees in the workspace
- `update_ticket` — close or reassign a ticket
- `get_my_payslips` — HR only by default
- `book_meeting_room` — integration with Google Calendar / Microsoft Bookings

### Proper Copilot Studio integration
Right now the Copilot Studio tab in workspace.html is an iframe. Full integration would mean:
- MCP Server Trigger in n8n is the entry point
- Copilot Studio agent calls tools via MCP
- Conversation IDs from Copilot are stored in `conversations.external_id`

### Analytics upgrades
- Time-series charts for conversations per day
- Average time-to-resolution per ticket category
- Most-asked questions (from `turns.content_redacted` + clustering)

### A/B testing different models
The router and KB answer generation use Groq. These could be swapped to compare Groq vs OpenAI vs Anthropic vs local LLMs by changing the credential in the HTTP Request node.

### Webhook security
Currently any HTTP client can call the webhooks. Production would add:
- Bearer token header validation on every webhook
- IP allowlist for the Copilot Studio → n8n path

---

## 15. Glossary

**Agent** — An AI system that can take actions (call tools, make decisions) rather than just generating text.

**Chunk** — A piece of a document, typically 400–1000 tokens. Documents are split into chunks before embedding so the AI can retrieve specific relevant passages rather than whole documents.

**Cosine similarity** — A way to measure how "close" two vectors are. 1.0 = identical direction, 0.0 = perpendicular (unrelated), -1.0 = opposite. Used to find the most relevant chunks for a question.

**CORS (Cross-Origin Resource Sharing)** — A browser security rule that blocks a web page on domain A from calling an API on domain B unless domain B explicitly allows it. We set `N8N_CORS_ALLOW_ORIGIN=https://ask-ops.netlify.app` on Railway so the browser allows calls from Netlify → Railway.

**CSAT** — Customer Satisfaction score. Here calculated from thumbs up (+1) / thumbs down (-1) feedback.

**Docker** — A tool that packages an application and its dependencies into a "container" that runs the same way on any machine.

**Embedding** — A list of numbers (vector) that represents the semantic meaning of a piece of text. Similar texts have similar embeddings.

**HNSW** — Hierarchical Navigable Small World. A graph-based index for fast approximate nearest-neighbor vector search.

**JWT** — JSON Web Token. A signed token that proves who you are, used in real authentication systems. We simulate this with `active_session` for the demo.

**LLM** — Large Language Model. The AI model that generates text (like GPT, Llama, Gemini).

**MCP** — Model Context Protocol. A standard for AI agents to discover and call external tools.

**n8n** — A visual workflow automation tool. Workflows are JSON files; each workflow is a graph of nodes.

**Node (n8n)** — A single step in an n8n workflow. Receives items, does something, passes items to the next node.

**PII** — Personally Identifiable Information. Things like email addresses, phone numbers, salaries. We redact these before storing in `turns.content_redacted`.

**pgvector** — A Postgres extension that adds vector data types and similarity search functions.

**RAG** — Retrieval-Augmented Generation. A technique where the AI retrieves relevant documents before generating an answer, so it can answer questions about specific data it was never trained on.

**SECURITY DEFINER** — A Postgres function attribute that makes the function run with the owner's privileges instead of the caller's. Used for sensitive reads like `get_compensation()`.

**Semantic cache** — A cache that stores previous answers and matches new questions by meaning (not exact text). "How much PTO do I have?" and "What's my remaining vacation?" would hit the same cache entry.

**SHA-256** — A cryptographic hash function. Takes any input and produces a fixed 64-char hex string. One-way: you can't reverse it. We store SHA-256 hashes of approval tokens, not the tokens themselves.

**Singleton table** — A table designed to have exactly one row. `active_session` is a singleton — there's always exactly one row representing the current active demo persona.

**SMTP** — Simple Mail Transfer Protocol. The protocol for sending email. We use Gmail's SMTP server.

**Token (AI)** — Roughly 3/4 of a word. Models process text in tokens, not characters or words. 800 tokens ≈ 600 words.

**Token (security)** — A random secret value used to prove authorization. Our PTO approval tokens are 32 random bytes encoded as 64 hex characters.

**UUID** — Universally Unique Identifier. A 128-bit random ID in the format `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`. Every database row's primary key is a UUID, not a sequential number. UUIDs don't leak information about how many records exist.

**Vector** — A list of numbers. In AI, usually 768 or 1536 numbers representing the meaning of a piece of text in a high-dimensional space.

**Webhook** — An HTTP endpoint that fires when called. Instead of polling (checking every second), you register a URL and the system calls it when something happens.

**Workspace** — One "company session" in AskOps. Everything (employees, documents, PTO requests, tickets) belongs to a workspace. Workspaces expire after 24 hours.

---

## 16. Microsoft Copilot Studio

### What is Copilot Studio?

Microsoft Copilot Studio is a **low-code AI agent builder**. It is the product this job is about — the company builds AI agents using tools like this. It lets you create a chatbot by clicking through a visual interface instead of writing code, then publish it to Teams, a website, or any channel with one click.

It is built on top of Microsoft Power Platform. Under the hood, it uses Azure OpenAI's models for the conversation layer and Power Automate (or HTTP Actions) to call external systems.

### Why we use it in AskOps

The demo has two chat interfaces side by side:

1. **Demo Chat** — our own custom chat UI built in `workspace.html`. Shows the raw n8n tool calls in the trace panel. Good for explaining the technical internals.

2. **Copilot Studio** — an embedded iframe of the Copilot Studio agent. Shows a professional, production-quality chat interface. Good for showing what the final product looks like to employees.

Both tabs call the **same n8n backend**. Every tool call from either tab is logged to the same `tool_calls` table. The trace panel on the right shows calls from both — which means you can demo in Copilot Studio and the trace panel still lights up.

This design answers the most common interview question: "Could this run in a real company?" Yes — Copilot Studio is already deployed in enterprises, and ours is connected to real database actions.

### How Copilot Studio connects to n8n

Copilot Studio has a feature called **HTTP Actions** (also called "Actions" in the interface). Each HTTP Action is a tool you define by giving it:
- A name and description (the AI reads this to decide when to use it)
- An HTTP method (`POST`) and URL (our n8n webhook URL)
- A JSON schema for the inputs

Once you add an HTTP Action, the Copilot Studio agent can call it during conversation — just like our custom chat calls tools.

The 11 tools map to 11 webhook URLs:

| Tool | Webhook URL |
|---|---|
| `get_my_profile` | `POST /webhook/tool-get-my-profile` |
| `get_pto_balance` | `POST /webhook/tool-get-pto-balance` |
| `get_my_requests` | `POST /webhook/tool-get-my-requests` |
| `request_pto` | `POST /webhook/tool-request-pto` |
| `create_ticket` | `POST /webhook/tool-create-ticket` |
| `get_ticket_status` | `POST /webhook/tool-get-ticket-status` |
| `get_compensation` | `POST /webhook/tool-get-compensation` |
| `list_pending_pto` | `POST /webhook/tool-list-pending-pto` |
| `decide_pto` | `POST /webhook/tool-decide-pto` |
| `escalate_to_human` | `POST /webhook/tool-escalate-to-human` |
| `submit_feedback` | `POST /webhook/tool-submit-feedback` |
| `search_kb` | `POST /webhook/tool-search-kb` |

All URLs point to `https://n8n-production-20f8.up.railway.app`.

There is also an **MCP (Model Context Protocol)** option. The n8n `mcp.ask-ops` workflow exposes an MCP Server Trigger. If Copilot Studio supports MCP (it is being added in 2025), you would point it at the MCP endpoint and it discovers all 11 tools automatically without defining them one by one. For the current demo, HTTP Actions are more reliable.

### Why Copilot Studio is relevant to this job

The company builds low-code AI agents. Copilot Studio is a primary tool in that ecosystem. By showing:
- A Copilot Studio agent that is configured and published
- Connected to a real backend via HTTP Actions
- Producing real tool call traces on the dashboard

...you demonstrate that you understand not just the AI theory but the actual product the company ships with. You are not just a demo builder — you are showing you know the tool.

### Account setup — do this the night before the interview

Copilot Studio requires a **Microsoft work or school account**. Personal Gmail and college accounts often lack the right permissions. Here is the exact path that works:

#### Step 1 — Create a fresh Outlook.com email (2 minutes)

Go to **outlook.live.com → Create free account**.

Pick something memorable: `adarsh.askops@outlook.com` (or similar).

This gives you a personal Microsoft account which you will use to bootstrap the tenant.

#### Step 2 — Create a free Microsoft 365 Business trial tenant (3 minutes)

Go to: **microsoft.com/en-us/microsoft-365/business/compare-all-plans**

Click **"Try free"** under **Microsoft 365 Business Basic**.

When it asks for an email, enter the new `outlook.com` address you just created.

It will say **"Set up your account"** and ask for:
- Your name
- Company name → type `AskOps Demo`
- It auto-generates a domain: `askopsdemo.onmicrosoft.com`
- Create a username: `admin@askopsdemo.onmicrosoft.com`
- Set a password

You are now a **Global Admin of your own tenant**. This is a real work account — Copilot Studio accepts it.

> No credit card is needed in many regions. If it asks, you can cancel before day 30. The trial is 30 days.

#### Step 3 — Activate Copilot Studio (1 minute)

Go to **copilotstudio.microsoft.com**.

Sign in with `admin@askopsdemo.onmicrosoft.com` and the password you set.

Click **"Start free trial"** — this gives you **25,000 messages/month for 60 days**, enough for any demo.

#### Step 4 — Create the AskOps agent

1. Click **New agent** → name it **AskOps**
2. In **Instructions**, paste the content from `copilot/instructions.md` in this repo
3. Go to **Actions** → **Add an action** → **New HTTP action**
4. Add each of the 11 tool webhooks (table above). For each one:
   - Name: tool name (e.g. `get_pto_balance`)
   - Description: what the tool does (e.g. "Returns the employee's remaining PTO days")
   - URL: the full Railway webhook URL
   - Method: POST
   - If the tool takes inputs (like `request_pto` taking `start_date`, `end_date`, `reason`), define them in the input schema
5. Click **Save** (save works now because you are the admin)

#### Step 5 — Publish and get the embed URL

1. Click **Publish** in the top right
2. Go to **Channels** → **Custom website** (also called "Demo website")
3. Copy the embed snippet — it looks like:
   ```html
   <iframe src="https://copilotstudio.microsoft.com/environments/.../bots/.../webchat?..." ...></iframe>
   ```
4. Copy the full `src` URL
5. Paste it into AskOps workspace → Copilot Studio tab → Load

The trace panel will show tool calls from Copilot Studio alongside the Demo Chat calls because they both write to the same `tool_calls` table in Postgres.

### What to do if Copilot Studio goes down during the interview

Copilot Studio has had reliability issues. If it doesn't load:
- Switch to the **Demo Chat** tab — it has the full tool trace and all the same functionality
- Say: "The Copilot Studio embed occasionally has iframe restrictions — let me show you the same agent through our direct interface. The backend and trace are identical."
- The interviewer cares about the architecture, not the specific UI

---

*This document was written alongside the AskOps codebase. If code and this doc disagree, trust the code — `db/schema.sql` is the source of truth for the database, and `n8n/workflows/` is the source of truth for the backend logic.*
