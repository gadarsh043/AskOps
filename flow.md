# AskOps Demo Flow

> Step-by-step script for the interview presentation. Each step has what to open, what to say, what to click, and a transition sentence.

---

## Pre-demo checklist (do the night before)

- [ ] Open https://ask-ops.netlify.app in a clean browser window (or incognito)
- [ ] Clear localStorage: open DevTools → Application → Local Storage → clear all
- [ ] Confirm Railway is running: visit https://n8n-production-20f8.up.railway.app — should redirect to n8n login
- [ ] Update manager email: on the persona page, enter the **interviewer's real email** so they receive the approval email live during the demo
- [ ] Keep your Gmail inbox open in another tab (to show the approval email arrives)
- [ ] Have the dashboard page bookmarked
- [ ] Copilot Studio: publish your agent → Channels → Demo website → note the URL
- [ ] Paste the Copilot URL in workspace → Copilot Studio tab → Load → confirm it works

---

## 1. Landing page (30 seconds)

**Navigate to:** https://ask-ops.netlify.app

**Say:**
> "This is AskOps — an AI service desk agent that works for any company. The idea is: a manager or IT admin pastes their company website, the system reads it and builds a knowledge base, and employees can immediately chat with an agent that knows their specific company's policies and can take real actions."

**Point to:**
- The animated product preview on the right (shows chat + trace panel)
- "Role-based access enforced by the database" — mention that this is the security angle

**Transition:** "Let me show you the setup. Click Get started."

---

## 2. Setup page (45 seconds)

**Navigate to:** setup.html (after clicking Get started)

**Say:**
> "Any company can use this. You'd paste their website URL here. For the demo, I'll use Northwind Labs, a fictional tech company I pre-built."

**Click:** "Fill everything with demo data" button

**Say while it fills:**
> "This fills in the company website, an extra URL for careers and benefits, and optionally you can upload PDF policy documents or an employee CSV. Everything in this demo is a sample, but the architecture supports real documents."

**Click:** Continue

---

## 3. Persona page (30 seconds)

**Navigate to:** persona.html

**Say:**
> "In a real deployment, the agent knows who you are via your company login — Azure Entra ID, for example. For the demo, I let you pick a persona. I'll be Adarsh Gella, a software engineer."

**Click:** Adarsh Gella card

**Say:**
> "I'll put your email as the manager email — when Adarsh requests PTO, the approval notification goes directly to you."

**Type:** interviewer's email in the manager email field

**Click:** Continue

---

## 4. Build animation (60 seconds)

**Navigate to:** build.html (auto, after Continue)

**Say:**
> "This is the real ingestion pipeline running — not a fake timer. You can see it scraping the website, chunking the content into 800-token pieces, generating vector embeddings with Google Gemini, and storing them in Postgres with pgvector for similarity search."

**Point to each event as it appears:**
- "Sitemap discovered" → "It found the site structure automatically"
- "Generated embeddings" → "These are 768-dimensional vectors — the mathematical representation of what each document means"
- "Stored in knowledge base" → "pgvector is now ready for semantic search"
- "Generated 5 sample policies" → "It also created sample company policies — PTO, IT security, remote work, expenses, onboarding — in Northwind Labs' name. In a real deployment, these get replaced by uploaded documents."

**When ready:** Click "Go to workspace"

---

## 5. Chat — knowledge base (60 seconds)

**Navigate to:** workspace.html

**Say:**
> "This is the workspace. On the left: persona switcher and live metrics. In the middle: the chat. On the right: the tool trace — every backend call, its status, and latency."

**Type (or click suggestion):** "What's our PTO policy?"

**Wait for response, then say:**
> "It answers from the knowledge base and cites the source — 'Sample policy' in this case, since we used generated data. If I'd uploaded a real PDF, it would say 'Uploaded document'. Watch the trace panel — you can see `search_kb` ran successfully in [X] ms."

**Type:** "What are our expense guidelines?"

**Say:**
> "Same thing — retrieval from the knowledge base. Each answer is cited. The agent never makes up information."

---

