#!/usr/bin/env python3
"""
Build the unified mcp.ask-ops workflow (qhmoB9pZdLav12FB) with all 11 tool branches
plus 2 HTML webhook branches for the PTO email approval loop,
plus Branch 14 (search_kb: Gemini embed → semantic cache → match_chunks → Groq LLM).
Each tool branch: Webhook N → Normalize Input N → Get Identity N → [tool logic]
                 → Prepare Log N → Log Tool Call N → Return Output N
                                 ↘ Handle Error N → Log Error N → Return Error N
HTML branches (12, 13): Webhook → Postgres → Build HTML → Respond to Webhook
Branch 14 (search_kb): built manually due to IF nodes and HTTP requests
"""
import json, re, urllib.request, urllib.error

BASE      = 'http://localhost:5678'
API_KEY   = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIyZjIyYTczYy04ZGUyLTQyZTMtYTg3ZS01OTBjMGYyMjIyYjciLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwiaWF0IjoxNzkzODU5MzQ2fQ.eAmo5vLR78e7fRQ7rbo3vGjV6r_cdMrM_FYavc4DBII'
TARGET_ID = 'qhmoB9pZdLav12FB'
CRED      = {'postgres': {'id': '4DuuvBbohpSo7Mr0', 'name': 'AskOps Postgres'}}
SMTP_CRED = {'smtp': {'id': '8vmLF66qqfuLZu5m', 'name': 'AskOps Gmail SMTP'}}
GROQ_CRED   = {'httpHeaderAuth': {'id': 'AxtE0phNFpQkBki9', 'name': 'AskOps Groq'}}
GEMINI_CRED = {'httpQueryAuth':  {'id': 'emzXNUHrKp6cIn1O', 'name': 'AskOps Gemini'}}
GMAIL_FROM = 'g.adarsh043@gmail.com'

Y_STEP = 500   # vertical gap between branches
X_STEP = 220   # horizontal gap between nodes


# ── API helper ─────────────────────────────────────────────────────────────────
def api(method, path, body=None):
    headers = {'X-N8N-API-KEY': API_KEY, 'Content-Type': 'application/json'}
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(f'{BASE}{path}', data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'n8n {method} {path} → {e.code}: {e.read().decode()[:300]}')


# ── Node constructors ──────────────────────────────────────────────────────────
def code_nd(nid, name, js, x, y, on_error=None):
    n = {'id': nid, 'name': name, 'type': 'n8n-nodes-base.code', 'typeVersion': 2,
         'position': [x, y], 'parameters': {'jsCode': js.strip()}}
    if on_error: n['onError'] = on_error
    return n

def pg_nd(nid, name, sql, x, y, on_error=None):
    n = {'id': nid, 'name': name, 'type': 'n8n-nodes-base.postgres', 'typeVersion': 2.5,
         'position': [x, y], 'credentials': CRED,
         'parameters': {'operation': 'executeQuery', 'query': sql.strip(), 'options': {}}}
    if on_error: n['onError'] = on_error
    return n

def fmt_nd(js, x, y):
    return code_nd('fmt', 'Format Output', js, x, y)


# ── String helpers ─────────────────────────────────────────────────────────────
def suffix_js(js, n):
    """$('Node Name') → $('Node Name N') in JS/SQL strings."""
    return re.sub(r"\$\('([^']+)'\)", lambda m: f"$('{m.group(1)} {n}')", js)


# ── Footer JS/SQL templates (use __N__ as placeholder, replaced by _t()) ──────
_PREP_LOG_JS = """
const d = $input.first().json;
const id = $('Get Identity __N__').first().json;
const start = $('Normalize Input __N__').first().json._start_at;
const esc = s => s == null ? null : String(s).replace(/'/g, "''");
return [{ json: {
  ...d._out,
  _lws:  id.workspace_id,
  _lemp: id.employee_id ?? null,
  _ltool: d._tool_name,
  _lin:  esc(JSON.stringify(d._in  ?? {})),
  _lout: d._out != null ? esc(JSON.stringify(d._out)) : null,
  _lst:  d._status,
  _lerr: esc(d._error) ?? null,
  _llat: Date.now() - start
}}];
"""

_LOG_SQL = """INSERT INTO tool_calls
  (workspace_id, employee_id, tool_name, input, output, status, error, latency_ms)
VALUES (
  '{{ $json._lws }}'::uuid,
  {{ $json._lemp ? "'" + $json._lemp + "'" : 'NULL' }}::uuid,
  '{{ $json._ltool }}',
  '{{ $json._lin }}'::jsonb,
  {{ $json._lout ? "'" + $json._lout + "'" : 'NULL' }}::jsonb,
  '{{ $json._lst }}',
  {{ $json._lerr ? "'" + $json._lerr + "'" : 'NULL' }},
  {{ $json._llat }}::integer
)
RETURNING id"""

_ERR_HANDLE_JS = r"""
const item = $input.first();
const rawErr = item.json?.error;
const msg = (item.json?.message
         || (typeof rawErr === 'string' ? rawErr : rawErr?.description)
         || 'Tool error').replace(/\s*\[line \d+\]$/, '');
let status = 'error';
let friendly = msg;
const m = msg.match(/^([A-Z_]+):\s*(.*)/s);
const code = m?.[1];
const rest = m?.[2] || msg;
const codeMap = {
  ACCESS_DENIED:        ['denied', 'You do not have permission to perform this action.'],
  INSUFFICIENT_BALANCE: ['error',  'Insufficient PTO balance for this request.'],
  NOT_FOUND:            ['error',  'The requested resource was not found.'],
  ALREADY_DECIDED:      ['error',  'This request has already been decided.'],
  INVALID_LINK:         ['error',  'This approval link is invalid or has expired.'],
};
if (code && codeMap[code]) {
  [status, friendly] = codeMap[code];
} else if (code) {
  friendly = rest;
}
const id = $('Get Identity __N__').first().json;
const start = $('Normalize Input __N__').first().json._start_at;
const esc = s => s == null ? null : String(s).replace(/'/g, "''");
return [{ json: {
  error: friendly,
  _lws:   id.workspace_id,
  _lemp:  id.employee_id ?? null,
  _ltool: $('Normalize Input __N__').first().json._tool,
  _lin:   esc(JSON.stringify({})),
  _lout:  null,
  _lst:   status,
  _lerr:  esc(friendly),
  _llat:  Date.now() - start
}}];
"""

def _t(template, n):
    return template.replace('__N__', str(n))


# ── Branch builder ─────────────────────────────────────────────────────────────
def build_branch(bi, branch):
    """
    bi     : 0-based branch index (determines Y position)
    branch : dict with keys name, path, nodes, conns, and optional normalize_js
    Returns (nodes_list, connections_dict) with all names suffixed.
    """
    n   = bi + 1          # 1-based suffix
    bx  = 0
    by  = bi * Y_STEP

    normalize_js = branch.get('normalize_js') or (
        f'const item = $input.first().json;\n'
        f'const body = item.body ?? item;\n'
        f'return [{{ json: {{ ...body, _tool: "{branch["name"]}", _start_at: Date.now() }} }}];'
    )

    # ── Header nodes ──
    wh = {
        'id': f'wh-{n}', 'name': f'Webhook {n}',
        'type': 'n8n-nodes-base.webhook', 'typeVersion': 2,
        'position': [bx, by + 165],
        'webhookId': f'askops-{branch["path"]}',
        'parameters': {'httpMethod': 'POST', 'path': branch['path'],
                       'responseMode': 'lastNode', 'options': {}}
    }
    nm = code_nd(f'nm-{n}', f'Normalize Input {n}', normalize_js, bx + 220, by + 110)
    gi = pg_nd(f'gi-{n}', f'Get Identity {n}', 'SELECT * FROM current_identity()',
               bx + 440, by + 110)

    # ── Suffix tool-specific nodes ──
    tool_sfx = []
    name_map = {}
    for nd in branch['nodes']:
        orig = nd['name']
        new_name = f'{orig} {n}'
        name_map[orig] = new_name
        snd = json.loads(json.dumps(nd))
        snd['name'] = new_name
        snd['id']   = f'{snd["id"]}-{n}'
        snd['position'] = [snd['position'][0] + bx, snd['position'][1] + by]
        if 'jsCode' in snd.get('parameters', {}):
            snd['parameters']['jsCode'] = suffix_js(snd['parameters']['jsCode'], n)
        if 'query' in snd.get('parameters', {}):
            snd['parameters']['query'] = suffix_js(snd['parameters']['query'], n)
        # Suffix expression fields on emailSend node
        for param_key in ('toEmail', 'subject', 'html', 'fromEmail'):
            if param_key in snd.get('parameters', {}):
                val = snd['parameters'][param_key]
                if isinstance(val, str):
                    snd['parameters'][param_key] = suffix_js(val, n)
        tool_sfx.append(snd)

    # ── Footer nodes ──
    max_x = max(nd['position'][0] for nd in tool_sfx) if tool_sfx else bx + 440
    fx = max_x + X_STEP
    ey = by + 330

    pl  = code_nd(f'pl-{n}',   f'Prepare Log {n}',   _t(_PREP_LOG_JS, n), fx,         by + 110)
    lg  = pg_nd(f'lg-{n}',     f'Log Tool Call {n}',  _LOG_SQL,            fx + X_STEP, by + 110)
    ro  = code_nd(f'ro-{n}',   f'Return Output {n}',
                  f"const d = $('Prepare Log {n}').first().json;\n"
                  f"const clean = Object.fromEntries(Object.entries(d).filter(([k]) => !k.startsWith('_l')));\n"
                  f"return [{{ json: clean }}];",
                  fx + X_STEP * 2, by + 110)

    he  = code_nd(f'he-{n}',   f'Handle Error {n}',  _t(_ERR_HANDLE_JS, n), bx + 220, ey)
    le  = pg_nd(f'le-{n}',     f'Log Error {n}',      _LOG_SQL,              bx + 440, ey)
    re_ = code_nd(f're-{n}',   f'Return Error {n}',
                  f"const d = $('Handle Error {n}').first().json;\n"
                  f"return [{{ json: {{ error: d.error }} }}];",
                  bx + 660, ey)

    nodes = [wh, nm, gi] + tool_sfx + [pl, lg, ro, he, le, re_]

    # ── Connections ──
    conns = {
        f'Webhook {n}':        {'main': [[{'node': f'Normalize Input {n}', 'type': 'main', 'index': 0}]]},
        f'Normalize Input {n}':{'main': [[{'node': f'Get Identity {n}',    'type': 'main', 'index': 0}]]},
        f'Get Identity {n}':   {'main': [[{'node': tool_sfx[0]['name'],    'type': 'main', 'index': 0}]]},
        f'Prepare Log {n}':    {'main': [[{'node': f'Log Tool Call {n}',   'type': 'main', 'index': 0}]]},
        f'Log Tool Call {n}':  {'main': [[{'node': f'Return Output {n}',   'type': 'main', 'index': 0}]]},
        f'Handle Error {n}':   {'main': [[{'node': f'Log Error {n}',       'type': 'main', 'index': 0}]]},
        f'Log Error {n}':      {'main': [[{'node': f'Return Error {n}',    'type': 'main', 'index': 0}]]},
    }
    for src, edges in branch['conns'].items():
        new_src = name_map.get(src, src + f' {n}')
        new_edges = []
        for port_links in edges['main']:
            new_edges.append([
                {'node': name_map.get(lk['node'], lk['node'] + f' {n}'),
                 'type': 'main', 'index': 0}
                for lk in port_links
            ])
        conns[new_src] = {'main': new_edges}

    return nodes, conns


