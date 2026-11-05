#!/usr/bin/env python3
"""
Build and deploy AskOps API workflows for the frontend:
  api.setup-workspace   POST /webhook/api-setup-workspace
  api.build-status      GET  /webhook/api-build-status
  api.set-persona       POST /webhook/api-set-persona
  api.metrics           GET  /webhook/api-metrics
  api.tool-trace        GET  /webhook/api-tool-trace
  tool.router           POST /webhook/tool-router
  tool.log-turn         POST /webhook/tool-log-turn
"""
import json, urllib.request, urllib.error, time

BASE    = 'http://localhost:5678'
API_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIyZjIyYTczYy04ZGUyLTQyZTMtYTg3ZS01OTBjMGYyMjIyYjciLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwiaWF0IjoxNzkzODU5MzQ2fQ.eAmo5vLR78e7fRQ7rbo3vGjV6r_cdMrM_FYavc4DBII'
CRED    = {'postgres': {'id': '4DuuvBbohpSo7Mr0', 'name': 'AskOps Postgres'}}
GROQ_CRED = {'httpHeaderAuth': {'id': 'AxtE0phNFpQkBki9', 'name': 'AskOps Groq'}}

def api(method, path, body=None):
    headers = {'X-N8N-API-KEY': API_KEY, 'Content-Type': 'application/json'}
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(f'{BASE}{path}', data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'n8n {method} {path} → {e.code}: {e.read().decode()[:400]}')

def wh_nd(nid, name, path, method='GET', response_mode='lastNode'):
    return {
        'id': nid, 'name': name,
        'type': 'n8n-nodes-base.webhook', 'typeVersion': 2,
        'position': [0, 0],
        'parameters': {
            'path': path,
            'httpMethod': method,
            'responseMode': response_mode,
            'options': {'allowedOrigins': '*'}
        },
        'webhookId': nid
    }

def pg_nd(nid, name, sql, x, y, on_error=None):
    n = {'id': nid, 'name': name,
         'type': 'n8n-nodes-base.postgres', 'typeVersion': 2.5,
         'position': [x, y],
         'credentials': CRED,
         'parameters': {'operation': 'executeQuery', 'query': sql.strip(), 'options': {}}}
    if on_error:
        n['onError'] = on_error
    return n

def code_nd(nid, name, js, x, y):
    return {'id': nid, 'name': name,
            'type': 'n8n-nodes-base.code', 'typeVersion': 2,
            'position': [x, y],
            'parameters': {'jsCode': js.strip()}}

def http_nd(nid, name, url, method, body_js, x, y, cred=None):
    n = {
        'id': nid, 'name': name,
        'type': 'n8n-nodes-base.httpRequest', 'typeVersion': 4.2,
        'position': [x, y],
        'parameters': {
            'method': method,
            'url': url,
            'sendBody': True,
            'contentType': 'json',
            'body': body_js,
            'options': {}
        }
    }
    if cred:
        n['credentials'] = cred
    return n

def build_workflow(name, nodes, connections, settings=None):
    return {
        'name': name,
        'nodes': nodes,
        'connections': connections,
        'settings': settings or {'executionOrder': 'v1'},
    }

def conn(from_node, to_node, from_out=0, to_in=0):
    return {from_node: {'main': [[{'node': to_node, 'type': 'main', 'index': to_in}]]}}

def merge_conn(*dicts):
    result = {}
    for d in dicts:
        for k, v in d.items():
            if k in result:
                for out_idx, targets in enumerate(v.get('main', [])):
                    while len(result[k]['main']) <= out_idx:
                        result[k]['main'].append([])
                    result[k]['main'][out_idx].extend(targets)
            else:
                result[k] = v
    return result

def deploy_workflow(wf_dict, wf_name):
    # Check if workflow with this name exists
    all_wfs = api('GET', '/api/v1/workflows?limit=100')
    existing = [w for w in all_wfs.get('data', []) if w['name'] == wf_name]
    if existing:
        wf_id = existing[0]['id']
        print(f'  Updating {wf_name} ({wf_id})')
        api('PUT', f'/api/v1/workflows/{wf_id}', wf_dict)
        try:
            api('POST', f'/api/v1/workflows/{wf_id}/activate')
        except Exception as e:
            print(f'  Warning: activate failed: {e}')
        return wf_id
    else:
        print(f'  Creating {wf_name}')
        result = api('POST', '/api/v1/workflows', wf_dict)
        wf_id = result['id']
        try:
            api('POST', f'/api/v1/workflows/{wf_id}/activate')
        except Exception as e:
            print(f'  Warning: activate failed: {e}')
        return wf_id


