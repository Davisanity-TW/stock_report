#!/usr/bin/env bash
set -euo pipefail

# Supabase keepalive ping (Edge Function)
# Reads publishable key from workspace secrets to avoid hardcoding.

PROJECT_URL="https://whjkvgjihtnvcgtsygst.supabase.co"
FUNCTION_NAME="telegram-add-item"   # Existing deployed Edge Function (used as keepalive ping)

KEY_FILE="/home/ubuntu/clawd/secrets/supabase_publishable_key.txt"

if [[ ! -f "$KEY_FILE" ]]; then
  echo "Missing key file: $KEY_FILE" >&2
  exit 1
fi

ANON_KEY="$(tr -d '\n' < "$KEY_FILE")"

URL="$PROJECT_URL/functions/v1/$FUNCTION_NAME"

# Default to GET; adjust to POST if your function expects it.
curl -fsS -X GET \
  -H "Authorization: Bearer $ANON_KEY" \
  -H "apikey: $ANON_KEY" \
  "$URL" \
  >/dev/null

echo "OK: pinged $URL"
