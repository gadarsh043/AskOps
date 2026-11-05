#!/bin/bash
# Runs once, on the first start of an empty Postgres volume.
# To re-run: docker compose down -v && docker compose up -d   (this wipes local data)
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -c "CREATE DATABASE askops;"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname askops \
  -v app_password="$APP_DB_PASSWORD" -f /askops-db/roles.sql

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname askops \
  -f /askops-db/schema.sql

echo "askops database ready"
