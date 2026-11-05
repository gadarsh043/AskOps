#!/usr/bin/env bash
# Open psql on the app database as the same least-privilege role n8n uses.
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose exec postgres sh -c 'PGPASSWORD="$APP_DB_PASSWORD" psql -h localhost -U askops_app -d askops'