# ══════════════════════════════════════════════════════════════════════════════
# 1. api.build-status — GET /webhook/api-build-status?workspace_id=X
# ══════════════════════════════════════════════════════════════════════════════
def build_build_status():
    nodes = [
        wh_nd('wh1', 'Webhook', 'api-build-status', 'GET'),
        pg_nd('pg1', 'Get Build Events',
              """SELECT COALESCE(
                   json_agg(
                     json_build_object(
                       'step', e.step,
                       'status', e.status,
                       'message', e.message,
                       'progress', e.progress,
                       'created_at', TO_CHAR(e.created_at,'YYYY-MM-DD"T"HH24:MI:SS"Z"')
                     ) ORDER BY e.id ASC
                   ),
                   '[]'::json
                 ) AS events
                 FROM build_events e
                 WHERE e.workspace_id = '{{ $json.query.workspace_id }}'::uuid""", 220, 0),
        code_nd('fmt1', 'Format', """
const d = $input.first().json;
const events = d.events || [];
return [{ json: { events: events, count: events.length } }];
""", 440, 0),
    ]
    nodes[0]['position'] = [0, 0]
    connections = merge_conn(conn('Webhook', 'Get Build Events'), conn('Get Build Events', 'Format'))
    return build_workflow('api.build-status', nodes, connections)


# ══════════════════════════════════════════════════════════════════════════════
# 2. api.set-persona — POST /webhook/api-set-persona
# ══════════════════════════════════════════════════════════════════════════════
def build_set_persona():
    nodes = [
        wh_nd('wh2', 'Webhook', 'api-set-persona', 'POST'),
        pg_nd('pg2a', 'Get Employee',
              """SELECT id, workspace_id, full_name, access_role, title, employee_code, department
                 FROM employees
                 WHERE employee_code = '{{ $json.body.employee_code }}'
                   AND workspace_id = '{{ $json.body.workspace_id }}'::uuid
                 LIMIT 1""", 220, 0),
        pg_nd('pg2b', 'Set Session',
              """SELECT set_active_session(
                   '{{ $json.workspace_id }}'::uuid,
                   '{{ $json.id }}'::uuid
                 ) AS ok""", 440, 0),
        pg_nd('pg2c', 'Update Manager Email',
              """UPDATE workspaces
                 SET demo_manager_email = '{{ $("Webhook").first().json.body.manager_email }}'
                 WHERE id = '{{ $("Webhook").first().json.body.workspace_id }}'::uuid
                   AND '{{ $("Webhook").first().json.body.manager_email }}' != ''
                 RETURNING id""", 660, 0, 'continueRegularOutput'),
        code_nd('fmt2', 'Format', """
const emp = $('Get Employee').first().json;
return [{ json: {
  status: 'ok',
  employee_code: emp.employee_code,
  full_name: emp.full_name,
  access_role: emp.access_role,
  title: emp.title,
  department: emp.department
} }];
""", 880, 0),
    ]
    nodes[0]['position'] = [0, 0]
    connections = merge_conn(
        conn('Webhook', 'Get Employee'),
        conn('Get Employee', 'Set Session'),
        conn('Set Session', 'Update Manager Email'),
        conn('Update Manager Email', 'Format'),
    )
    return build_workflow('api.set-persona', nodes, connections)


# ══════════════════════════════════════════════════════════════════════════════
# 3. api.metrics — GET /webhook/api-metrics?workspace_id=X
# ══════════════════════════════════════════════════════════════════════════════
def build_metrics():
    nodes = [
        wh_nd('wh3', 'Webhook', 'api-metrics', 'GET'),
        pg_nd('pg3', 'Get Metrics',
              """SELECT * FROM workspace_metrics
                 WHERE workspace_id = '{{ $json.query.workspace_id }}'::uuid""", 220, 0),
        code_nd('fmt3', 'Format', """
const rows = $input.all().map(i => i.json);
if (!rows.length) return [{ json: { status: 'not_found' } }];
return [{ json: { status: 'ok', metrics: rows[0] } }];
""", 440, 0),
    ]
    nodes[0]['position'] = [0, 0]
    connections = merge_conn(conn('Webhook', 'Get Metrics'), conn('Get Metrics', 'Format'))
    return build_workflow('api.metrics', nodes, connections)


