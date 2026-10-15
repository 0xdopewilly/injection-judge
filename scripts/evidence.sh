#!/usr/bin/env bash
# Runs one write through scripts/tx.mjs and appends the labelled result to an evidence log.
#
#   scripts/evidence.sh <log.jsonl> <label> <contract> <method> [args...]
set -uo pipefail
cd "$(dirname "$0")/.."
log="$1"; label="$2"; contract="$3"; shift 3
out=$(node scripts/tx.mjs write "$contract" "$@" 2>&1 | tail -1)
printf '%s' "$out" | python3 -I -c '
import json, sys, time
label, method = sys.argv[1], sys.argv[2]
try:
    result = json.loads(sys.stdin.read())
except ValueError:
    result = {"ok": False, "error": "unparseable tx.mjs output"}
record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "label": label, "method": method}
record.update({k: result.get(k) for k in ("ok", "hash", "status", "execution", "votes", "returned", "error") if k in result})
print(json.dumps(record, ensure_ascii=False))
' "$label" "$1" | tee -a "$log"