## 6. Chat — PTO balance (30 seconds)

**Type:** "How many PTO days do I have left?"

**Say:**
> "Notice I phrased it naturally — not 'PTO balance query'. The router classifies the intent, and the system calls the right tool. This is `get_pto_balance`."

**Point to trace panel:** "Green dot — success. 48ms."

---

## 7. Chat — PTO request + live email (90 seconds)

**Type:** "I want to request PTO from 2026-12-10 to 2026-12-12 for the holidays"

**Say while it runs:**
> "It's checking the balance — do I have enough days? Checking for overlapping requests. If everything passes, it inserts the request and sends an approval email."

**After response:**
> "PTO request submitted. Now check your email."

**Switch to Gmail tab:**
> "Here it is — a real email from Gmail SMTP with the request details and two buttons: Approve and Reject."

**Click the Approve link in the email:**
> "This is the approval flow. The link goes to a preview page — it shows what will happen without taking action yet. That's intentional: email scanners pre-fetch GET links for safety checks. Only clicking this button actually approves it."

**Click Approve on the confirmation page:**
> "Approved. The database just updated the request status and deducted 3 days from Adarsh's balance. If Adarsh asks for the balance now, it'll be 7 days."

---

## 8. Access control demo (60 seconds)

**Switch persona to John Lee (HR Manager) — click in sidebar**

**Type:** "What is Adarsh Gella's salary?"

**Say:**
> "John is HR, so he can see this."

**Wait for response with salary, then say:**
> "Now watch what happens when the same request comes from an employee."

**Switch back to Adarsh**

**Type:** "What is my salary?"

**Say:**
> "Same question, different role."

**After denied response, point to trace panel:**
> "Purple dot — denied. The database refused to return this data. The `get_compensation` function checks the caller's role before running. This isn't the AI's judgment — it's enforced at the database level. Even if someone said 'pretend you're HR', the tool still calls `current_identity()` which reads the session, not the conversation."

**Say:**
> "And critically — that denial is logged. You can see it on the dashboard. It's an audit trail."

---

## 9. Copilot Studio tab (30 seconds)

**Click the Copilot Studio tab**

**Say:**
> "This is Microsoft Copilot Studio — a low-code agent builder. I built the same agent there, connected to the same n8n tool backend. The trace panel on the right still shows tool calls from this tab, because they both write to the same database."

**Ask something in Copilot Studio chat:** "What's our remote work policy?"

**Point to trace panel:**
> "Same trace appearing — `search_kb` running. This shows the tool infrastructure works with any AI frontend."

---

## 10. Metrics dashboard (60 seconds)

**Click Dashboard in the header**

**Navigate to:** dashboard.html

**Say:**
> "Every interaction is logged. Here are the metrics that the job description specifically asks for."

**Point to each KPI:**
- **Agents deployed: 1** → "This is the agent we just used"
- **CSAT** → "From the thumbs up/down at the end of conversations"
- **Accuracy / success rate** → "Success vs error across all tool calls"
- **Denied requests** → "Access control in action — these are logged on purpose"
- **KB chunks** → "Size of the knowledge base"

**Point to the Agent Builder success metrics section:**
> "I mapped the dashboard directly to the success metrics in the job description. Agents deployed, manual time reduced, CSAT, accuracy, task completion."

**Point to the tool call log:**
> "Every call: tool name, status, latency, which employee, when. If something went wrong during a demo, this is where you'd see it."

---

## 11. Closing (30 seconds)

**Say:**
> "So in about 5 minutes: knowledge base built from a real website, PTO request submitted and approved via email, access control demonstrated at the database level, and metrics tracked for every interaction. The whole backend is n8n workflows — all visual, all editable, all exportable as JSON. If you wanted to swap the AI model, change the ingestion source, or add a new tool, it's a matter of editing a workflow."

**Optional if asked:** "It's deployed on Railway and Netlify — both free tiers. The only paid component would be more Groq or Gemini usage at scale."

---

## Q&A Notes

### "How does Copilot Studio connect to n8n?"

