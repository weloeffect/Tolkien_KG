#!/usr/bin/env bash
set -euo pipefail

TTL_FILE="${1:-kg/elrond.ttl}"
GRAPH_URI="http://localhost:8000/graph/main"
GSP_ENDPOINT="http://localhost:3030/tolkien/data"

curl -sS -X PUT \
  -H "Content-Type: text/turtle" \
  --data-binary "@${TTL_FILE}" \
  "${GSP_ENDPOINT}?graph=${GRAPH_URI}"

echo "OK: loaded ${TTL_FILE} into ${GRAPH_URI}"