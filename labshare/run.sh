#!/usr/bin/env bash
# Run LabShare locally with gunicorn (same server Render uses).
cd "$(dirname "$0")"
[ -f .env ] || { echo "No .env found - run ./setup.sh first."; exit 1; }
set -a; . ./.env; set +a
echo "LabShare running at http://localhost:${PORT:-5000}"
exec ./venv/bin/gunicorn app:app --workers 1 --threads 4 --timeout 120 --bind 0.0.0.0:${PORT:-5000}
