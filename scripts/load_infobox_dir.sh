#!/usr/bin/env bash
set -euo pipefail

DIR="${1:-kg/infobox_templates}"
GRAPH_URI="${2:-http://localhost:8000/graph/main}"

# reset once
./scripts/reset_graph.sh "${GRAPH_URI}"

for f in "$DIR"/*.ttl; do
  echo "Loading $f"
  ./scripts/load_ttl.sh "$f" "${GRAPH_URI}"
done

echo "OK: loaded all TTLs from ${DIR} into ${GRAPH_URI}"