# ══════════════════════════════════════════════════════════════════════════════
# 4. api.tool-trace — GET /webhook/api-tool-trace?workspace_id=X&limit=20
# ══════════════════════════════════════════════════════════════════════════════
def build_tool_trace():
    nodes = [
        wh_nd('wh4', 'Webhook', 'api-tool-trace', 'GET'),
        pg_nd('pg4', 'Get Tool Calls',
              """SELECT COALESCE(
                   json_agg(
                     json_build_object(
                       'tool_name', tc.tool_name,
                       'status', tc.status,
                       'latency_ms', tc.latency_ms,
                       'created_at', TO_CHAR(tc.created_at,'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
                       'output_preview', SUBSTRING(tc.output::text, 1, 300)
                     ) ORDER BY tc.created_at DESC
                   ),
                   '[]'::json
                 ) AS calls
                 FROM (
                   SELECT tool_name, status, latency_ms, created_at, output
                   FROM tool_calls
                   WHERE workspace_id = '{{ $json.query.workspace_id }}'::uuid
                   ORDER BY created_at DESC
                   LIMIT 25
                 ) tc""", 220, 0),
        code_nd('fmt4', 'Format', """
const d = $input.first().json;
return [{ json: { status: 'ok', calls: d.calls || [] } }];
""", 440, 0),
    ]
    nodes[0]['position'] = [0, 0]
    connections = merge_conn(conn('Webhook', 'Get Tool Calls'), conn('Get Tool Calls', 'Format'))
    return build_workflow('api.tool-trace', nodes, connections)


# ══════════════════════════════════════════════════════════════════════════════
# 5. api.setup-workspace — POST /webhook/api-setup-workspace
# ══════════════════════════════════════════════════════════════════════════════
def build_setup_workspace():
    seed_personas_sql = """
WITH
adarsh AS (
  INSERT INTO employees
    (workspace_id, employee_code, full_name, email, title,
     department, access_role, hire_date, pto_balance_days, is_persona)
  VALUES (
    '{{ $json.id }}'::uuid,
    'EMP-042', 'Adarsh Gella', 'adarsh.gella@demo.local',
    'Software Engineer', 'Engineering', 'employee', '2025-03-10', 8, true
  )
  ON CONFLICT (workspace_id, employee_code) DO UPDATE SET is_persona = true
  RETURNING id
),
john AS (
  INSERT INTO employees
    (workspace_id, employee_code, full_name, email, title,
     department, access_role, hire_date, pto_balance_days, is_persona)
  VALUES (
    '{{ $json.id }}'::uuid,
    'EMP-007', 'John Lee', 'john.lee@demo.local',
    'HR Manager', 'People', 'hr', '2019-06-01', 15, true
  )
  ON CONFLICT (workspace_id, employee_code) DO UPDATE SET is_persona = true
  RETURNING id
),
maya AS (
  INSERT INTO employees
    (workspace_id, employee_code, full_name, email, title,
     department, access_role, hire_date, pto_balance_days, is_persona)
  VALUES (
    '{{ $json.id }}'::uuid,
    'EMP-015', 'Maya Patel', 'maya.patel@demo.local',
    'Engineering Manager', 'Engineering', 'employee', '2020-01-15', 12, false
  )
  ON CONFLICT (workspace_id, employee_code) DO UPDATE SET is_persona = false
  RETURNING id
),
set_mgr AS (
  UPDATE employees e SET manager_id = maya.id
  FROM adarsh, maya WHERE e.id = adarsh.id
)
SELECT '{{ $json.id }}'::text AS workspace_id FROM adarsh
"""
    nodes = [
        wh_nd('wh5', 'Webhook', 'api-setup-workspace', 'POST'),
        pg_nd('pg5a', 'Create Workspace',
              """INSERT INTO workspaces
                   (company_name, website_url, extra_url, industry, status,
                    demo_manager_email, webhook_url, expires_at)
                 VALUES (
                   COALESCE(NULLIF('{{ $json.body.company_name }}',''), 'Demo Company'),
                   NULLIF('{{ $json.body.company_url }}',''),
                   NULLIF('{{ $json.body.extra_url }}',''),
                   COALESCE(NULLIF('{{ $json.body.industry }}',''), 'Technology'),
                   'building',
                   COALESCE(NULLIF('{{ $json.body.manager_email }}',''), 'your-email@example.com'),
                   'http://localhost:5678',
                   now() + interval '7 days'
                 )
                 RETURNING id""", 220, 0),
        pg_nd('pg5seed', 'Seed Personas', seed_personas_sql, 440, 0),
        pg_nd('pg5b', 'Set Persona Session',
              """SELECT set_active_session(
                   '{{ $json.workspace_id }}'::uuid,
                   (SELECT id FROM employees
                    WHERE workspace_id = '{{ $json.workspace_id }}'::uuid
                      AND employee_code = COALESCE(NULLIF('{{ $("Webhook").first().json.body.persona_code }}',''), 'EMP-042')
                    LIMIT 1)
                 ) AS ok""", 660, 0, 'continueRegularOutput'),
        pg_nd('pg5c', 'Emit Start Event',
              """INSERT INTO build_events (workspace_id, step, status, message, progress)
                 VALUES (
                   '{{ $("Seed Personas").first().json.workspace_id }}'::uuid,
                   'ready', 'done', 'Workspace created. Ready to ingest knowledge base.', 100
                 )
                 RETURNING '{{ $("Seed Personas").first().json.workspace_id }}'::text AS workspace_id""", 880, 0),
        code_nd('fmt5', 'Format', """
const wsId = $('Emit Start Event').first().json.workspace_id
  || $('Seed Personas').first().json.workspace_id;
return [{ json: { status: 'building', workspace_id: wsId } }];
""", 1100, 0),
    ]
    nodes[0]['position'] = [0, 0]
    connections = merge_conn(
        conn('Webhook', 'Create Workspace'),
        conn('Create Workspace', 'Seed Personas'),
        conn('Seed Personas', 'Set Persona Session'),
        conn('Set Persona Session', 'Emit Start Event'),
        conn('Emit Start Event', 'Format'),
    )
    return build_workflow('api.setup-workspace', nodes, connections)


