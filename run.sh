#!/usr/bin/with-contenv bashio

export DATABASE_PATH="$(bashio::config 'database_path')"
export REACT_APP_AMAZON_EMAIL="$(bashio::config 'amazon_email')"
export REACT_APP_AMAZON_PASSWORD="$(bashio::config 'amazon_password')"
export REACT_APP_AMAZON_COUNTRY="$(bashio::config 'amazon_country')"

if [ -z "${DATABASE_PATH}" ] || [ "${DATABASE_PATH}" = "null" ]; then
  export DATABASE_PATH="/data/tasks.db"
fi

if [ -z "${REACT_APP_AMAZON_COUNTRY}" ] || [ "${REACT_APP_AMAZON_COUNTRY}" = "null" ]; then
  export REACT_APP_AMAZON_COUNTRY="co.uk"
fi

echo "Using database path: ${DATABASE_PATH}"

cd /app/backend

exec /app/backend/.venv/bin/uvicorn app.main:app \
  --app-dir /app/backend \
  --host 0.0.0.0 \
  --port 8000