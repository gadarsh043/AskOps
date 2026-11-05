#!/usr/bin/env python3
"""
Build the unified mcp.ask-ops workflow (qhmoB9pZdLav12FB) with all 11 tool branches.
Each branch: Webhook N → Normalize Input N → Get Identity N → [tool logic]
             → Prepare Log N → Log Tool Call N → Return Output N
                             ↘ Handle Error N → Log Error N → Return Error N
"""
import json, re, urllib.request, urllib.error

BASE      = 'http://localhost:5678'
API_KEY   = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIyZjIyYTczYy04ZGUyLTQyZTMtYTg3ZS01OTBjMGYyMjIyYjciLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwiaWF0IjoxNzkzODU5MzQ2fQ.eAmo5vLR78e7fRQ7rbo3vGjV6r_cdMrM_FYavc4DBII'
TARGET_ID = 'qhmoB9pZdLav12FB'
CRED      = {'postgres': {'id': '4DuuvBbohpSo7Mr0', 'name': 'AskOps Postgres'}}

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


# ── Footer JS/SQL templates (use __N__ as placeholder, replaced by suffix_n) ──
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

    # ── Custom or default normalize JS ──
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
        snd = json.loads(json.dumps(nd))   # deep copy
        snd['name'] = new_name
        snd['id']   = f'{snd["id"]}-{n}'
        snd['position'] = [snd['position'][0] + bx, snd['position'][1] + by]
        if 'jsCode' in snd.get('parameters', {}):
            snd['parameters']['jsCode'] = suffix_js(snd['parameters']['jsCode'], n)
        if 'query' in snd.get('parameters', {}):
            snd['parameters']['query'] = suffix_js(snd['parameters']['query'], n)
        tool_sfx.append(snd)

    # ── Footer nodes (placed after last tool node) ──
    max_x = max(nd['position'][0] for nd in tool_sfx) if tool_sfx else bx + 440
    fx = max_x + X_STEP
    ey = by + 330   # error row

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
    # Suffix tool-specific connections
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

# ── 7. request_pto ────────────────────────────────────────────────────────────
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

RPTO_INS_SQL = """WITH tok AS (SELECT gen_random_bytes(32) AS raw)
INSERT INTO pto_requests
  (workspace_id, employee_id, start_date, end_date, days, reason,
   status, approval_token_hash, token_expires_at)
SELECT '{{ $json.workspace_id }}'::uuid, '{{ $json.employee_id }}'::uuid,
  '{{ $json.start_date }}'::date, '{{ $json.end_date }}'::date,
  {{ $json.requested_days }}, '{{ $json.reason }}', 'pending',
  encode(digest(raw, 'sha256'), 'hex'), now() + interval '48 hours'
FROM tok
RETURNING code, days::text, status"""

RPTO_FMT = """
const r = $input.first().json;
const ctx = $('Guard Check').first().json;
const body = $('Normalize Input').first().json;
const out = { code: r.code, days: r.days, status: r.status,
              start_date: ctx.start_date, end_date: ctx.end_date,
              message: 'PTO request submitted. Your manager will receive an approval email shortly.' };
return [{ json: { ...out, _out: out, _tool_name: 'request_pto',
  _in: { start_date: body.start_date, end_date: body.end_date, reason: body.reason },
  _status: 'success', _error: null } }];
"""

BRANCH_7 = {
    'name': 'request_pto', 'path': 'tool-request-pto',
    'nodes': [
        code_nd('rpto-val',   'Validate Dates', RPTO_VAL_JS,   660,  0, 'continueErrorOutput'),
        pg_nd('rpto-check',   'Check Balance',  RPTO_CHECK_SQL, 880,  0, 'continueErrorOutput'),
        code_nd('rpto-guard', 'Guard Check',    RPTO_GUARD_JS,  1100, 0, 'continueErrorOutput'),
        pg_nd('rpto-ins',     'Insert PTO',     RPTO_INS_SQL,   1320, 0, 'continueErrorOutput'),
        fmt_nd(RPTO_FMT, 1540, 0),
    ],
    'conns': {
        'Validate Dates': {'main': [[{'node': 'Check Balance', 'type': 'main', 'index': 0}],
                                     [{'node': 'Handle Error',  'type': 'main', 'index': 0}]]},
        'Check Balance':  {'main': [[{'node': 'Guard Check',   'type': 'main', 'index': 0}],
                                     [{'node': 'Handle Error',  'type': 'main', 'index': 0}]]},
        'Guard Check':    {'main': [[{'node': 'Insert PTO',    'type': 'main', 'index': 0}],
                                     [{'node': 'Handle Error',  'type': 'main', 'index': 0}]]},
        'Insert PTO':     {'main': [[{'node': 'Format Output', 'type': 'main', 'index': 0}],
                                     [{'node': 'Handle Error',  'type': 'main', 'index': 0}]]},
        'Format Output':  {'main': [[{'node': 'Prepare Log',   'type': 'main', 'index': 0}]]},
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

print(f'Assembling {len(all_nodes)} nodes across {len(BRANCHES)} branches...')

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
print('Done.')
