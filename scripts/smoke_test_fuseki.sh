#!/usr/bin/env bash
set -euo pipefail

ENDPOINT="http://localhost:3030/tolkien/sparql"

curl -sG \
  --data-urlencode 'query=SELECT (1 as ?ok) WHERE {}' \
  "${ENDPOINT}" \
  -H 'Accept: application/sparql-results+json' | grep -q '"ok"'

echo "OK: Fuseki SPARQL endpoint is responding."