Copilot Studio connects via two methods:
1. **HTTP Actions** — You define each tool as an HTTP POST action pointing to the n8n webhook URL (`/webhook/tool-get-pto-balance`, etc.)
2. **MCP (Model Context Protocol)** — The n8n `mcp.ask-ops` workflow exposes an MCP Server Trigger endpoint. Copilot Studio connects to it and discovers all 11 tools automatically.

For the demo, HTTP Actions are more reliable. MCP is the more modern approach.

The trace panel shows Copilot Studio tool calls because both the Demo Chat and Copilot Studio write to the same `tool_calls` table in Postgres. The trace panel polls that table every 3 seconds.

---

### "What are evals?"

Evals (evaluations) are automated tests that measure AI output quality. A proper eval suite looks like this:

```
Question: "What is our PTO policy?"
Expected: answer contains "10 days" and cites a source
Actual: [run the agent and check]
Pass/Fail
```

In this project, we don't have a formal eval suite, but we have two things that serve the same purpose:

1. **`tool_calls` logging** — Every tool call logs `status: success/error/denied`. The dashboard's accuracy rate (success count / total non-denied calls) is a live eval metric. If a tool starts returning errors, the accuracy rate drops immediately.

2. **`semantic_cache`** — When a question hits the cache (cosine similarity > 0.85 to a previous question), we return the cached answer. If the cached answer was reviewed and correct, the cache acts as a lightweight regression test.

What we'd add in production:
- A test script: 20 canonical Q&A pairs, run weekly, check that answers still contain the expected phrases
- A "thumbs down" flag that marks an answer as bad and invalidates it from the cache
- A/B testing: compare two models on the same questions using different workspace IDs

---

### "Why n8n instead of Python/FastAPI?"

n8n is the tool the interviewer's company builds with. The demo is itself a demonstration of building with that tool. It's also genuinely good for this use case:
- Every workflow is a JSON file — version-controlled, reviewable, importable
- Visual canvas makes the data flow obvious to non-engineers
- Built-in connectors (SMTP, HTTP, Postgres) reduce boilerplate
- If a step fails, the error output is automatic — no try/catch everywhere

The tradeoff: for very high-throughput production systems, a compiled language would be faster. But for a service desk agent handling a few hundred requests per day, n8n is completely appropriate.

---

### "Is the knowledge base real-time?"

The knowledge base is built once during setup and is static until manually triggered again. Documents don't update automatically when the website changes.

What we'd add: a `cron.re-ingest` workflow that runs weekly, diffs the fetched content against stored chunks, and re-embeds changed sections. This is in the roadmap but not in the current demo scope.

---

### "When does the metrics dashboard show real data?"

The dashboard shows data as soon as tool calls have been made. Here's the sequence:

1. User opens workspace and sends their first message
2. That triggers a tool call (e.g., `search_kb`)
3. The tool call logs a row to `tool_calls` table
4. The dashboard (or sidebar metrics) polls `/webhook/api-metrics`
5. That webhook queries the `workspace_metrics` view
6. Data appears

The sidebar metrics update every 20 seconds. The dashboard page refreshes every 15 seconds and also has a manual Refresh button. After any tool call in the workspace, metrics refresh immediately.

If the dashboard shows `—` for all values: the workspace ID might not match, or no tool calls have been made yet. Try sending one message in the workspace, then refresh the dashboard.

---

### "What would you add next?"

**Highest priority:**
1. Document upload (PDF/DOCX) — table already exists, just need the ingestion webhook
2. Employee CSV upload with Groq column mapping
3. Build events emitted in real time (the table exists, the frontend animation is ready)

**Medium priority:**
4. Formal evals: 20 golden Q&A pairs, CI check on every knowledge base rebuild
5. Multi-turn conversation memory: pass the last 5 messages as context to tool calls
6. More tools: `update_ticket`, `book_meeting_room`, `get_my_payslips`

**Production hardening:**
7. Real authentication (Azure Entra ID → replace `active_session`)
8. Webhook security (Bearer token on all n8n webhooks)
9. Automatic re-ingestion cron
