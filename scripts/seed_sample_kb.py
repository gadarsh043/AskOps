#!/usr/bin/env python3
"""
Seed the knowledge base with sample Northwind Labs content for testing search_kb.
Embeds content via the Gemini API and inserts into documents + chunks tables.

Usage:
  docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d askops -t -A -c "SELECT id FROM workspaces LIMIT 1"' | \
    python3 scripts/seed_sample_kb.py

Or with an explicit workspace ID:
  python3 scripts/seed_sample_kb.py 00000000-0000-0000-0000-000000000001
"""
import json, os, sys, urllib.request, urllib.error, re

# ── Load .env ──────────────────────────────────────────────────────────────────
env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
if os.path.isfile(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, _, v = line.partition('=')
                v = v.strip().strip('"')
                os.environ.setdefault(k.strip(), v)

GEMINI_KEY = os.environ.get('GEMINI_API_KEY', '')
DB_HOST    = os.environ.get('DB_HOST', 'localhost')
DB_PORT    = os.environ.get('DB_PORT', '5432')
DB_NAME    = 'askops'
DB_USER    = 'askops_app'
DB_PASS    = os.environ.get('APP_DB_PASSWORD', '')

if not GEMINI_KEY:
    print('ERROR: GEMINI_API_KEY not set in .env')
    sys.exit(1)

WORKSPACE_ID = (sys.argv[1] if len(sys.argv) > 1
                else '00000000-0000-0000-0000-000000000001')

# ── Sample content ─────────────────────────────────────────────────────────────
SAMPLES = [
    {
        'title': 'PTO Policy (SAMPLE)',
        'source_type': 'sample',
        'source_url': None,
        'chunks': [
            ('PTO Policy Overview',
             'Northwind Labs offers a generous paid time off (PTO) policy. '
             'Full-time employees accrue PTO based on their role and tenure. '
             'Software engineers start with 10 days per year and accrue up to 20 days after 5 years. '
             'PTO requests must be submitted at least 48 hours in advance for requests under 3 days, '
             'and 2 weeks in advance for requests over 5 days.'),
            ('PTO Request Process',
             'To request PTO, submit a request through the AskOps chatbot or HR portal. '
             'All PTO requests require manager approval. '
             'Requests are processed within 1 business day. '
             'Unused PTO can be carried over (up to 5 days) to the following year. '
             'PTO cannot be cashed out except upon termination.'),
            ('PTO Blackout Dates',
             'Northwind Labs observes end-of-quarter blackout periods where PTO may be restricted. '
             'Blackout periods are announced by HR at least 60 days in advance. '
             'Emergency leave during blackout periods requires VP approval. '
             'Federal holidays are paid days off separate from your PTO balance.'),
        ]
    },
    {
        'title': 'IT Security Policy (SAMPLE)',
        'source_type': 'sample',
        'source_url': None,
        'chunks': [
            ('Password Requirements',
             'All Northwind Labs employees must use strong passwords: minimum 12 characters, '
             'at least one uppercase letter, one number, and one special character. '
             'Passwords must be changed every 90 days. '
             'Multi-factor authentication (MFA) is required for all corporate systems. '
             'Never share your password with anyone, including IT staff.'),
            ('Device Security',
             'All company devices must have full-disk encryption enabled. '
             'Install only approved software from the IT-approved software catalog. '
             'Report lost or stolen devices to IT immediately (IT hotline: ext 2000). '
             'Remote wipe will be initiated for lost devices. '
             'Personal devices accessing corporate resources must be enrolled in MDM.'),
            ('VPN Policy',
             'Remote employees must connect via the company VPN when accessing internal resources. '
             'The VPN client is available from the IT portal at it.northwind.example. '
             'VPN sessions auto-disconnect after 8 hours of inactivity. '
             'Split tunneling is disabled; all traffic routes through corporate network when on VPN. '
             'If the VPN client disconnects repeatedly, restart it and contact IT Support.'),
        ]
    },
    {
        'title': 'Benefits Overview (SAMPLE)',
        'source_type': 'sample',
        'source_url': None,
        'chunks': [
            ('Health Insurance',
             'Northwind Labs provides comprehensive medical, dental, and vision coverage. '
             'The company covers 80% of the premium for employees and 60% for dependents. '
             'Open enrollment is in November each year for the following calendar year. '
             'New hires must enroll within 30 days of their start date. '
             'Contact benefits@northwind.example for questions.'),
            ('Retirement and 401k',
             'Northwind Labs offers a 401(k) plan with a 4% company match. '
             'Employees are eligible to contribute starting on their first day. '
             'The company match vests over 3 years (1/3 per year). '
             'The 401(k) is administered by Fidelity. '
             'Contact HR for the enrollment code and investment options.'),
        ]
    },
    {
        'title': 'Remote Work Policy (SAMPLE)',
        'source_type': 'sample',
        'source_url': None,
        'chunks': [
            ('Remote Work Eligibility',
             'Full-time employees who have completed 90 days of employment are eligible for remote work. '
             'Engineering, product, and design roles may work fully remote. '
             'Customer-facing and operations roles require a minimum of 2 days per week in office. '
             'Remote work agreements must be approved by your manager and HR. '
             'Employees must maintain a professional, distraction-free workspace.'),
            ('Home Office Stipend',
             'Northwind Labs provides a one-time $500 home office equipment stipend for approved remote workers. '
             'Annual $100 internet/phone allowance is paid out quarterly ($25/quarter). '
             'Submit receipts through the expense portal within 90 days of purchase. '
             'Equipment purchased with the stipend remains property of the company upon termination. '
             'Contact finance@northwind.example for reimbursement questions.'),
        ]
    },
]


# ── Gemini embed ───────────────────────────────────────────────────────────────
def embed(text):
    url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key={GEMINI_KEY}'
    body = json.dumps({
        'model': 'models/gemini-embedding-001',
        'content': {'parts': [{'text': text}]},
        'taskType': 'RETRIEVAL_DOCUMENT',
        'outputDimensionality': 768
    }).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())
    vals = data['embedding']['values']
    return '[' + ','.join(str(v) for v in vals) + ']'


