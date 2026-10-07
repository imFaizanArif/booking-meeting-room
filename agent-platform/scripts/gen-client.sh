#!/usr/bin/env bash
# Regenerate the TypeScript API client from the FastAPI OpenAPI schema.
# --check: fail if the committed client is out of date (used in CI).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/packages/api-client/src"
TMP="$(mktemp -d)"
(cd "$ROOT/apps/api" && SEED_DEMO=false uv run --quiet python -c \
  "import json; from app.main import app; print(json.dumps(app.openapi(), indent=2, sort_keys=True))") > "$TMP/openapi.json"
(cd "$ROOT/packages/api-client" && npx --no-install openapi-typescript "$TMP/openapi.json" --default-non-nullable false -o "$TMP/schema.ts" >/dev/null)
if [[ "${1:-}" == "--check" ]]; then
  if ! diff -q "$TMP/openapi.json" "$OUT/openapi.json" >/dev/null || ! diff -q "$TMP/schema.ts" "$OUT/schema.ts" >/dev/null; then
    echo "API client is out of date. Run: pnpm gen:client" >&2
    exit 1
  fi
  echo "API client is up to date."
else
  cp "$TMP/openapi.json" "$OUT/openapi.json"
  cp "$TMP/schema.ts" "$OUT/schema.ts"
  echo "Generated $OUT/schema.ts"
fi
rm -rf "$TMP"
