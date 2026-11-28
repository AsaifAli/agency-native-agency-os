#!/bin/sh
# Claude Code HTTP MCP headersHelper. Store the machine credential in macOS
# Keychain as a generic password with service "agency-os-mcp" and account
# equal to the current macOS username. This script never reads repository .env files.
set -eu

if ! command -v /usr/bin/security >/dev/null 2>&1; then
  echo "macOS Keychain security command is unavailable" >&2
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required to emit MCP headers JSON" >&2
  exit 1
fi

TOKEN=$(/usr/bin/security find-generic-password \
  -a "${USER:?USER is required}" \
  -s "agency-os-mcp" \
  -w)
if [ -z "$TOKEN" ]; then
  echo "Agency OS MCP credential is missing from macOS Keychain" >&2
  exit 1
fi

printf '%s' "$TOKEN" | python3 -c '
import json
import sys

token = sys.stdin.read().strip()
if not token:
    raise SystemExit("Agency OS MCP credential is empty")
print(json.dumps({"Authorization": "Bearer " + token}))
'
unset TOKEN