# ── HTML webhook branch builder ────────────────────────────────────────────────
def respond_node(nid, name, x, y):
    """respondToWebhook node that sends HTML from $json.html."""
    return {
        'id': nid, 'name': name,
        'type': 'n8n-nodes-base.respondToWebhook', 'typeVersion': 1.1,
        'position': [x, y],
        'parameters': {
            'respondWith': 'text',
            'responseBody': '={{ $json.html }}',
            'options': {
                'responseCode': 200,
                'responseHeaders': {
                    'entries': [{'name': 'Content-Type', 'value': 'text/html; charset=utf-8'}]
                }
            }
        }
    }


def build_html_branch(bi, branch_id, http_method, path, main_node, success_js, error_js):
    """
    Simple GET/POST webhook branch returning HTML. No identity lookup or logging.
    Used for the email approval pages (pto-review, pto-decide).
    """
    bx = 0
    base_y = bi * Y_STEP

    wh = {
        'id': f'wh-h{branch_id}', 'name': f'Webhook {branch_id}',
        'type': 'n8n-nodes-base.webhook', 'typeVersion': 2,
        'position': [bx, base_y + 110],
        'webhookId': f'askops-{path}',
        'parameters': {
            'httpMethod': http_method, 'path': path,
            'responseMode': 'responseNode', 'options': {}
        }
    }

    main_nd = json.loads(json.dumps(main_node))
    main_nd['id'] += f'-{branch_id}'
    main_nd['name'] += f' {branch_id}'
    main_nd['position'] = [bx + 220, base_y + 110]
    main_nd['onError'] = 'continueErrorOutput'

    suc      = code_nd(f'suc-h{branch_id}', f'Build Success HTML {branch_id}', success_js, bx + 440, base_y + 110)
    err_html = code_nd(f'err-h{branch_id}', f'Build Error HTML {branch_id}',   error_js,   bx + 220, base_y + 330)
    suc_resp = respond_node(f'rsp-s{branch_id}', f'Respond Success {branch_id}', bx + 660, base_y + 110)
    err_resp = respond_node(f'rsp-e{branch_id}', f'Respond Error {branch_id}',   bx + 440, base_y + 330)

    nodes = [wh, main_nd, suc, err_html, suc_resp, err_resp]
    mn = main_nd['name']
    conns = {
        f'Webhook {branch_id}':              {'main': [[{'node': mn,                               'type': 'main', 'index': 0}]]},
        mn:                                  {'main': [[{'node': f'Build Success HTML {branch_id}', 'type': 'main', 'index': 0}],
                                                        [{'node': f'Build Error HTML {branch_id}',  'type': 'main', 'index': 0}]]},
        f'Build Success HTML {branch_id}':   {'main': [[{'node': f'Respond Success {branch_id}',    'type': 'main', 'index': 0}]]},
        f'Build Error HTML {branch_id}':     {'main': [[{'node': f'Respond Error {branch_id}',      'type': 'main', 'index': 0}]]},
    }
    return nodes, conns


# ══════════════════════════════════════════════════════════════════════════════
# Branch definitions (11 tools)
# ══════════════════════════════════════════════════════════════════════════════

# ── 1. get_my_profile ─────────────────────────────────────────────────────────
GMP_SQL = """SELECT e.full_name, e.title, e.department, m.full_name AS manager_name,
       e.employee_code, e.hire_date::text, e.pto_balance_days::integer AS pto_balance_days
FROM employees e
LEFT JOIN employees m ON m.id = e.manager_id
WHERE e.id = '{{ $json.employee_id }}'::uuid"""

GMP_FMT = """
const r = $input.first().json;
const id = $('Get Identity').first().json;
const out = { name: r.full_name, title: r.title, department: r.department,
              manager: r.manager_name, employee_code: r.employee_code,
              hire_date: r.hire_date, pto_balance_days: r.pto_balance_days };
return [{ json: { ...out, _out: out, _tool_name: 'get_my_profile', _in: {}, _status: 'success', _error: null } }];
"""

BRANCH_1 = {
    'name': 'get_my_profile', 'path': 'tool-get-my-profile',
    'nodes': [
        pg_nd('pg-gmp', 'Get Profile', GMP_SQL, 660, 0, 'continueErrorOutput'),
        fmt_nd(GMP_FMT, 880, 0),
    ],
    'conns': {
        'Get Profile':   {'main': [[{'node': 'Format Output', 'type': 'main', 'index': 0}],
                                    [{'node': 'Handle Error',  'type': 'main', 'index': 0}]]},
        'Format Output': {'main': [[{'node': 'Prepare Log',   'type': 'main', 'index': 0}]]},
    }
}

# ── 2. get_pto_balance ────────────────────────────────────────────────────────
GPB_SQL = "SELECT pto_balance_days::text AS balance_days, full_name FROM employees WHERE id = '{{ $json.employee_id }}'::uuid"
GPB_FMT = """
const r = $input.first().json;
const out = { balance_days: r.balance_days, employee_name: r.full_name };
return [{ json: { ...out, _out: out, _tool_name: 'get_pto_balance', _in: {}, _status: 'success', _error: null } }];
"""

BRANCH_2 = {
    'name': 'get_pto_balance', 'path': 'tool-get-pto-balance',
    'nodes': [
        pg_nd('pg-gpb', 'Get Balance', GPB_SQL, 660, 0, 'continueErrorOutput'),
        fmt_nd(GPB_FMT, 880, 0),
    ],
    'conns': {
        'Get Balance':   {'main': [[{'node': 'Format Output', 'type': 'main', 'index': 0}],
                                    [{'node': 'Handle Error',  'type': 'main', 'index': 0}]]},
        'Format Output': {'main': [[{'node': 'Prepare Log',   'type': 'main', 'index': 0}]]},
    }
}

# ── 3. get_my_requests ────────────────────────────────────────────────────────
GMR_SQL = """SELECT COALESCE(json_agg(r), '[]'::json) AS requests
FROM (
  SELECT code, start_date::text, end_date::text, days::integer AS days,
         status, reason, decided_at::text, decision_note
  FROM pto_requests
  WHERE workspace_id = '{{ $json.workspace_id }}'::uuid
    AND employee_id  = '{{ $json.employee_id }}'::uuid
  ORDER BY start_date DESC, id DESC LIMIT 20
) r"""

GMR_FMT = """
const r = $input.first().json;
const requests = Array.isArray(r.requests) ? r.requests : (r.requests ? JSON.parse(r.requests) : []);
const out = { requests };
return [{ json: { ...out, _out: out, _tool_name: 'get_my_requests', _in: {}, _status: 'success', _error: null } }];
"""

BRANCH_3 = {
    'name': 'get_my_requests', 'path': 'tool-get-my-requests',
    'nodes': [
        pg_nd('pg-gmr', 'Get Requests', GMR_SQL, 660, 0, 'continueErrorOutput'),
        fmt_nd(GMR_FMT, 880, 0),
    ],
    'conns': {
        'Get Requests':  {'main': [[{'node': 'Format Output', 'type': 'main', 'index': 0}],
                                    [{'node': 'Handle Error',  'type': 'main', 'index': 0}]]},
        'Format Output': {'main': [[{'node': 'Prepare Log',   'type': 'main', 'index': 0}]]},
    }
}

# ── 4. get_compensation ───────────────────────────────────────────────────────
GC_SQL = """SELECT base_salary::text AS salary, currency
FROM get_compensation(
  (SELECT employee_id FROM current_identity()),
  CASE
    WHEN '{{ $('Normalize Input').first().json.employee_name_or_code }}' ~ '^EMP-'
    THEN (SELECT id FROM employees
          WHERE employee_code = '{{ $('Normalize Input').first().json.employee_name_or_code }}'
            AND workspace_id  = '{{ $json.workspace_id }}'::uuid)
    ELSE (SELECT id FROM employees
          WHERE lower(full_name) = lower('{{ $('Normalize Input').first().json.employee_name_or_code }}')
            AND workspace_id  = '{{ $json.workspace_id }}'::uuid)
  END
)"""

GC_FMT = """
const r = $input.first().json;
const body = $('Normalize Input').first().json;
const out = { salary: r.salary, currency: r.currency, employee: body.employee_name_or_code };
return [{ json: { ...out, _out: out, _tool_name: 'get_compensation',
  _in: { employee_name_or_code: body.employee_name_or_code }, _status: 'success', _error: null } }];
"""

BRANCH_4 = {
    'name': 'get_compensation', 'path': 'tool-get-compensation',
    'nodes': [
        pg_nd('pg-gc', 'Get Compensation', GC_SQL, 660, 0, 'continueErrorOutput'),
        fmt_nd(GC_FMT, 880, 0),
    ],
    'conns': {
        'Get Compensation': {'main': [[{'node': 'Format Output', 'type': 'main', 'index': 0}],
                                       [{'node': 'Handle Error',  'type': 'main', 'index': 0}]]},
        'Format Output':    {'main': [[{'node': 'Prepare Log',   'type': 'main', 'index': 0}]]},
    }
}

