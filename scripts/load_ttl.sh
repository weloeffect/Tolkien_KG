#!/usr/bin/env bash
set -euo pipefail

TTL_FILE="${1:-kg/elrond.ttl}"
GRAPH_URI="${2:-http://localhost:8000/graph/main}"
GSP_ENDPOINT="${GSP_ENDPOINT:-http://localhost:3030/tolkien/data}"

curl -sS -X POST \
  -H "Content-Type: text/turtle" \
  --data-binary "@${TTL_FILE}" \
  "${GSP_ENDPOINT}?graph=${GRAPH_URI}"

echo "OK: appended ${TTL_FILE} into ${GRAPH_URI}"