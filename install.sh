#!/usr/bin/env bash
set -euo pipefail

DB_NAME="upravljanje_najmovima"
APP_DB_USER="app_user"
APP_DB_PASS="app_pass"
APP_HOST="127.0.0.1"
APP_PORT="5432"

SCHEMA_FILE="schema.sql"
SEED_FILE="unos_testnih_podataka.sql"

if [ ! -f "$SCHEMA_FILE" ]; then
  echo "Greska: ne postoji $SCHEMA_FILE u trenutnom direktoriju."
  exit 1
fi

echo "== Provjera paketa =="

if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update -y

  if ! command -v psql >/dev/null 2>&1; then
    sudo apt-get install -y postgresql postgresql-contrib
  fi

  if ! command -v python3 >/dev/null 2>&1; then
    sudo apt-get install -y python3 python3-venv python3-pip
  else
    sudo apt-get install -y python3-venv python3-pip
  fi
else
  echo "Upozorenje: apt-get nije dostupan. Preskacem instalaciju paketa."
fi

echo "== Pokretanje PostgreSQL servisa (ako je potrebno) =="
if command -v systemctl >/dev/null 2>&1; then
  sudo systemctl enable postgresql >/dev/null 2>&1 || true
  sudo systemctl start postgresql >/dev/null 2>&1 || true
fi

echo "== Kreiranje role i baze (ako ne postoje) =="

sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${APP_DB_USER}') THEN
    CREATE ROLE ${APP_DB_USER} LOGIN PASSWORD '${APP_DB_PASS}';
  END IF;
END
\$\$;

DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = '${DB_NAME}') THEN
    CREATE DATABASE ${DB_NAME};
  END IF;
END
\$\$;

GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${APP_DB_USER};
SQL

echo "== Ucitavanje sheme: ${SCHEMA_FILE} =="
sudo -u postgres psql -v ON_ERROR_STOP=1 -d "${DB_NAME}" -f "${SCHEMA_FILE}"

if [ -f "$SEED_FILE" ]; then
  echo "== Ucitavanje testnih podataka: ${SEED_FILE} =="
  sudo -u postgres psql -v ON_ERROR_STOP=1 -d "${DB_NAME}" -f "${SEED_FILE}"
else
  echo "== Seed datoteka nije pronadena (${SEED_FILE}) - preskacem. =="
fi

echo "== Kreiranje .env (ako ne postoji) =="
if [ ! -f ".env" ]; then
  cat > .env <<EOF
DB_HOST=${APP_HOST}
DB_PORT=${APP_PORT}
DB_NAME=${DB_NAME}
DB_USER=${APP_DB_USER}
DB_PASSWORD=${APP_DB_PASS}
FLASK_ENV=development
EOF
fi

echo "== Python virtualenv (ako postoji aplikacija) =="
if [ -d "app" ] && [ -f "app/app.py" ]; then
  if [ ! -d ".venv" ]; then
    python3 -m venv .venv
  fi
  . .venv/bin/activate
  python -m pip install --upgrade pip >/dev/null
  if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
  else
    pip install flask psycopg2-binary python-dotenv
  fi
  deactivate
fi

echo
echo "== Gotovo =="
echo "Baza: ${DB_NAME}"
echo "Korisnik baze: ${APP_DB_USER}"
echo
echo "Pokretanje aplikacije:"
echo "  source .venv/bin/activate"
echo "  export \$(cat .env | xargs)"
echo "  python app/app.py"
echo
echo "Zatim otvori: http://localhost:5000"