# ── 5. create_ticket ──────────────────────────────────────────────────────────
CT_PREP_JS = """
const id = $('Get Identity').first().json;
const body = $('Normalize Input').first().json;
const esc = s => s == null ? null : String(s).replace(/'/g, "''");
const validCat = ['it','hr','facilities','other'];
const validPri = ['low','normal','high','urgent'];
const cat = (body.category || 'other').toLowerCase();
const pri = (body.priority || 'normal').toLowerCase();
return [{ json: {
  ...id,
  category: validCat.includes(cat) ? cat : 'other',
  title:    esc(body.title || 'Support Request'),
  desc:     esc(body.description || ''),
  priority: validPri.includes(pri) ? pri : 'normal',
}}];
"""

CT_SQL = """INSERT INTO tickets
  (workspace_id, employee_id, category, title, description, priority)
VALUES (
  '{{ $json.workspace_id }}'::uuid,
  '{{ $json.employee_id }}'::uuid,
  '{{ $json.category }}',
  '{{ $json.title }}',
  '{{ $json.desc }}',
  '{{ $json.priority }}'
)
RETURNING code, status, assigned_team"""

CT_FMT = """
const r = $input.first().json;
const ctx = $('Prep Ticket').first().json;
const body = $('Normalize Input').first().json;
const out = { code: r.code, status: r.status, assigned_team: r.assigned_team,
              category: ctx.category, priority: ctx.priority };
return [{ json: { ...out, _out: out, _tool_name: 'create_ticket',
  _in: { category: body.category, title: body.title, description: body.description, priority: body.priority },
  _status: 'success', _error: null } }];
"""

BRANCH_5 = {
    'name': 'create_ticket', 'path': 'tool-create-ticket',
    'nodes': [
        code_nd('ct-prep', 'Prep Ticket',    CT_PREP_JS, 660,  0, 'continueErrorOutput'),
        pg_nd('pg-ct',     'Insert Ticket',  CT_SQL,     880,  0, 'continueErrorOutput'),
        fmt_nd(CT_FMT, 1100, 0),
    ],
    'conns': {
        'Prep Ticket':   {'main': [[{'node': 'Insert Ticket', 'type': 'main', 'index': 0}],
                                    [{'node': 'Handle Error',  'type': 'main', 'index': 0}]]},
        'Insert Ticket': {'main': [[{'node': 'Format Output', 'type': 'main', 'index': 0}],
                                    [{'node': 'Handle Error',  'type': 'main', 'index': 0}]]},
        'Format Output': {'main': [[{'node': 'Prepare Log',   'type': 'main', 'index': 0}]]},
    }
}

# ── 6. get_ticket_status ──────────────────────────────────────────────────────
GTS_SQL = """SELECT COALESCE(json_agg(t ORDER BY t.created_at DESC), '[]'::json) AS tickets
FROM (
  SELECT code, category, title, priority, status, assigned_team,
         created_at::text, updated_at::text
  FROM tickets t
  WHERE workspace_id = '{{ $json.workspace_id }}'::uuid
    AND ('' = '{{ $json.code }}' OR code = '{{ $json.code }}')
    AND ('{{ $json.access_role }}' = 'hr' OR employee_id = '{{ $json.employee_id }}'::uuid)
  ORDER BY created_at DESC LIMIT 20
) t"""

GTS_FMT = """
const r = $input.first().json;
const body = $('Normalize Input').first().json;
const tickets = Array.isArray(r.tickets) ? r.tickets : (r.tickets ? JSON.parse(r.tickets) : []);
const out = { tickets };
return [{ json: { ...out, _out: out, _tool_name: 'get_ticket_status',
  _in: { code: body.code }, _status: 'success', _error: null } }];
"""

BRANCH_6 = {
    'name': 'get_ticket_status', 'path': 'tool-get-ticket-status',
    'nodes': [
        pg_nd('pg-gts', 'Get Tickets', GTS_SQL, 660, 0, 'continueErrorOutput'),
        fmt_nd(GTS_FMT, 880, 0),
    ],
    'conns': {
        'Get Tickets':   {'main': [[{'node': 'Format Output', 'type': 'main', 'index': 0}],
                                    [{'node': 'Handle Error',  'type': 'main', 'index': 0}]]},
        'Format Output': {'main': [[{'node': 'Prepare Log',   'type': 'main', 'index': 0}]]},
    }
}

# ── 7. request_pto (with email approval) ──────────────────────────────────────
RPTO_VAL_JS = r"""
const id = $('Get Identity').first().json;
const body = $('Normalize Input').first().json;
const esc = s => s == null ? null : String(s).replace(/'/g, "''");
const start = body.start_date;
const end   = body.end_date;
if (!start || !end) throw new Error('INVALID_DATES: start_date and end_date are required (YYYY-MM-DD format).');
if (!/^\d{4}-\d{2}-\d{2}$/.test(start) || !/^\d{4}-\d{2}-\d{2}$/.test(end))
  throw new Error('INVALID_DATES: dates must be in YYYY-MM-DD format.');
if (start >= end) throw new Error('INVALID_DATES: end_date must be after start_date.');
return [{ json: { ...id, start_date: start, end_date: end, reason: esc(body.reason || 'Vacation') } }];
"""

RPTO_CHECK_SQL = """SELECT
  (SELECT pto_balance_days FROM employees WHERE id = '{{ $json.employee_id }}'::uuid) AS balance,
  (SELECT COUNT(*) FROM generate_series(
      '{{ $json.start_date }}'::date,
      '{{ $json.end_date }}'::date - interval '1 day',
      '1 day'::interval) d
   WHERE EXTRACT(DOW FROM d) NOT IN (0,6)) AS business_days,
  (SELECT COUNT(*) FROM pto_requests
   WHERE employee_id = '{{ $json.employee_id }}'::uuid
     AND status IN ('pending','approved')
     AND start_date < '{{ $json.end_date }}'::date
     AND end_date > '{{ $json.start_date }}'::date) AS overlaps"""

RPTO_GUARD_JS = """
const r = $input.first().json;
const ctx = $('Validate Dates').first().json;
const days = parseFloat(r.business_days);
const balance = parseFloat(r.balance);
const overlaps = parseInt(r.overlaps);
if (days === 0) throw new Error('INVALID_DATES: The date range contains no business days (weekdays only).');
if (overlaps > 0) throw new Error('INVALID_DATES: You already have an approved or pending request overlapping those dates.');
if (days > balance) throw new Error('INSUFFICIENT_BALANCE: You requested ' + days + ' days but only have ' + balance + ' available.');
return [{ json: { ...ctx, requested_days: days, balance_days: balance } }];
"""

RPTO_INS_SQL = """WITH tok AS (SELECT gen_random_bytes(32) AS raw),
ins AS (
  INSERT INTO pto_requests
    (workspace_id, employee_id, start_date, end_date, days, reason,
     status, approval_token_hash, token_expires_at)
  SELECT '{{ $json.workspace_id }}'::uuid, '{{ $json.employee_id }}'::uuid,
    '{{ $json.start_date }}'::date, '{{ $json.end_date }}'::date,
    {{ $json.requested_days }}, '{{ $json.reason }}', 'pending',
    encode(digest(raw, 'sha256'), 'hex'), now() + interval '48 hours'
  FROM tok
  RETURNING code, days::text AS days, status
)
SELECT
  ins.code, ins.days, ins.status,
  encode(tok.raw, 'hex') AS token_raw,
  w.demo_manager_email, w.company_name, w.webhook_url,
  e.full_name AS employee_name
FROM ins
CROSS JOIN tok
JOIN workspaces w ON w.id = '{{ $json.workspace_id }}'::uuid
JOIN employees e ON e.id = '{{ $json.employee_id }}'::uuid"""

BUILD_EMAIL_JS = """
const r = $input.first().json;
const ctx = $('Guard Check').first().json;
const baseUrl = r.webhook_url || 'http://localhost:5678';
const reviewUrl = baseUrl + '/webhook/pto-review?token=' + r.token_raw;
const html = `<!DOCTYPE html>
<html><body style="font-family:sans-serif;max-width:600px;margin:40px auto;padding:0 20px">
<h2 style="color:#1a56db">PTO Request: Approval Needed</h2>
<p>Hi Manager,</p>
<p><strong>${r.employee_name}</strong> has requested time off:</p>
<table style="border-collapse:collapse;width:100%;margin:20px 0">
  <tr><td style="padding:8px;border:1px solid #ddd;background:#f9f9f9"><strong>Dates</strong></td>
      <td style="padding:8px;border:1px solid #ddd">${ctx.start_date} → ${ctx.end_date}</td></tr>
  <tr><td style="padding:8px;border:1px solid #ddd;background:#f9f9f9"><strong>Days</strong></td>
      <td style="padding:8px;border:1px solid #ddd">${r.days}</td></tr>
  <tr><td style="padding:8px;border:1px solid #ddd;background:#f9f9f9"><strong>Reason</strong></td>
      <td style="padding:8px;border:1px solid #ddd">${ctx.reason}</td></tr>
  <tr><td style="padding:8px;border:1px solid #ddd;background:#f9f9f9"><strong>Reference</strong></td>
      <td style="padding:8px;border:1px solid #ddd">${r.code}</td></tr>
</table>
<a href="${reviewUrl}" style="display:inline-block;padding:12px 28px;background:#1a56db;color:#fff;text-decoration:none;border-radius:6px;font-size:16px">Review Request</a>
<p style="color:#888;font-size:12px;margin-top:32px">This link expires in 48 hours. Powered by AskOps — ${r.company_name}</p>
</body></html>`;
return [{ json: {
  email_to: r.demo_manager_email,
  email_subject: '[AskOps] PTO request from ' + r.employee_name + ': ' + r.code,
  email_html: html,
  code: r.code, days: r.days, status: r.status,
  start_date: ctx.start_date, end_date: ctx.end_date
}}];
"""

RPTO_FMT = """
const r = $('Build Email Content').first().json;
const body = $('Normalize Input').first().json;
const out = { code: r.code, days: r.days, status: r.status,
              start_date: r.start_date, end_date: r.end_date,
              message: 'PTO request submitted. Your manager will receive an approval email shortly.' };
return [{ json: { ...out, _out: out, _tool_name: 'request_pto',
  _in: { start_date: body.start_date, end_date: body.end_date, reason: body.reason },
  _status: 'success', _error: null } }];
"""

