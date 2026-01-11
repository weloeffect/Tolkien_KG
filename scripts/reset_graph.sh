#!/usr/bin/env bash
set -euo pipefail

GRAPH_URI="${1:-http://localhost:8000/graph/main}"
GSP_ENDPOINT="${GSP_ENDPOINT:-http://localhost:3030/tolkien/data}"

# PUT with empty body resets/creates the graph
curl -sS -X PUT "${GSP_ENDPOINT}?graph=${GRAPH_URI}" >/dev/null

echo "OK: reset graph ${GRAPH_URI}"