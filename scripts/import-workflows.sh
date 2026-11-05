#!/usr/bin/env bash
# Import workflows from n8n/workflows/*.json into n8n via the REST API.
# Creates new workflows or updates existing ones matched by name.
# Requires N8N_API_URL and N8N_API_KEY in .env.
set -euo pipefail
cd "$(dirname "$0")/.."

set -a; [ -f .env ] && source .env; set +a

: "${N8N_API_URL:?Set N8N_API_URL in .env}"
: "${N8N_API_KEY:?Set N8N_API_KEY in .env (create in n8n UI: Settings → n8n API → Create key)}"

python3 - <<'PYEOF'
import os, sys, json, urllib.request, urllib.error
from pathlib import Path

base = os.environ["N8N_API_URL"]
key  = os.environ["N8N_API_KEY"]
headers = {"X-N8N-API-KEY": key, "Content-Type": "application/json"}

def api(method, path, body=None):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(f"{base}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"  ERROR {e.code}: {e.read().decode()}", file=sys.stderr)
        return None

existing = {w["name"]: w["id"] for w in api("GET", "/api/v1/workflows?limit=250").get("data", [])}

files = sorted(Path("n8n/workflows").glob("*.json"))
if not files:
    print("No JSON files in n8n/workflows/. Nothing to import.")
    sys.exit(0)

created = updated = failed = 0
for f in files:
    workflow = json.loads(f.read_text())
    name = workflow.get("name", f.stem)
    for field in ("id", "versionId", "createdAt", "updatedAt"):
        workflow.pop(field, None)

    if name in existing:
        result = api("PUT", f"/api/v1/workflows/{existing[name]}", workflow)
        if result:
            print(f"  updated  {name}")
            updated += 1
        else:
            failed += 1
    else:
        result = api("POST", "/api/v1/workflows", workflow)
        if result:
            print(f"  created  {name}")
            created += 1
        else:
            failed += 1

print(f"\nImported: {created} created, {updated} updated, {failed} failed.")
print("Re-link credentials in the n8n UI if any node shows a warning.")
PYEOF