BRANCH_7 = {
    'name': 'request_pto', 'path': 'tool-request-pto',
    'nodes': [
        code_nd('rpto-val',   'Validate Dates',     RPTO_VAL_JS,    660,  0, 'continueErrorOutput'),
        pg_nd('rpto-check',   'Check Balance',       RPTO_CHECK_SQL, 880,  0, 'continueErrorOutput'),
        code_nd('rpto-guard', 'Guard Check',         RPTO_GUARD_JS,  1100, 0, 'continueErrorOutput'),
        pg_nd('rpto-ins',     'Insert PTO',          RPTO_INS_SQL,   1320, 0, 'continueErrorOutput'),
        code_nd('rpto-email', 'Build Email Content', BUILD_EMAIL_JS, 1540, 0, 'continueErrorOutput'),
        {
            'id': 'rpto-send', 'name': 'Send Approval Email',
            'type': 'n8n-nodes-base.emailSend', 'typeVersion': 2.1,
            'position': [1760, 0],
            'parameters': {
                'fromEmail': GMAIL_FROM,
                'toEmail': '={{ $json.email_to }}',
                'subject': '={{ $json.email_subject }}',
                'emailFormat': 'html',
                'html': '={{ $json.email_html }}',
                'options': {}
            },
            'credentials': SMTP_CRED,
            'onError': 'continueErrorOutput'
        },
        fmt_nd(RPTO_FMT, 1980, 0),
    ],
    'conns': {
        'Validate Dates':     {'main': [[{'node': 'Check Balance',      'type': 'main', 'index': 0}],
                                         [{'node': 'Handle Error',       'type': 'main', 'index': 0}]]},
        'Check Balance':      {'main': [[{'node': 'Guard Check',         'type': 'main', 'index': 0}],
                                         [{'node': 'Handle Error',       'type': 'main', 'index': 0}]]},
        'Guard Check':        {'main': [[{'node': 'Insert PTO',          'type': 'main', 'index': 0}],
                                         [{'node': 'Handle Error',       'type': 'main', 'index': 0}]]},
        'Insert PTO':         {'main': [[{'node': 'Build Email Content', 'type': 'main', 'index': 0}],
                                         [{'node': 'Handle Error',       'type': 'main', 'index': 0}]]},
        'Build Email Content':{'main': [[{'node': 'Send Approval Email', 'type': 'main', 'index': 0}],
                                         [{'node': 'Handle Error',       'type': 'main', 'index': 0}]]},
        # best-effort: email success AND error both go to Format Output
        'Send Approval Email':{'main': [[{'node': 'Format Output',       'type': 'main', 'index': 0}],
                                         [{'node': 'Format Output',       'type': 'main', 'index': 0}]]},
        'Format Output':      {'main': [[{'node': 'Prepare Log',         'type': 'main', 'index': 0}]]},
    }
}

# ── 8. list_pending_pto ───────────────────────────────────────────────────────
LPP_SQL = """DO $$ BEGIN
  IF (SELECT access_role FROM current_identity()) <> 'hr' THEN
    RAISE EXCEPTION 'ACCESS_DENIED: Only HR can list pending PTO requests.';
  END IF;
END $$;
SELECT COALESCE(json_agg(r), '[]'::json) AS requests
FROM (
  SELECT pr.code, e.full_name AS employee, e.employee_code,
         pr.start_date::text, pr.end_date::text, pr.days::integer AS days,
         pr.reason, pr.created_at::text
  FROM pto_requests pr
  JOIN employees e ON e.id = pr.employee_id
  WHERE pr.workspace_id = (SELECT workspace_id FROM current_identity())
    AND pr.status = 'pending'
  ORDER BY pr.created_at ASC
) r"""

LPP_FMT = """
const r = $input.all();
const agg = r.find(item => item.json.requests !== undefined);
const requests = agg ? (Array.isArray(agg.json.requests) ? agg.json.requests : JSON.parse(agg.json.requests)) : [];
const out = { requests };
return [{ json: { ...out, _out: out, _tool_name: 'list_pending_pto', _in: {}, _status: 'success', _error: null } }];
"""

BRANCH_8 = {
    'name': 'list_pending_pto', 'path': 'tool-list-pending-pto',
    'nodes': [
        pg_nd('pg-lpp', 'List Pending PTO', LPP_SQL, 660, 0, 'continueErrorOutput'),
        fmt_nd(LPP_FMT, 880, 0),
    ],
    'conns': {
        'List Pending PTO': {'main': [[{'node': 'Format Output', 'type': 'main', 'index': 0}],
                                       [{'node': 'Handle Error',  'type': 'main', 'index': 0}]]},
        'Format Output':    {'main': [[{'node': 'Prepare Log',   'type': 'main', 'index': 0}]]},
    }
}

# ── 9. decide_pto ─────────────────────────────────────────────────────────────
DP_VAL_JS = """
const body = $('Normalize Input').first().json;
const esc = s => s == null ? null : String(s).replace(/'/g, "''");
if (!body.code) throw new Error('code is required (e.g. PTO-1001).');
const decision = (body.decision || '').toLowerCase();
if (!['approved', 'rejected'].includes(decision))
  throw new Error('decision must be "approved" or "rejected".');
const id = $('Get Identity').first().json;
return [{ json: { ...id, code: body.code.trim(), decision: decision, note: esc(body.note || null) } }];
"""

DP_SQL = """DO $$ BEGIN
  IF (SELECT access_role FROM current_identity()) <> 'hr' THEN
    RAISE EXCEPTION 'ACCESS_DENIED: Only HR can decide PTO requests.';
  END IF;
END $$;
WITH req AS (
  SELECT id FROM pto_requests
  WHERE code = '{{ $json.code }}' AND workspace_id = '{{ $json.workspace_id }}'::uuid
)
SELECT row_to_json(d.*) AS result
FROM decide_pto(
  (SELECT id FROM req),
  '{{ $json.decision }}',
  'chat',
  {{ $json.note ? "'" + $json.note + "'" : 'NULL' }}
) d"""

DP_FMT = """
const items = $input.all();
const ctx = $('Validate Input').first().json;
const row_item = items.find(i => i.json.result !== undefined);
const row = row_item ? (typeof row_item.json.result === 'string' ? JSON.parse(row_item.json.result) : row_item.json.result) : {};
const out = { code: ctx.code, decision: ctx.decision, days: row.days,
              message: 'PTO request ' + ctx.code + ' has been ' + ctx.decision + '.' };
return [{ json: { ...out, _out: out, _tool_name: 'decide_pto',
  _in: { code: ctx.code, decision: ctx.decision, note: ctx.note }, _status: 'success', _error: null } }];
"""

BRANCH_9 = {
    'name': 'decide_pto', 'path': 'tool-decide-pto',
    'nodes': [
        code_nd('dp-val', 'Validate Input', DP_VAL_JS, 660,  0, 'continueErrorOutput'),
        pg_nd('dp-sql',   'Decide PTO',     DP_SQL,    880,  0, 'continueErrorOutput'),
        fmt_nd(DP_FMT, 1100, 0),
    ],
    'conns': {
        'Validate Input': {'main': [[{'node': 'Decide PTO',    'type': 'main', 'index': 0}],
                                     [{'node': 'Handle Error',  'type': 'main', 'index': 0}]]},
        'Decide PTO':     {'main': [[{'node': 'Format Output', 'type': 'main', 'index': 0}],
                                     [{'node': 'Handle Error',  'type': 'main', 'index': 0}]]},
        'Format Output':  {'main': [[{'node': 'Prepare Log',   'type': 'main', 'index': 0}]]},
    }
}

# ── 10. escalate_to_human ─────────────────────────────────────────────────────
ETH_NORM_JS = """
const item = $input.first().json;
const body = item.body ?? item;
const esc = s => s == null ? null : String(s).replace(/'/g, "''");
return [{ json: {
  ...body,
  summary: esc(body.summary || 'No summary provided'),
  conversation_id: body.conversation_id || null,
  _tool: 'escalate_to_human', _start_at: Date.now()
}}];
"""

ETH_SQL = """WITH ins AS (
  INSERT INTO tickets
    (workspace_id, employee_id, category, title, description, priority, assigned_team, is_escalation)
  VALUES (
    '{{ $json.workspace_id }}'::uuid,
    '{{ $json.employee_id }}'::uuid,
    'other',
    'Escalation: {{ $json.summary }}',
    '{{ $json.summary }}',
    'urgent', 'Human Agent', true
  )
  RETURNING code
)
SELECT i.code, {{ $json.conversation_id ? "'" + $json.conversation_id + "'" : 'NULL' }}::uuid AS conv_id FROM ins i"""

ETH_FMT = """
const r = $input.first().json;
const body = $('Normalize Input').first().json;
const out = { code: r.code,
  message: 'Your request has been escalated to a human agent. Reference: ' + r.code + '. Someone will follow up with you shortly.' };
return [{ json: { ...out, _out: out, _tool_name: 'escalate_to_human',
  _in: { summary: body.summary }, _status: 'success', _error: null } }];
"""

BRANCH_10 = {
    'name': 'escalate_to_human', 'path': 'tool-escalate-to-human',
    'normalize_js': ETH_NORM_JS,
    'nodes': [
        pg_nd('eth-ins', 'Insert Escalation', ETH_SQL, 660, 0, 'continueErrorOutput'),
        fmt_nd(ETH_FMT, 880, 0),
    ],
    'conns': {
        'Insert Escalation': {'main': [[{'node': 'Format Output', 'type': 'main', 'index': 0}],
                                        [{'node': 'Handle Error',  'type': 'main', 'index': 0}]]},
        'Format Output':     {'main': [[{'node': 'Prepare Log',   'type': 'main', 'index': 0}]]},
    }
}

# ── 11. submit_feedback ───────────────────────────────────────────────────────
SF_VAL_JS = """
const body = $('Normalize Input').first().json;
const rating = parseInt(body.rating);
if (![-1, 1].includes(rating)) throw new Error('rating must be 1 (positive) or -1 (negative).');
const id = $('Get Identity').first().json;
const esc = s => s == null ? null : String(s).replace(/'/g, "''");
return [{ json: { ...id, rating: rating, comment: esc(body.comment || null),
                  conversation_id: body.conversation_id || null } }];
"""

SF_SQL = """INSERT INTO conversations
  (workspace_id, employee_id, external_id, feedback, feedback_comment)
VALUES (
  '{{ $json.workspace_id }}'::uuid,
  '{{ $json.employee_id }}'::uuid,
  {{ $json.conversation_id ? "'" + $json.conversation_id + "'" : "'demo-' || gen_random_uuid()::text" }},
  {{ $json.rating }},
  {{ $json.comment ? "'" + $json.comment + "'" : 'NULL' }}
)
ON CONFLICT (workspace_id, external_id) DO UPDATE
  SET feedback = EXCLUDED.feedback,
      feedback_comment = EXCLUDED.feedback_comment,
      last_activity_at = now()
RETURNING id::text, feedback"""

