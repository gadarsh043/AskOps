#!/usr/bin/env bash
# Expose local n8n to the internet (needed for Copilot Studio and approval emails).
# Free, no account. The URL changes each run: copy it into WEBHOOK_URL in .env,
# then `docker compose up -d n8n` to apply.
set -euo pipefail
command -v cloudflared >/dev/null || { echo "Install first: brew install cloudflared"; exit 1; }
cloudflared tunnel --url http://localhost:5678