# ══════════════════════════════════════════════════════════════════════════════
# 6. tool.router — POST /webhook/tool-router
#    Classifies a user query as faq / action / sensitive / off_topic / smalltalk
# ══════════════════════════════════════════════════════════════════════════════
def build_router():
    sys_prompt = (
        'You are a query classifier for an IT/HR service desk chatbot. '
        'Classify the user message into exactly one of these categories:\\n'
        '- faq: factual question answerable from knowledge base (policies, procedures, company info)\\n'
        '- action: request to perform an action (PTO request, create ticket, check balance, escalate)\\n'
        '- sensitive: involves salary, compensation, performance reviews, termination, discrimination\\n'
        '- off_topic: not related to work, IT, HR, or company matters\\n'
        '- smalltalk: greeting, thanks, casual conversation\\n\\n'
        'Respond with ONLY valid JSON: {"classification": "<category>", "confidence": 0.0-1.0, "reason": "<one sentence>"}'
    )
    nodes = [
        wh_nd('wh6', 'Webhook', 'tool-router', 'POST'),
        code_nd('prep6', 'Build Groq Body', f"""
const query = $input.first().json.body?.query || '';
const body = JSON.stringify({{
  model: 'openai/gpt-oss-120b',
  messages: [
    {{ role: 'system', content: {json.dumps(sys_prompt)} }},
    {{ role: 'user', content: query }}
  ],
  temperature: 0.1,
  max_tokens: 100
}});
return [{{ json: {{ query, groq_body: body }} }}];
""", 220, 0),
        {
            'id': 'http6', 'name': 'Groq Classify',
            'type': 'n8n-nodes-base.httpRequest', 'typeVersion': 4.2,
            'position': [440, 0],
            'credentials': GROQ_CRED,
            'parameters': {
                'method': 'POST',
                'url': 'https://api.groq.com/openai/v1/chat/completions',
                'authentication': 'genericCredentialType',
                'genericAuthType': 'httpHeaderAuth',
                'sendBody': True,
                'specifyBody': 'json',
                'jsonBody': '={{ $json.groq_body }}',
                'options': {}
            }
        },
        code_nd('fmt6', 'Format', """
const content = $input.first().json.choices[0].message.content.trim();
let parsed;
try {
  parsed = JSON.parse(content);
} catch {
  parsed = { classification: 'faq', confidence: 0.5, reason: 'parse error fallback' };
}
const query = $('Build Groq Body').first().json.query || '';
return [{ json: {
  query,
  classification: parsed.classification,
  confidence: parsed.confidence,
  reason: parsed.reason
} }];
""", 660, 0),
    ]
    nodes[0]['position'] = [0, 0]
    connections = merge_conn(
        conn('Webhook', 'Build Groq Body'),
        conn('Build Groq Body', 'Groq Classify'),
        conn('Groq Classify', 'Format'),
    )
    return build_workflow('tool.router', nodes, connections)