# ── Postgres via docker compose exec ──────────────────────────────────────────
import subprocess

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

def psql(sql):
    result = subprocess.run(
        ['docker', 'compose', 'exec', '-T', 'postgres', 'sh', '-c',
         'PGPASSWORD="$APP_DB_PASSWORD" psql -h localhost -U askops_app -d askops -t -A'],
        input=sql, capture_output=True, text=True, cwd=PROJECT_ROOT
    )
    if result.returncode != 0:
        raise RuntimeError(f'psql error: {result.stderr}')
    # -t -A outputs each result row, then optionally a DML status line like "INSERT 0 1".
    # For RETURNING queries, the first line is the returned value; take only that.
    lines = [l for l in result.stdout.splitlines() if l.strip() and not l.startswith('INSERT') and not l.startswith('UPDATE') and not l.startswith('DELETE') and not l.startswith('SELECT')]
    return lines[0] if lines else result.stdout.strip()


def pg_escape(s):
    return str(s).replace("'", "''") if s else ''


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    # Verify workspace exists
    ws = psql(f"SELECT company_name FROM workspaces WHERE id = '{WORKSPACE_ID}'")
    if not ws:
        print(f'ERROR: workspace {WORKSPACE_ID} not found. Run seed-demo.sh first.')
        sys.exit(1)
    print(f'Seeding KB for workspace: {ws} ({WORKSPACE_ID})\n')

    total_chunks = 0
    for doc in SAMPLES:
        print(f'  Document: {doc["title"]}')

        # Insert or find document
        src_url = f"'{ pg_escape(doc['source_url']) }'" if doc['source_url'] else 'NULL'
        doc_id = psql(f"""
INSERT INTO documents (workspace_id, source_type, title, source_url, content)
VALUES ('{WORKSPACE_ID}'::uuid, '{doc['source_type']}',
        '{pg_escape(doc['title'])}', {src_url},
        '{pg_escape(doc['chunks'][0][1][:200])}...')
ON CONFLICT DO NOTHING
RETURNING id::text;
""")
        if not doc_id:
            # Already exists, fetch it
            doc_id = psql(f"""
SELECT id::text FROM documents
WHERE workspace_id = '{WORKSPACE_ID}'::uuid
  AND title = '{pg_escape(doc['title'])}'
LIMIT 1""")

        for idx, (heading, content) in enumerate(doc['chunks']):
            text_to_embed = f'{heading}\n\n{content}'
            print(f'    Chunk {idx}: {heading[:50]}... ', end='', flush=True)
            vec = embed(text_to_embed)
            psql(f"""
INSERT INTO chunks (document_id, workspace_id, chunk_index, content, embedding)
VALUES ('{doc_id}'::uuid, '{WORKSPACE_ID}'::uuid,
        {idx}, '{pg_escape(content)}', '{vec}'::vector)
ON CONFLICT DO NOTHING""")
            print('OK')
            total_chunks += 1

    print(f'\nSeeded {total_chunks} chunks across {len(SAMPLES)} documents.')
    print('Test with:')
    print(f'  curl -s http://localhost:5678/webhook/tool-search-kb \\')
    print(f'       -H "Content-Type: application/json" \\')
    print(f'       -d \'{{"query": "what is the PTO policy"}}\' | python3 -m json.tool')


if __name__ == '__main__':
    main()
