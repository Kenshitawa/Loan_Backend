#!/bin/sh
set -eu
if [ "$#" -ne 1 ]; then echo "Usage: restore.sh BACKUP_FILE" >&2; exit 2; fi
: "${DATABASE_URL:=sqlite:///./mwangazabiz.db}"
case "$DATABASE_URL" in
  sqlite:///*) db=${DATABASE_URL#sqlite:///}; cp "$1" "$db" ;;
  postgresql://*|postgresql+psycopg://*) psql "$DATABASE_URL" < "$1" ;;
  *) echo "Unsupported DATABASE_URL" >&2; exit 1 ;;
esac
