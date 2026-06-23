#!/bin/sh
# Apply migrations (once) and seed (idempotent) against the db container.
set -e
export PGPASSWORD=postgres
PSQL="psql -h db -U postgres -v ON_ERROR_STOP=1 -q"

echo "waiting for db..."
until pg_isready -h db -U postgres >/dev/null 2>&1; do sleep 2; done
# the supabase image bounces postgres once during first-boot init; let it settle
sleep 4
until pg_isready -h db -U postgres >/dev/null 2>&1; do sleep 2; done

if $PSQL -tAc "select to_regclass('public.works')" | grep -q works; then
  echo "migrations already applied, skipping"
else
  for f in $(ls /migrations/*.sql | sort); do
    echo "applying $(basename "$f")"
    $PSQL -f "$f"
  done
fi

echo "seeding"
$PSQL -f /seed.sql
echo "migrate + seed complete"
