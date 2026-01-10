#!/usr/bin/env bash
set -euo pipefail

FUSEKI_VERSION="5.6.0"
ARCHIVE="apache-jena-fuseki-${FUSEKI_VERSION}.zip"
URL="https://archive.apache.org/dist/jena/binaries/${ARCHIVE}"

mkdir -p tools
cd tools

if [ -d "fuseki" ]; then
  echo "tools/fuseki already exists. Nothing to do."
  exit 0
fi

echo "Downloading Fuseki ${FUSEKI_VERSION}..."
curl -L -o "${ARCHIVE}" "${URL}"

echo "Extracting..."
tar -xzf "${ARCHIVE}"
rm "${ARCHIVE}"

mv "apache-jena-fuseki-${FUSEKI_VERSION}" fuseki
echo "OK: tools/fuseki installed."