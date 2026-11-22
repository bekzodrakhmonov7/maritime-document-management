#!/usr/bin/env bash
# Run a SQL file one statement at a time with `supabase db query` (which takes
# one statement per call; each goes through a temp file because npx on Windows
# cuts a multi-line argument). Usage: run_sql_statements.sh <file.sql> --local|--linked
set -euo pipefail
file=$1; target=$2
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
python - "$file" "$tmp" <<'PY'
import pathlib, re, sys
text = re.sub(r"--[^\n]*", "", pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
parts = [s.strip() for s in text.split(";") if s.strip()]
for i, s in enumerate(parts):
    pathlib.Path(sys.argv[2], f"{i:04d}.sql").write_text(s + "\n", encoding="utf-8")
PY
for f in "$tmp"/*.sql; do
  out=$(npx --yes supabase@2.122.1 db query "$target" -f "$f" 2>&1 | grep -v "new version\|recommend\|Initialising\|Connecting" || true)
  if grep -q '"_tag":"Error"' <<<"$out"; then echo "FAILED: $(head -c 80 "$f")"; echo "$out"; exit 1; fi
  echo "ok: $(head -c 60 "$f" | tr '\r\n' '  ')"
done