# ══════════════════════════════════════════════════════════════════════════════
# 7. tool.log-turn — POST /webhook/tool-log-turn
#    Writes to conversations + turns tables (called by demo chat frontend)
# ══════════════════════════════════════════════════════════════════════════════
def build_log_turn():
    pii_redact_js = """
const body = $input.first().json.body || $input.first().json;
// PII redaction: remove emails, phone numbers
function redactPII(text) {
  if (!text) return '';
  return text
    .replace(/[a-zA-Z0-9._%+\\-]+@[a-zA-Z0-9.\\-]+\\.[a-zA-Z]{2,}/g, '[EMAIL]')
    .replace(/\\b(?:\\+?1[-.\\s]?)?(?:\\(?[2-9][0-9]{2}\\)?[-.\\s]?)?[2-9][0-9]{2}[-.\\s]?[0-9]{4}\\b/g, '[PHONE]')
    .replace(/\\$[0-9]{3,}(?:,[0-9]{3})*(?:\\.[0-9]{2})?/g, '[AMOUNT]');
}
return [{ json: {
  workspace_id:    body.workspace_id,
  employee_id:     body.employee_id || null,
  conversation_id: body.conversation_id || null,
  role:            body.role || 'user',
  content_redacted: redactPII(body.content),
  route:           body.route || null,
  cache_hit:       body.cache_hit || false,
  latency_ms:      body.latency_ms || null,
  outcome:         body.outcome || 'in_progress'
} }];
"""
    ensure_conversation_sql = """
-- Upsert conversation: if conversation_id provided, use it; otherwise create new
WITH ins AS (
  INSERT INTO conversations (id, workspace_id, employee_id, outcome)
  VALUES (
    COALESCE(
      CASE WHEN '{{ $json.conversation_id }}' = 'null' OR '{{ $json.conversation_id }}' = ''
           THEN NULL
           ELSE '{{ $json.conversation_id }}'::uuid END,
      gen_random_uuid()
    ),
    '{{ $json.workspace_id }}'::uuid,
    {{ $json.employee_id ? "'" + $json.employee_id + "'::uuid" : 'NULL' }},
    '{{ $json.outcome }}'
  )
  ON CONFLICT (id) DO UPDATE SET outcome = EXCLUDED.outcome
  RETURNING id
)
SELECT id FROM ins
"""
    insert_turn_sql = """
INSERT INTO turns (conversation_id, role, content_redacted, route, cache_hit, latency_ms)
VALUES (
  '{{ $json.conversation_id }}'::uuid,
  '{{ $("Prep Turn").first().json.role }}',
  '{{ $("Prep Turn").first().json.content_redacted.replace(/'/g, "''") }}',
  {{ $("Prep Turn").first().json.route ? "'" + $("Prep Turn").first().json.route + "'" : 'NULL' }},
  {{ $("Prep Turn").first().json.cache_hit }},
  {{ $("Prep Turn").first().json.latency_ms || 'NULL' }}
)
RETURNING id
"""
    nodes = [
        wh_nd('wh7', 'Webhook', 'tool-log-turn', 'POST'),
        code_nd('prep7', 'Prep Turn', pii_redact_js, 220, 0),
        pg_nd('pg7a', 'Ensure Conversation', ensure_conversation_sql, 440, 0),
        code_nd('merge7', 'Merge Conv ID', """
const conv = $('Ensure Conversation').first().json;
const prep = $('Prep Turn').first().json;
return [{ json: { ...prep, conversation_id: conv.id } }];
""", 660, 0),
        pg_nd('pg7b', 'Insert Turn', insert_turn_sql, 880, 0),
        code_nd('fmt7', 'Format', """
const turn = $input.first().json;
const conv_id = $('Merge Conv ID').first().json.conversation_id;
return [{ json: { status: 'ok', turn_id: turn.id, conversation_id: conv_id } }];
""", 1100, 0),
    ]
    nodes[0]['position'] = [0, 0]
    connections = merge_conn(
        conn('Webhook', 'Prep Turn'),
        conn('Prep Turn', 'Ensure Conversation'),
        conn('Ensure Conversation', 'Merge Conv ID'),
        conn('Merge Conv ID', 'Insert Turn'),
        conn('Insert Turn', 'Format'),
    )
    return build_workflow('tool.log-turn', nodes, connections)


