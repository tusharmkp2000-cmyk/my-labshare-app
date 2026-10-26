#!/usr/bin/env bash
# One-time local setup: virtualenv, packages, and a .env with random secrets.
set -e
cd "$(dirname "$0")"

command -v python3 >/dev/null || { echo "Python 3 is required."; exit 1; }

echo "== 1/3 Creating virtualenv =="
python3 -m venv venv

echo "== 2/3 Installing packages =="
./venv/bin/pip install -q --upgrade pip
./venv/bin/pip install -q -r requirements.txt

echo "== 3/3 Writing .env =="
if [ -f .env ]; then
  echo ".env already exists - keeping it."
else
  SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
  PASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(12))")
  sed -e "s|^LABSHARE_SECRET=.*|LABSHARE_SECRET=$SECRET|" \
      -e "s|^ADMIN_PASSWORD=.*|ADMIN_PASSWORD=$PASS|" .env.example > .env
  chmod 600 .env
  echo "Admin password: $PASS   (saved in .env)"
fi
echo "Done. Start the app with:  ./run.sh"
