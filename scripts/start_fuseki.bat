@echo off
IF NOT EXIST tools\fuseki\ (
  echo Fuseki not found in tools\fuseki
  echo Run scripts\setup_fuseki.sh (or download manually) and extract into tools\fuseki
  exit /b 1
)

tools\fuseki\fuseki-server.bat --config fuseki\config.ttl