SF_FMT = """
const r = $input.first().json;
const ctx = $('Validate Feedback').first().json;
const label = ctx.rating === 1 ? 'positive' : 'negative';
const out = { rating: ctx.rating, message: 'Thank you for your ' + label + ' feedback!' };
return [{ json: { ...out, _out: out, _tool_name: 'submit_feedback',
  _in: { rating: ctx.rating, comment: ctx.comment }, _status: 'success', _error: null } }];
"""

BRANCH_11 = {
    'name': 'submit_feedback', 'path': 'tool-submit-feedback',
    'nodes': [
        code_nd('sf-val',    'Validate Feedback', SF_VAL_JS,  660, 0, 'continueErrorOutput'),
        pg_nd('sf-upsert',   'Upsert Feedback',   SF_SQL,     880, 0, 'continueErrorOutput'),
        fmt_nd(SF_FMT, 1100, 0),
    ],
    'conns': {
        'Validate Feedback': {'main': [[{'node': 'Upsert Feedback', 'type': 'main', 'index': 0}],
                                        [{'node': 'Handle Error',    'type': 'main', 'index': 0}]]},
        'Upsert Feedback':   {'main': [[{'node': 'Format Output',   'type': 'main', 'index': 0}],
                                        [{'node': 'Handle Error',    'type': 'main', 'index': 0}]]},
        'Format Output':     {'main': [[{'node': 'Prepare Log',     'type': 'main', 'index': 0}]]},
    }
}


# ══════════════════════════════════════════════════════════════════════════════
# HTML webhook branches (12 & 13) — email approval loop
# ══════════════════════════════════════════════════════════════════════════════

# ── 12. api.pto-review (GET — email link → confirmation HTML page) ────────────
PEEK_SQL_NODE = pg_nd('pg-peek', 'Peek PTO Token', """SELECT code, employee_name, start_date::text, end_date::text, days::integer, reason, status
FROM peek_pto_by_token('{{ $json.query.token }}')""", 0, 0)

PEEK_SUCCESS_JS = r"""
const r = $input.first().json;
const wh = $('Webhook 12').first().json;
const token = wh.query?.token || '';
const proto = wh.headers?.['x-forwarded-proto'] || 'http';
const host  = wh.headers?.host || 'localhost:5678';
const baseUrl = proto + '://' + host;
const html = `<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Review PTO Request</title>
<style>
body{font-family:sans-serif;max-width:560px;margin:60px auto;padding:0 20px}
h1{color:#1a56db}
.card{background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:24px;margin:24px 0}
table{width:100%;border-collapse:collapse}
td{padding:8px 12px;border-bottom:1px solid #e2e8f0}
td:first-child{font-weight:600;color:#374151;width:35%}
.btn{display:inline-block;padding:12px 28px;border-radius:6px;font-size:15px;cursor:pointer;border:none;margin:4px}
.approve{background:#059669;color:#fff}.reject{background:#dc2626;color:#fff}
.status{display:inline-block;padding:3px 10px;border-radius:12px;font-size:13px;background:#fef3c7;color:#92400e}
</style></head><body>
<h1>PTO Request Review</h1>
<p>Please review the following time-off request:</p>
<div class="card">
<table>
  <tr><td>Employee</td><td>${r.employee_name}</td></tr>
  <tr><td>Dates</td><td>${r.start_date} → ${r.end_date}</td></tr>
  <tr><td>Days</td><td>${r.days}</td></tr>
  <tr><td>Reason</td><td>${r.reason}</td></tr>
  <tr><td>Reference</td><td>${r.code}</td></tr>
  <tr><td>Status</td><td><span class="status">${r.status}</span></td></tr>
</table>
</div>
${r.status === 'pending' ? `
<p><strong>Your decision:</strong></p>
<button class="btn approve" onclick="decide('approved')">&#10003; Approve</button>
<button class="btn reject"  onclick="decide('rejected')">&#10007; Reject</button>
<p><label style="font-size:14px">Note (optional):<br>
<textarea id="note" rows="2" style="width:100%;margin-top:4px;border:1px solid #d1d5db;border-radius:4px;padding:8px"></textarea>
</label></p>
<script>
async function decide(d){
  const note = document.getElementById('note').value;
  const resp = await fetch('${baseUrl}/webhook/pto-decide',{
    method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({token:'${token}',decision:d,note:note||null})
  });
  document.body.innerHTML = await resp.text();
}
</script>` : '<p style="color:#059669;font-weight:600">This request has already been decided.</p>'}
</body></html>`;
return [{ json: { html } }];
"""

PEEK_ERROR_JS = r"""
const item = $input.first();
const msg = item.json?.message || item.json?.error?.description || 'Invalid or expired link';
const html = `<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Link Error</title>
<style>body{font-family:sans-serif;max-width:480px;margin:80px auto;text-align:center;padding:0 20px}
.card{background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:24px;margin:24px 0}</style>
</head><body>
<h2>⚠️ Link Invalid or Expired</h2>
<div class="card"><p>${msg}</p></div>
<p style="color:#6b7280;font-size:14px">Approval links are single-use and expire after 48 hours.<br>
Please ask the employee to submit a new request.</p>
</body></html>`;
return [{ json: { html } }];
"""

BRANCH_12_NODES, BRANCH_12_CONNS = build_html_branch(
    11, 12, 'GET', 'pto-review', PEEK_SQL_NODE, PEEK_SUCCESS_JS, PEEK_ERROR_JS
)

# ── 13. api.pto-decide (POST — button click → decision HTML result) ───────────
DECIDE_TOKEN_SQL_NODE = pg_nd('pg-decide-tok', 'Decide by Token', """SELECT row_to_json(r.*) AS result
FROM decide_pto_by_token(
  '{{ $json.body?.token || $json.token }}',
  '{{ $json.body?.decision || $json.decision }}',
  {{ ($json.body?.note || $json.note) ? "'" + ($json.body?.note || $json.note).replace(/'/g, "''") + "'" : 'NULL' }}
) r""", 0, 0)

DECIDE_SUCCESS_JS = r"""
const item = $input.first().json;
const row = item.result ? (typeof item.result === 'string' ? JSON.parse(item.result) : item.result) : item;
const decision = row.status || 'decided';
const color = decision === 'approved' ? '#059669' : '#dc2626';
const icon  = decision === 'approved' ? '✅' : '❌';
const html = `<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Decision Recorded</title>
<style>body{font-family:sans-serif;max-width:480px;margin:80px auto;text-align:center;padding:0 20px}
.icon{font-size:56px;display:block;margin-bottom:12px}
.badge{display:inline-block;padding:6px 18px;border-radius:20px;font-size:16px;font-weight:600;color:#fff;background:${color};margin:12px 0}
</style></head><body>
<span class="icon">${icon}</span>
<h2>Decision Recorded</h2>
<p>Request <strong>${row.code}</strong> has been:</p>
<span class="badge">${decision.toUpperCase()}</span>
<p style="color:#6b7280;font-size:14px;margin-top:32px">The employee will be notified. You can close this window.</p>
</body></html>`;
return [{ json: { html } }];
"""

DECIDE_ERROR_JS = r"""
const item = $input.first();
const rawErr = item.json?.error;
const msg = (item.json?.message
         || (typeof rawErr === 'string' ? rawErr : rawErr?.description)
         || 'Could not process decision').replace(/\s*\[line \d+\]$/, '');
const friendly = msg.includes('INVALID_LINK')
  ? 'This approval link is invalid, expired, or has already been used.'
  : msg;
const html = `<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Error</title>
<style>body{font-family:sans-serif;max-width:480px;margin:80px auto;text-align:center;padding:0 20px}
.card{background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:24px;margin:24px 0}</style>
</head><body>
<h2>⚠️ Could Not Record Decision</h2>
<div class="card"><p>${friendly}</p></div>
<p style="color:#6b7280;font-size:14px">If the link has already been used, check your PTO system for the current status.</p>
</body></html>`;
return [{ json: { html } }];
"""

BRANCH_13_NODES, BRANCH_13_CONNS = build_html_branch(
    12, 13, 'POST', 'pto-decide', DECIDE_TOKEN_SQL_NODE, DECIDE_SUCCESS_JS, DECIDE_ERROR_JS
)


# ══════════════════════════════════════════════════════════════════════════════
# Branch 14: search_kb  (built manually — has IF nodes + HTTP requests)
# Flow: Webhook 14 → Normalize → Get Identity → Embed (Gemini) → Format Embedding
#       → Lookup Cache (Postgres) → Eval Cache → Cache Hit IF
#           TRUE  → Build Hit Response → Prepare Log
#           FALSE → Match Chunks (Postgres) → Eval Chunks → No Chunks IF
#                     TRUE  → Build No-Chunks Response → Prepare Log
#                     FALSE → Build Groq Prompt → Groq LLM → Build LLM Response
#                             → Write Cache (best-effort) → Format SKB Answer → Prepare Log
#       Prepare Log → Log Tool Call → Return Output
#       any error → Handle Error → Log Error → Return Error
# ══════════════════════════════════════════════════════════════════════════════

