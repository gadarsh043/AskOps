#!/usr/bin/env bash
# Load (or reset) the Northwind Labs demo workspace with the Adarsh / John personas.
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d askops' < db/seed_demo.sql
echo "Demo workspace loaded. Active persona: Adarsh Gella."
