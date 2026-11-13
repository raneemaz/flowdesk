#!/usr/bin/env python3
"""PreToolUse hook: block edits to a real .env file (never .env.example).
Enforces FlowDesk spec NFR-013: secrets live in environment variables /
secret management only, never committed or hand-edited by the agent."""
import json
import os
import sys

try:
    payload = json.load(sys.stdin)
except Exception:
    sys.exit(0)  # don't block on malformed input we can't parse

tool_input = payload.get("tool_input", {}) or {}
path = tool_input.get("file_path") or tool_input.get("path") or ""
base = os.path.basename(path)

if base == ".env" or (base.startswith(".env.") and not base.endswith(".example")):
    print(
        "Blocked: '{}' looks like a real secrets file (.env), not .env.example. "
        "Per NFR-013, secrets live in environment variables / secret management "
        "only - edit .env.example with placeholder names instead, or ask the "
        "user to edit the real .env themselves.".format(path),
        file=sys.stderr,
    )
    sys.exit(2)

sys.exit(0)