def build_search_kb_branch():
    n  = 14
    bi = 13
    by = bi * Y_STEP   # 6500
    bx = 0
    ey = by + 330      # 6830 — error row + cache-miss row

    # ── Header ──
    wh = {
        'id': f'wh-{n}', 'name': f'Webhook {n}',
        'type': 'n8n-nodes-base.webhook', 'typeVersion': 2,
        'position': [bx, by + 165],
        'webhookId': 'askops-tool-search-kb',
        'parameters': {'httpMethod': 'POST', 'path': 'tool-search-kb',
                       'responseMode': 'lastNode', 'options': {}}
    }
    nm = code_nd(f'nm-{n}', f'Normalize Input {n}',
                 "const item = $input.first().json;\n"
                 "const body = item.body ?? item;\n"
                 "return [{ json: { ...body, _tool: 'search_kb', _start_at: Date.now() } }];",
                 bx + 220, by + 110)
    gi = pg_nd(f'gi-{n}', f'Get Identity {n}', 'SELECT * FROM current_identity()',
               bx + 440, by + 110)

    # ── Prep Embed (merge identity + query before HTTP call; $json.query must exist) ──
    pemb = code_nd(f'skb-pemb-{n}', f'Prep Embed {n}',
        _t("""
const id = $('Get Identity __N__').first().json;
const q  = $('Normalize Input __N__').first().json.query;
if (!q || !q.trim()) throw new Error('search_kb: query is required');
return [{ json: { ...id, query: q.trim() } }];
""", n), 660, by + 110, 'continueErrorOutput')

    # ── Embed Query (Gemini HTTP) ──
    emb = {
        'id': f'skb-emb-{n}', 'name': f'Embed Query {n}',
        'type': 'n8n-nodes-base.httpRequest', 'typeVersion': 4.2,
        'position': [880, by + 110],
        'credentials': GEMINI_CRED,
        'parameters': {
            'method': 'POST',
            'url': 'https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent',
            'authentication': 'genericCredentialType',
            'genericAuthType': 'httpQueryAuth',
            'sendBody': True,
            'specifyBody': 'json',
            'jsonBody': (
                '={{ JSON.stringify({"model":"models/gemini-embedding-001",'
                '"content":{"parts":[{"text":$json.query}]},'
                '"taskType":"RETRIEVAL_QUERY","outputDimensionality":768}) }}'
            ),
            'options': {}
        },
        'onError': 'continueErrorOutput'
    }

    # ── Format Embedding (parse Gemini response → embedding_str for Postgres) ──
    femb = code_nd(f'skb-femb-{n}', f'Format Embedding {n}',
        _t("""
const id = $('Get Identity __N__').first().json;
const q  = $('Prep Embed __N__').first().json.query;
const vals = $input.first().json.embedding?.values;
if (!vals || vals.length === 0) throw new Error('Embedding error: Gemini returned no values');
const vec = '[' + vals.join(',') + ']';
return [{ json: { ...id, query: q, embedding_str: vec } }];
""", n), 1100, by + 110, 'continueErrorOutput')

    # ── Lookup Cache (always returns 1 row via json_agg) ──
    lkc = pg_nd(f'skb-lkc-{n}', f'Lookup Cache {n}',
        """SELECT COALESCE(json_agg(c), '[]'::json) AS cache_result
FROM (
  SELECT cache_id, answer, sources::text
  FROM lookup_cache(
    '{{ $json.workspace_id }}'::uuid,
    '{{ $json.access_role }}',
    '{{ $json.embedding_str }}'::vector
  )
) c""",
        1320, by + 110, 'continueErrorOutput')

    # ── Eval Cache (parse json_agg, set cache_hit flag) ──
    ec = code_nd(f'skb-ec-{n}', f'Eval Cache {n}',
        _t("""
const item = $input.first().json;
const id  = $('Get Identity __N__').first().json;
const q   = $('Prep Embed __N__').first().json.query;
const emb = $('Format Embedding __N__').first().json.embedding_str;
const arr = Array.isArray(item.cache_result) ? item.cache_result
  : (typeof item.cache_result === 'string' ? JSON.parse(item.cache_result || '[]') : []);
const hit = arr.length > 0;
const cached = arr[0] || null;
return [{ json: {
  ...id, query: q, embedding_str: emb,
  cache_hit:    hit,
  cache_id:     cached ? cached.cache_id  : null,
  cache_answer: cached ? cached.answer    : null,
  cache_sources: cached ? cached.sources  : null,
} }];
""", n), 1540, by + 110)

    # ── Cache Hit IF (TRUE=0 when cache_hit, FALSE=1 for miss) ──
    if_cache = {
        'id': f'skb-ifc-{n}', 'name': f'Cache Hit IF {n}',
        'type': 'n8n-nodes-base.if', 'typeVersion': 2.2,
        'position': [1760, by + 110],
        'parameters': {
            'conditions': {
                'options': {'caseSensitive': True, 'leftValue': '', 'typeValidation': 'loose'},
                'conditions': [{
                    'id': f'ifc-cond-{n}',
                    'leftValue': '={{ $json.cache_hit }}',
                    'rightValue': '',
                    'operator': {'type': 'boolean', 'operation': 'true',
                                 'name': 'boolean:true', 'rightType': 'any', 'singleValue': True}
                }],
                'combinator': 'and'
            },
            'options': {}
        }
    }

    # ── Build Hit Response (cache hit, TRUE path of Cache Hit IF) ──
    hr = code_nd(f'skb-hr-{n}', f'Build Hit Response {n}',
        _t("""
const item = $input.first().json;
const sources = typeof item.cache_sources === 'string'
  ? JSON.parse(item.cache_sources || '[]')
  : (Array.isArray(item.cache_sources) ? item.cache_sources : []);
const srcList = sources.map(s => s.title ? s.title + ' (' + s.source_type + ')' : (s.source_type || '')).join(', ');
const q = $('Prep Embed __N__').first().json.query;
const out = {
  answer: item.cache_answer,
  sources,
  source_citation: srcList ? 'Source: ' + srcList : null,
  cache_hit: true
};
return [{ json: { ...item, ...out, _out: out, _tool_name: 'search_kb',
  _in: { query: q }, _status: 'success', _error: null } }];
""", n), 1980, by + 110)

    # ── Match Chunks (cache miss, FALSE path of Cache Hit IF, row y=ey) ──
    mc = pg_nd(f'skb-mc-{n}', f'Match Chunks {n}',
        """SELECT COALESCE(json_agg(c), '[]'::json) AS chunks_data
FROM (
  SELECT chunk_id, title, source_type, source_url, content
  FROM match_chunks(
    '{{ $json.workspace_id }}'::uuid,
    '{{ $json.embedding_str }}'::vector,
    5,
    0.5
  )
) c""",
        1980, ey, 'continueErrorOutput')

    # ── Eval Chunks (parse json_agg, set has_chunks / no_chunks flags) ──
    eck = code_nd(f'skb-eck-{n}', f'Eval Chunks {n}',
        _t("""
const item = $input.first().json;
const id  = $('Get Identity __N__').first().json;
const q   = $('Prep Embed __N__').first().json.query;
const emb = $('Format Embedding __N__').first().json.embedding_str;
const chunks = Array.isArray(item.chunks_data) ? item.chunks_data
  : (typeof item.chunks_data === 'string' ? JSON.parse(item.chunks_data || '[]') : []);
return [{ json: {
  ...id, query: q, embedding_str: emb,
  chunks_data:  chunks,
  chunks_count: chunks.length,
  has_chunks:   chunks.length > 0,
  no_chunks:    chunks.length === 0
} }];
""", n), 2200, ey)

    # ── No Chunks IF (TRUE=0 when no chunks, FALSE=1 when chunks found) ──
    if_nck = {
        'id': f'skb-ifnck-{n}', 'name': f'No Chunks IF {n}',
        'type': 'n8n-nodes-base.if', 'typeVersion': 2.2,
        'position': [2420, ey],
        'parameters': {
            'conditions': {
                'options': {'caseSensitive': True, 'leftValue': '', 'typeValidation': 'loose'},
                'conditions': [{
                    'id': f'ifnck-cond-{n}',
                    'leftValue': '={{ $json.no_chunks }}',
                    'rightValue': '',
                    'operator': {'type': 'boolean', 'operation': 'true',
                                 'name': 'boolean:true', 'rightType': 'any', 'singleValue': True}
                }],
                'combinator': 'and'
            },
            'options': {}
        }
    }

    # ── Build No-Chunks Response (TRUE path of No Chunks IF, back on main row) ──
    nck = code_nd(f'skb-nck-{n}', f'Build No-Chunks Response {n}',
        _t("""
const q   = $('Prep Embed __N__').first().json.query;
const id  = $('Get Identity __N__').first().json;
const out = {
  answer: "I don't have information about that in the knowledge base yet. Try asking a more general question, or contact your HR/IT team directly.",
  sources: [],
  source_citation: null,
  cache_hit: false
};
return [{ json: { ...id, ...out, _out: out, _tool_name: 'search_kb',
  _in: { query: q }, _status: 'success', _error: null } }];
""", n), 2640, by + 110)

    # ── Build Groq Prompt (FALSE path of No Chunks IF — has chunks) ──
    gp = code_nd(f'skb-gp-{n}', f'Build Groq Prompt {n}',
        _t("""
const item = $input.first().json;
const id   = $('Get Identity __N__').first().json;
const chunks = Array.isArray(item.chunks_data) ? item.chunks_data
  : JSON.parse(item.chunks_data || '[]');
const ctx = chunks.map((c, i) =>
  '[' + (i+1) + '] ' + (c.title||'') + ' (' + (c.source_type||'') + '):' + c.content
).join('\\n\\n');
const sys = 'You are a helpful IT/HR service desk assistant for ' + id.company_name + '.\\n'
  + 'Answer based ONLY on the provided context. Be concise and professional.\\n'
  + "If the context doesn't contain the answer, say \\"I don't have that information.\\".\\n"
  + 'Always end with the source type in parentheses: (Source: website/upload/sample).';
const usr = 'Context:\\n' + ctx + '\\n\\nQuestion: ' + item.query + '\\nAnswer:';
const groqBody = JSON.stringify({
  model: 'openai/gpt-oss-120b',
  messages: [{role:'system',content:sys},{role:'user',content:usr}],
  max_tokens: 400,
  temperature: 0.1
});
return [{ json: { ...item, chunks_data: chunks, groq_body: groqBody } }];
""", n), 2640, ey, 'continueErrorOutput')

    # ── Groq LLM (HTTP Request) ──
    groq_nd = {
        'id': f'skb-groq-{n}', 'name': f'Groq LLM {n}',
        'type': 'n8n-nodes-base.httpRequest', 'typeVersion': 4.2,
        'position': [2860, ey],
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
        },
        'onError': 'continueErrorOutput'
    }

    # ── Build LLM Response (parse Groq output, escape for Write Cache) ──
    lr = code_nd(f'skb-lr-{n}', f'Build LLM Response {n}',
        _t("""
const resp = $input.first().json;
const ctx  = $('Build Groq Prompt __N__').first().json;
const esc  = s => s == null ? null : String(s).replace(/'/g, "''");
const answer = resp.choices?.[0]?.message?.content || "I could not generate an answer. Please try again.";
const chunks  = Array.isArray(ctx.chunks_data) ? ctx.chunks_data : JSON.parse(ctx.chunks_data || '[]');
const sources = chunks.map(c => ({ title: c.title, source_type: c.source_type, url: c.source_url || null }));
return [{ json: {
  ...ctx,
  answer,
  answer_esc:   esc(answer),
  question_esc: esc(ctx.query),
  sources_jsonb: JSON.stringify(sources)
} }];
""", n), 3080, ey, 'continueErrorOutput')

    # ── Write Cache (Postgres, best-effort — both outputs go to Format SKB Answer) ──
    wc = pg_nd(f'skb-wc-{n}', f'Write Cache {n}',
        """INSERT INTO semantic_cache
  (workspace_id, access_role, question, question_embedding, answer, sources)
VALUES (
  '{{ $json.workspace_id }}'::uuid,
  '{{ $json.access_role }}',
  '{{ $json.question_esc }}',
  '{{ $json.embedding_str }}'::vector,
  '{{ $json.answer_esc }}',
  '{{ $json.sources_jsonb }}'::jsonb
)
RETURNING id::text AS cache_id""",
        3300, ey, 'continueErrorOutput')

    # ── Format SKB Answer (reads from Build LLM Response; best-effort after Write Cache) ──
    fmt = code_nd(f'skb-fmt-{n}', f'Format SKB Answer {n}',
        _t("""
const lr = $('Build LLM Response __N__').first().json;
const chunks  = Array.isArray(lr.chunks_data) ? lr.chunks_data : JSON.parse(lr.chunks_data || '[]');
const sources = chunks.map(c => ({ title: c.title, source_type: c.source_type, url: c.source_url }));
const srcList = [...new Set(chunks.map(c => c.source_type))].join(', ');
const out = {
  answer: lr.answer,
  sources,
  source_citation: srcList ? 'Source: ' + srcList : null,
  cache_hit: false
};
return [{ json: { ...lr, ...out, _out: out, _tool_name: 'search_kb',
  _in: { query: lr.query }, _status: 'success', _error: null } }];
""", n), 3520, ey)

    # ── Footer ──
    fx = 3740
    pl  = code_nd(f'pl-{n}',  f'Prepare Log {n}',   _t(_PREP_LOG_JS, n), fx,       by + 110)
    lg  = pg_nd(f'lg-{n}',    f'Log Tool Call {n}',  _LOG_SQL,            fx + 220, by + 110)
    ro  = code_nd(f'ro-{n}',  f'Return Output {n}',
                  f"const d = $('Prepare Log {n}').first().json;\n"
                  f"const clean = Object.fromEntries(Object.entries(d).filter(([k]) => !k.startsWith('_l')));\n"
                  f"return [{{ json: clean }}];",
                  fx + 440, by + 110)
    he  = code_nd(f'he-{n}',  f'Handle Error {n}',  _t(_ERR_HANDLE_JS, n), 220, ey)
    le  = pg_nd(f'le-{n}',    f'Log Error {n}',      _LOG_SQL,              440, ey)
    re_ = code_nd(f're-{n}',  f'Return Error {n}',
                  f"const d = $('Handle Error {n}').first().json;\n"
                  f"return [{{ json: {{ error: d.error }} }}];",
                  660, ey)

    nodes = [wh, nm, gi, pemb, emb, femb, lkc, ec, if_cache, hr,
             mc, eck, if_nck, nck, gp, groq_nd, lr, wc, fmt,
             pl, lg, ro, he, le, re_]

    conns = {
        f'Webhook {n}':                  {'main': [[{'node': f'Normalize Input {n}',         'type': 'main', 'index': 0}]]},
        f'Normalize Input {n}':          {'main': [[{'node': f'Get Identity {n}',            'type': 'main', 'index': 0}]]},
        f'Get Identity {n}':             {'main': [[{'node': f'Prep Embed {n}',              'type': 'main', 'index': 0}]]},
        f'Prep Embed {n}':               {'main': [[{'node': f'Embed Query {n}',             'type': 'main', 'index': 0}],
                                                    [{'node': f'Handle Error {n}',           'type': 'main', 'index': 0}]]},
        f'Embed Query {n}':              {'main': [[{'node': f'Format Embedding {n}',        'type': 'main', 'index': 0}],
                                                    [{'node': f'Handle Error {n}',           'type': 'main', 'index': 0}]]},
        f'Format Embedding {n}':         {'main': [[{'node': f'Lookup Cache {n}',            'type': 'main', 'index': 0}],
                                                    [{'node': f'Handle Error {n}',           'type': 'main', 'index': 0}]]},
        f'Lookup Cache {n}':             {'main': [[{'node': f'Eval Cache {n}',              'type': 'main', 'index': 0}],
                                                    [{'node': f'Handle Error {n}',           'type': 'main', 'index': 0}]]},
        f'Eval Cache {n}':               {'main': [[{'node': f'Cache Hit IF {n}',            'type': 'main', 'index': 0}]]},
        f'Cache Hit IF {n}':             {'main': [[{'node': f'Build Hit Response {n}',      'type': 'main', 'index': 0}],
                                                    [{'node': f'Match Chunks {n}',           'type': 'main', 'index': 0}]]},
        f'Build Hit Response {n}':       {'main': [[{'node': f'Prepare Log {n}',             'type': 'main', 'index': 0}]]},
        f'Match Chunks {n}':             {'main': [[{'node': f'Eval Chunks {n}',             'type': 'main', 'index': 0}],
                                                    [{'node': f'Handle Error {n}',           'type': 'main', 'index': 0}]]},
        f'Eval Chunks {n}':              {'main': [[{'node': f'No Chunks IF {n}',            'type': 'main', 'index': 0}]]},
        f'No Chunks IF {n}':             {'main': [[{'node': f'Build No-Chunks Response {n}','type': 'main', 'index': 0}],
                                                    [{'node': f'Build Groq Prompt {n}',      'type': 'main', 'index': 0}]]},
        f'Build No-Chunks Response {n}': {'main': [[{'node': f'Prepare Log {n}',             'type': 'main', 'index': 0}]]},
        f'Build Groq Prompt {n}':        {'main': [[{'node': f'Groq LLM {n}',               'type': 'main', 'index': 0}],
                                                    [{'node': f'Handle Error {n}',           'type': 'main', 'index': 0}]]},
        f'Groq LLM {n}':                 {'main': [[{'node': f'Build LLM Response {n}',      'type': 'main', 'index': 0}],
                                                    [{'node': f'Handle Error {n}',           'type': 'main', 'index': 0}]]},
        f'Build LLM Response {n}':       {'main': [[{'node': f'Write Cache {n}',             'type': 'main', 'index': 0}],
                                                    [{'node': f'Handle Error {n}',           'type': 'main', 'index': 0}]]},
        # best-effort: Write Cache success AND error both → Format SKB Answer
        f'Write Cache {n}':              {'main': [[{'node': f'Format SKB Answer {n}',       'type': 'main', 'index': 0}],
                                                    [{'node': f'Format SKB Answer {n}',      'type': 'main', 'index': 0}]]},
        f'Format SKB Answer {n}':        {'main': [[{'node': f'Prepare Log {n}',             'type': 'main', 'index': 0}]]},
        f'Prepare Log {n}':              {'main': [[{'node': f'Log Tool Call {n}',           'type': 'main', 'index': 0}]]},
        f'Log Tool Call {n}':            {'main': [[{'node': f'Return Output {n}',           'type': 'main', 'index': 0}]]},
        f'Handle Error {n}':             {'main': [[{'node': f'Log Error {n}',               'type': 'main', 'index': 0}]]},
        f'Log Error {n}':                {'main': [[{'node': f'Return Error {n}',            'type': 'main', 'index': 0}]]},
    }

    return nodes, conns


