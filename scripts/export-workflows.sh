#!/usr/bin/env bash
# Export all n8n workflows to n8n/workflows/<name>.json via the REST API.
# Requires N8N_API_URL and N8N_API_KEY in .env.
set -euo pipefail
cd "$(dirname "$0")/.."

set -a; [ -f .env ] && source .env; set +a

: "${N8N_API_URL:?Set N8N_API_URL in .env}"
: "${N8N_API_KEY:?Set N8N_API_KEY in .env (create in n8n UI: Settings → n8n API → Create key)}"

mkdir -p n8n/workflows

python3 - <<'PYEOF'
import os, json, re, urllib.request

base = os.environ["N8N_API_URL"]
key  = os.environ["N8N_API_KEY"]

def api_get(path):
    req = urllib.request.Request(f"{base}{path}", headers={"X-N8N-API-KEY": key})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

data = api_get("/api/v1/workflows?limit=250")
workflows = data.get("data", [])

for w in workflows:
    slug = re.sub(r"[^a-zA-Z0-9._-]", "_", w["name"]).strip("_") or "workflow"
    path = f"n8n/workflows/{slug}.json"
    with open(path, "w") as f:
        json.dump(w, f, indent=2)
    print(f"  {path}")

print(f"\nExported {len(workflows)} workflow(s) to n8n/workflows/. Review the diff and commit.")
PYEOF