# ══════════════════════════════════════════════════════════════════════════════
# Update ingest.website to emit build_events
# ══════════════════════════════════════════════════════════════════════════════
INGEST_WF_ID = 'ltWeFOzNMrZ1DxxK'

def update_ingest_website():
    """Add Emit Start Event and Emit Complete Event nodes to ingest.website."""
    emit_start_sql = """
INSERT INTO build_events (workspace_id, step, status, message, progress)
VALUES (
  '{{ $json.workspace_id }}'::uuid,
  'crawl', 'started', 'Fetching website content from {{ $json.base_url }}', 10
);
SELECT
  '{{ $json.workspace_id }}'::text AS workspace_id,
  '{{ $json.base_url }}'::text     AS base_url,
  {{ $json._start_at }}::bigint    AS _start_at
"""
    done_js = (
        "const wsId = $('Validate Input').first().json.workspace_id;\n"
        "const count = $input.all().length;\n"
        "return [{ json: { status: 'done', chunks_stored: count, workspace_id: wsId,\n"
        "  message: 'Ingestion complete — ' + count + ' chunks stored.' } }];"
    )
    emit_complete_sql = """
INSERT INTO build_events (workspace_id, step, status, message, progress)
VALUES (
  '{{ $json.workspace_id }}'::uuid,
  'ready', 'done',
  'Knowledge base ready — {{ $json.chunks_stored }} chunks stored from website.',
  100
)
RETURNING
  '{{ $json.workspace_id }}'::text AS workspace_id,
  {{ $json.chunks_stored }}        AS chunks_stored,
  'done'::text                     AS status
"""
    nodes = [
        {
            'id': 'ing-wh', 'name': 'Ingest Webhook',
            'type': 'n8n-nodes-base.webhook', 'typeVersion': 2,
            'position': [0, 0], 'webhookId': 'askops-ingest-website',
            'parameters': {'httpMethod': 'POST', 'path': 'ingest/website',
                           'responseMode': 'lastNode', 'options': {'allowedOrigins': '*'}}
        },
        {
            'id': 'ing-val', 'name': 'Validate Input',
            'type': 'n8n-nodes-base.code', 'typeVersion': 2, 'position': [220, 0],
            'onError': 'continueErrorOutput',
            'parameters': {'jsCode': (
                "const body = $input.first().json.body ?? $input.first().json;\n"
                "const wsId  = body.workspace_id;\n"
                "const rawUrl = (body.url || '').trim().replace(/\\/+$/, '');\n"
                "if (!wsId || !rawUrl) throw new Error('workspace_id and url are required');\n"
                "const url = rawUrl.startsWith('http') ? rawUrl : 'https://' + rawUrl;\n"
                "return [{ json: { workspace_id: wsId, base_url: url, _start_at: Date.now() } }];"
            )}
        },
        pg_nd('ing-evstart', 'Emit Start Event', emit_start_sql, 440, 0, 'continueErrorOutput'),
        {
            'id': 'ing-prep', 'name': 'Prep Jina URL',
            'type': 'n8n-nodes-base.code', 'typeVersion': 2, 'position': [660, 0],
            'parameters': {'jsCode': (
                "const item = $input.first().json;\n"
                "const jinaUrl = 'https://r.jina.ai/' + item.base_url;\n"
                "return [{ json: { ...item, jina_url: jinaUrl } }];"
            )}
        },
        {
            'id': 'ing-jina', 'name': 'Jina Fetch',
            'type': 'n8n-nodes-base.httpRequest', 'typeVersion': 4.2, 'position': [880, 0],
            'onError': 'continueErrorOutput',
            'parameters': {
                'method': 'GET', 'url': '={{ $json.jina_url }}',
                'sendHeaders': True,
                'headerParameters': {'parameters': [
                    {'name': 'Accept',          'value': 'text/plain'},
                    {'name': 'X-Return-Format', 'value': 'markdown'},
                ]},
                'options': {'response': {'response': {'responseFormat': 'text'}}}
            }
        },
        {
            'id': 'ing-ext', 'name': 'Extract Chunks',
            'type': 'n8n-nodes-base.code', 'typeVersion': 2, 'position': [1100, 0],
            'onError': 'continueErrorOutput',
            'parameters': {'jsCode': (
                "const item = $input.first().json;\n"
                "const content = $input.first().json.data || $input.first().json.body || '';\n"
                "const wsId = $('Validate Input').first().json.workspace_id;\n"
                "const baseUrl = $('Validate Input').first().json.base_url;\n"
                "function chunkText(text, maxLen=800, overlap=100) {\n"
                "  const paras = text.split(/\\n\\n+/).filter(p => p.trim().length > 20);\n"
                "  const chunks = [];\n"
                "  let cur = '';\n"
                "  for (const p of paras) {\n"
                "    if (cur.length + p.length + 2 > maxLen && cur.length > 0) {\n"
                "      chunks.push(cur.trim());\n"
                "      cur = cur.split('\\n\\n').slice(-1)[0] + '\\n\\n' + p;\n"
                "    } else {\n"
                "      cur = cur ? cur + '\\n\\n' + p : p;\n"
                "    }\n"
                "  }\n"
                "  if (cur.trim().length > 0) chunks.push(cur.trim());\n"
                "  return chunks;\n"
                "}\n"
                "const chunks = chunkText(content, 800, 100).slice(0, 20);\n"
                "return chunks.map((c, i) => ({ json: {\n"
                "  workspace_id: wsId, base_url: baseUrl, source_url: baseUrl,\n"
                "  chunk_index: i, content: c, total_chunks: chunks.length\n"
                "} }));"
            )}
        },
        {
            'id': 'ing-emb', 'name': 'Embed Chunk',
            'type': 'n8n-nodes-base.httpRequest', 'typeVersion': 4.2, 'position': [1320, 0],
            'onError': 'continueErrorOutput',
            'credentials': {'httpQueryAuth': {'id': 'emzXNUHrKp6cIn1O', 'name': 'AskOps Gemini'}},
            'parameters': {
                'method': 'POST',
                'url': 'https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent',
                'authentication': 'genericCredentialType', 'genericAuthType': 'httpQueryAuth',
                'sendBody': True, 'specifyBody': 'json',
                'jsonBody': '={{ JSON.stringify({"model":"models/gemini-embedding-001","content":{"parts":[{"text":$json.content}]},"taskType":"RETRIEVAL_DOCUMENT","outputDimensionality":768}) }}',
                'options': {}
            }
        },
        {
            'id': 'ing-femb', 'name': 'Format Embedding',
            'type': 'n8n-nodes-base.code', 'typeVersion': 2, 'position': [1540, 0],
            'onError': 'continueErrorOutput',
            'parameters': {'jsCode': (
                "const item = $input.first().json;\n"
                "const vals = item.embedding?.values;\n"
                "if (!vals || vals.length === 0) throw new Error('Embed error: no values from Gemini');\n"
                "const vec = '[' + vals.join(',') + ']';\n"
                "const ctx = $('Extract Chunks').first().json;\n"
                "return [{ json: {\n"
                "  workspace_id: ctx.workspace_id || item.workspace_id,\n"
                "  base_url:     ctx.base_url     || item.base_url,\n"
                "  source_url:   ctx.source_url   || item.source_url,\n"
                "  chunk_index:  ctx.chunk_index  ?? item.chunk_index ?? 0,\n"
                "  content:      ctx.content      || item.content,\n"
                "  embedding_str: vec\n"
                "} }];"
            )}
        },
        {
            'id': 'ing-pg', 'name': 'Store Chunk',
            'type': 'n8n-nodes-base.postgres', 'typeVersion': 2.5, 'position': [1760, 0],
            'onError': 'continueErrorOutput',
            'credentials': CRED,
            'parameters': {'operation': 'executeQuery', 'options': {}, 'query': (
                "WITH ins_doc AS (\n"
                "  INSERT INTO documents (workspace_id, source_type, title, source_url, content)\n"
                "  VALUES ('{{ $json.workspace_id }}'::uuid, 'website',\n"
                "    'Website: {{ $json.base_url }}', '{{ $json.source_url }}',\n"
                "    '{{ $json.content.substring(0,200).replace(/'/g, \"''\") }}...')\n"
                "  ON CONFLICT DO NOTHING RETURNING id\n"
                "),\n"
                "doc_id AS (\n"
                "  SELECT id FROM ins_doc\n"
                "  UNION ALL\n"
                "  SELECT id FROM documents\n"
                "   WHERE workspace_id = '{{ $json.workspace_id }}'::uuid\n"
                "     AND source_url = '{{ $json.source_url }}' AND source_type = 'website'\n"
                "   LIMIT 1\n"
                ")\n"
                "INSERT INTO chunks (document_id, workspace_id, chunk_index, content, embedding)\n"
                "VALUES ((SELECT id FROM doc_id LIMIT 1), '{{ $json.workspace_id }}'::uuid,\n"
                "  {{ $json.chunk_index }}, '{{ $json.content.replace(/'/g, \"''\") }}',\n"
                "  '{{ $json.embedding_str }}'::vector)\n"
                "ON CONFLICT DO NOTHING RETURNING id::text"
            )}
        },
        code_nd('ing-done', 'Done', done_js, 1980, 0),
        pg_nd('ing-evend', 'Emit Complete Event', emit_complete_sql, 2200, 0),
        {
            'id': 'ing-err', 'name': 'Ingest Error',
            'type': 'n8n-nodes-base.code', 'typeVersion': 2, 'position': [660, 220],
            'parameters': {'jsCode': (
                "const e = $input.first().json;\n"
                "const msg = e.message || e.error?.description || 'Ingest failed';\n"
                "return [{ json: { status: 'error', error: msg } }];"
            )}
        },
    ]
    connections = {
        'Ingest Webhook':    {'main': [[{'node': 'Validate Input',    'type': 'main', 'index': 0}]]},
        'Validate Input':    {'main': [[{'node': 'Emit Start Event',  'type': 'main', 'index': 0}],
                                       [{'node': 'Ingest Error',      'type': 'main', 'index': 0}]]},
        'Emit Start Event':  {'main': [[{'node': 'Prep Jina URL',     'type': 'main', 'index': 0}],
                                       [{'node': 'Ingest Error',      'type': 'main', 'index': 0}]]},
        'Prep Jina URL':     {'main': [[{'node': 'Jina Fetch',        'type': 'main', 'index': 0}]]},
        'Jina Fetch':        {'main': [[{'node': 'Extract Chunks',    'type': 'main', 'index': 0}],
                                       [{'node': 'Ingest Error',      'type': 'main', 'index': 0}]]},
        'Extract Chunks':    {'main': [[{'node': 'Embed Chunk',       'type': 'main', 'index': 0}],
                                       [{'node': 'Ingest Error',      'type': 'main', 'index': 0}]]},
        'Embed Chunk':       {'main': [[{'node': 'Format Embedding',  'type': 'main', 'index': 0}],
                                       [{'node': 'Ingest Error',      'type': 'main', 'index': 0}]]},
        'Format Embedding':  {'main': [[{'node': 'Store Chunk',       'type': 'main', 'index': 0}],
                                       [{'node': 'Ingest Error',      'type': 'main', 'index': 0}]]},
        'Store Chunk':       {'main': [[{'node': 'Done',              'type': 'main', 'index': 0}],
                                       [{'node': 'Ingest Error',      'type': 'main', 'index': 0}]]},
        'Done':              {'main': [[{'node': 'Emit Complete Event','type': 'main', 'index': 0}]]},
    }
    wf_body = {
        'name': 'ingest.website',
        'nodes': nodes, 'connections': connections,
        'settings': {'executionOrder': 'v1', 'callerPolicy': 'workflowsFromSameOwner',
                     'availableInMCP': False}
    }
    api('PUT', f'/api/v1/workflows/{INGEST_WF_ID}', wf_body)
    api('POST', f'/api/v1/workflows/{INGEST_WF_ID}/activate')
    print(f'  Updated  : ingest.website (id={INGEST_WF_ID}) with build_events')


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    workflows = [
        ('api.build-status',    build_build_status()),
        ('api.set-persona',     build_set_persona()),
        ('api.metrics',         build_metrics()),
        ('api.tool-trace',      build_tool_trace()),
        ('api.setup-workspace', build_setup_workspace()),
        ('tool.router',         build_router()),
        ('tool.log-turn',       build_log_turn()),
    ]
    for name, wf in workflows:
        print(f'Deploying {name}...')
        try:
            wf_id = deploy_workflow(wf, name)
            print(f'  → {wf_id}')
        except Exception as e:
            print(f'  ERROR: {e}')
        time.sleep(0.3)

    print('\nUpdating ingest.website with build_events...')
    try:
        update_ingest_website()
    except Exception as e:
        print(f'  ERROR updating ingest.website: {e}')

    print('\nDone.')