BRANCH_14_NODES, BRANCH_14_CONNS = build_search_kb_branch()


# ══════════════════════════════════════════════════════════════════════════════
# Assemble + deploy
# ══════════════════════════════════════════════════════════════════════════════

BRANCHES = [
    BRANCH_1, BRANCH_2, BRANCH_3, BRANCH_4, BRANCH_5,
    BRANCH_6, BRANCH_7, BRANCH_8, BRANCH_9, BRANCH_10, BRANCH_11
]

all_nodes, all_conns = [], {}
for bi, branch in enumerate(BRANCHES):
    nodes, conns = build_branch(bi, branch)
    all_nodes.extend(nodes)
    all_conns.update(conns)

# HTML webhook branches for the email approval loop
all_nodes.extend(BRANCH_12_NODES)
all_conns.update(BRANCH_12_CONNS)
all_nodes.extend(BRANCH_13_NODES)
all_conns.update(BRANCH_13_CONNS)

# Branch 14: search_kb
all_nodes.extend(BRANCH_14_NODES)
all_conns.update(BRANCH_14_CONNS)

print(f'Assembling {len(all_nodes)} nodes across {len(BRANCHES)} tool branches + 2 HTML branches + Branch 14 (search_kb)...')

wf_body = {
    'name': 'mcp.ask-ops',
    'nodes': all_nodes,
    'connections': all_conns,
    'settings': {'executionOrder': 'v1'}
}

result = api('PUT', f'/api/v1/workflows/{TARGET_ID}', wf_body)
print(f'PUT → id={result.get("id")}, name={result.get("name")}')

api('POST', f'/api/v1/workflows/{TARGET_ID}/activate', {})
print('Activated  → http://localhost:5678/workflow/' + TARGET_ID)


# ══════════════════════════════════════════════════════════════════════════════
# cron.cleanup — hourly call to delete_expired_workspaces()
# ══════════════════════════════════════════════════════════════════════════════
print('\nDeploying cron.cleanup ...')

CLEANUP_WF = {
    'name': 'cron.cleanup',
    'nodes': [
        {
            'id': 'cron-sched', 'name': 'Every Hour',
            'type': 'n8n-nodes-base.scheduleTrigger', 'typeVersion': 1.2,
            'position': [0, 0],
            'parameters': {
                'rule': {'interval': [{'field': 'hours', 'minutesInterval': 1}]}
            }
        },
        pg_nd('cron-pg', 'Delete Expired',
              'SELECT delete_expired_workspaces() AS deleted_count',
              220, 0),
        code_nd('cron-log', 'Log Result',
                "const r = $input.first().json;\n"
                "console.log('Cleanup: deleted', r.deleted_count, 'expired workspace(s)');\n"
                "return [{ json: r }];",
                440, 0),
    ],
    'connections': {
        'Every Hour':     {'main': [[{'node': 'Delete Expired', 'type': 'main', 'index': 0}]]},
        'Delete Expired': {'main': [[{'node': 'Log Result',     'type': 'main', 'index': 0}]]},
    },
    'settings': {'executionOrder': 'v1'}
}

