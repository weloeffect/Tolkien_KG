#!/usr/bin/env bash
set -euo pipefail

if [ ! -d "tools/fuseki" ]; then
  echo "Fuseki not found in tools/fuseki."
  echo "Run: ./scripts/setup_fuseki.sh"
  exit 1
fi

chmod +x tools/fuseki/fuseki-server || true

tools/fuseki/fuseki-server --config fuseki/config.ttl