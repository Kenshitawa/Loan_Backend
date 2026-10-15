#!/bin/sh
set -eu
: "${DATABASE_URL:=sqlite:///./mwangazabiz.db}"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p backups
case "$DATABASE_URL" in
  sqlite:///*) db=${DATABASE_URL#sqlite:///}; cp "$db" "backups/mwangazabiz-$stamp.db" ;;
  postgresql://*|postgresql+psycopg://*) pg_dump "$DATABASE_URL" > "backups/mwangazabiz-$stamp.sql" ;;
  *) echo "Unsupported DATABASE_URL" >&2; exit 1 ;;
esac