# Check if cron.cleanup already exists
existing_wfs = api('GET', '/api/v1/workflows?limit=250')
cleanup_existing = next((w for w in existing_wfs.get('data', []) if w['name'] == 'cron.cleanup'), None)
if cleanup_existing:
    r = api('PUT', f'/api/v1/workflows/{cleanup_existing["id"]}', CLEANUP_WF)
    api('POST', f'/api/v1/workflows/{cleanup_existing["id"]}/activate', {})
    print(f'  Updated + activated cron.cleanup (id={cleanup_existing["id"]})')
else:
    r = api('POST', '/api/v1/workflows', CLEANUP_WF)
    api('POST', f'/api/v1/workflows/{r["id"]}/activate', {})
    print(f'  Created + activated cron.cleanup (id={r["id"]})')


# ══════════════════════════════════════════════════════════════════════════════
# ingest.website — Jina scrape → Groq extract → Gemini embed → Postgres
# ══════════════════════════════════════════════════════════════════════════════
print('\nDeploying ingest.website ...')

# Jina scrape + URL scoring code
INGEST_SCRAPE_JS = """
const body = $input.first().json.body ?? $input.first().json;
const wsId  = body.workspace_id;
const rawUrl = (body.url || '').trim().replace(/\\/+$/, '');
if (!wsId || !rawUrl) throw new Error('workspace_id and url are required');

// Normalise: ensure https://
const url = rawUrl.startsWith('http') ? rawUrl : 'https://' + rawUrl;

return [{ json: { workspace_id: wsId, base_url: url, _start_at: Date.now() } }];
"""

# Fetch homepage via Jina
INGEST_FETCH_JS = """
const item = $input.first().json;
const jinaUrl = 'https://r.jina.ai/' + item.base_url;
return [{ json: { ...item, jina_url: jinaUrl } }];
"""

INGEST_JINA_NODE = {
    'id': 'ing-jina', 'name': 'Jina Fetch',
    'type': 'n8n-nodes-base.httpRequest', 'typeVersion': 4.2,
    'position': [660, 0],
    'parameters': {
        'method': 'GET',
        'url': '={{ $json.jina_url }}',
        'sendHeaders': True,
        'headerParameters': {
            'parameters': [
                {'name': 'Accept', 'value': 'text/plain'},
                {'name': 'X-Return-Format', 'value': 'markdown'},
            ]
        },
        'options': {'response': {'response': {'responseFormat': 'text'}}}
    },
    'onError': 'continueErrorOutput'
}

# Extract company info + chunk content
INGEST_EXTRACT_JS = """
const item = $input.first().json;
const content = $input.first().json.data || $input.first().json.body || '';
const wsId = $('Validate Input').first().json.workspace_id;
const baseUrl = $('Validate Input').first().json.base_url;

// Chunk the content: ~800 chars with 100 overlap, keeping paragraphs
function chunkText(text, maxLen=800, overlap=100) {
  const paras = text.split(/\\n\\n+/).filter(p => p.trim().length > 20);
  const chunks = [];
  let cur = '';
  for (const p of paras) {
    if (cur.length + p.length + 2 > maxLen && cur.length > 0) {
      chunks.push(cur.trim());
      // overlap: keep last paragraph
      cur = cur.split('\\n\\n').slice(-1)[0] + '\\n\\n' + p;
    } else {
      cur = cur ? cur + '\\n\\n' + p : p;
    }
  }
  if (cur.trim().length > 0) chunks.push(cur.trim());
  return chunks;
}

const chunks = chunkText(content, 800, 100).slice(0, 20); // cap at 20 chunks per page
return chunks.map((c, i) => ({ json: {
  workspace_id: wsId,
  base_url: baseUrl,
  source_url: baseUrl,
  chunk_index: i,
  content: c,
  total_chunks: chunks.length
} }));
"""

# Embed each chunk via Gemini
INGEST_EMBED_NODE = {
    'id': 'ing-emb', 'name': 'Embed Chunk',
    'type': 'n8n-nodes-base.httpRequest', 'typeVersion': 4.2,
    'position': [1100, 0],
    'credentials': GEMINI_CRED,
    'parameters': {
        'method': 'POST',
        'url': 'https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent',
        'authentication': 'genericCredentialType',
        'genericAuthType': 'httpQueryAuth',
        'sendBody': True,
        'specifyBody': 'json',
        'jsonBody': (
            '={{ JSON.stringify({"model":"models/gemini-embedding-001",'
            '"content":{"parts":[{"text":$json.content}]},'
            '"taskType":"RETRIEVAL_DOCUMENT","outputDimensionality":768}) }}'
        ),
        'options': {}
    },
    'onError': 'continueErrorOutput'
}

# Insert document + chunk into Postgres
INGEST_DOC_SQL = """WITH ins_doc AS (
  INSERT INTO documents (workspace_id, source_type, title, source_url, content)
  VALUES (
    '{{ $json.workspace_id }}'::uuid,
    'website',
    'Website: {{ $json.base_url }}',
    '{{ $json.source_url }}',
    '{{ $json.content.substring(0,200).replace(/'/g, "''") }}...'
  )
  ON CONFLICT DO NOTHING
  RETURNING id
),
doc_id AS (
  SELECT id FROM ins_doc
  UNION ALL
  SELECT id FROM documents
   WHERE workspace_id = '{{ $json.workspace_id }}'::uuid
     AND source_url   = '{{ $json.source_url }}'
     AND source_type  = 'website'
   LIMIT 1
)
INSERT INTO chunks (document_id, workspace_id, chunk_index, content, embedding)
VALUES (
  (SELECT id FROM doc_id LIMIT 1),
  '{{ $json.workspace_id }}'::uuid,
  {{ $json.chunk_index }},
  '{{ $json.content.replace(/'/g, "''") }}',
  '{{ $json.embedding_str }}'::vector
)
ON CONFLICT DO NOTHING
RETURNING id::text"""

INGEST_FMT_EMBED_JS = """
const item = $input.first().json;
const vals = item.embedding?.values;
if (!vals || vals.length === 0) throw new Error('Embed error: no values from Gemini');
const vec = '[' + vals.join(',') + ']';
const ctx = $('Extract Chunks').first().json;
// $('Extract Chunks') may reference wrong item in loop; use current item fields
return [{ json: {
  workspace_id: ctx.workspace_id || item.workspace_id,
  base_url:     ctx.base_url     || item.base_url,
  source_url:   ctx.source_url   || item.source_url,
  chunk_index:  ctx.chunk_index  ?? item.chunk_index ?? 0,
  content:      ctx.content      || item.content,
  embedding_str: vec
} }];
"""

INGEST_DONE_JS = """
const count = $input.all().length;
return [{ json: { status: 'done', chunks_stored: count, message: 'Ingestion complete.' } }];
"""

INGEST_WF = {
    'name': 'ingest.website',
    'nodes': [
        {
            'id': 'ing-wh', 'name': 'Ingest Webhook',
            'type': 'n8n-nodes-base.webhook', 'typeVersion': 2,
            'position': [0, 0],
            'webhookId': 'askops-ingest-website',
            'parameters': {'httpMethod': 'POST', 'path': 'ingest/website',
                           'responseMode': 'lastNode', 'options': {}}
        },
        code_nd('ing-val', 'Validate Input', INGEST_SCRAPE_JS, 220, 0, 'continueErrorOutput'),
        code_nd('ing-prep', 'Prep Jina URL', INGEST_FETCH_JS, 440, 0),
        INGEST_JINA_NODE,
        code_nd('ing-ext', 'Extract Chunks', INGEST_EXTRACT_JS, 880, 0, 'continueErrorOutput'),
        INGEST_EMBED_NODE,
        code_nd('ing-femb', 'Format Embedding', INGEST_FMT_EMBED_JS, 1320, 0, 'continueErrorOutput'),
        pg_nd('ing-pg', 'Store Chunk', INGEST_DOC_SQL, 1540, 0, 'continueErrorOutput'),
        code_nd('ing-done', 'Done', INGEST_DONE_JS, 1760, 0),
        code_nd('ing-err', 'Ingest Error',
                "const e = $input.first().json;\n"
                "const msg = e.message || e.error?.description || 'Ingest failed';\n"
                "return [{ json: { status: 'error', error: msg } }];",
                440, 220),
    ],
    'connections': {
        'Ingest Webhook':  {'main': [[{'node': 'Validate Input',   'type': 'main', 'index': 0}]]},
        'Validate Input':  {'main': [[{'node': 'Prep Jina URL',    'type': 'main', 'index': 0}],
                                      [{'node': 'Ingest Error',    'type': 'main', 'index': 0}]]},
        'Prep Jina URL':   {'main': [[{'node': 'Jina Fetch',       'type': 'main', 'index': 0}]]},
        'Jina Fetch':      {'main': [[{'node': 'Extract Chunks',   'type': 'main', 'index': 0}],
                                      [{'node': 'Ingest Error',    'type': 'main', 'index': 0}]]},
        'Extract Chunks':  {'main': [[{'node': 'Embed Chunk',      'type': 'main', 'index': 0}],
                                      [{'node': 'Ingest Error',    'type': 'main', 'index': 0}]]},
        'Embed Chunk':     {'main': [[{'node': 'Format Embedding', 'type': 'main', 'index': 0}],
                                      [{'node': 'Ingest Error',    'type': 'main', 'index': 0}]]},
        'Format Embedding':{'main': [[{'node': 'Store Chunk',      'type': 'main', 'index': 0}],
                                      [{'node': 'Ingest Error',    'type': 'main', 'index': 0}]]},
        'Store Chunk':     {'main': [[{'node': 'Done',             'type': 'main', 'index': 0}],
                                      [{'node': 'Ingest Error',    'type': 'main', 'index': 0}]]},
    },
    'settings': {'executionOrder': 'v1'}
}

ingest_existing = next((w for w in existing_wfs.get('data', []) if w['name'] == 'ingest.website'), None)
if ingest_existing:
    r = api('PUT', f'/api/v1/workflows/{ingest_existing["id"]}', INGEST_WF)
    api('POST', f'/api/v1/workflows/{ingest_existing["id"]}/activate', {})
    print(f'  Updated + activated ingest.website (id={ingest_existing["id"]})')
else:
    r = api('POST', '/api/v1/workflows', INGEST_WF)
    api('POST', f'/api/v1/workflows/{r["id"]}/activate', {})
    print(f'  Created + activated ingest.website (id={r["id"]})')

print('\nDone.')
