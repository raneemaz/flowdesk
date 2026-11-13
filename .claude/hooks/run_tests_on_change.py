#!/usr/bin/env python3
"""PostToolUse hook: after editing a backend Python file, run the most
relevant pytest module (falling back to the whole backend suite) so the
spec's "never mark complete without running tests" rule (Section 32) is
enforced automatically rather than relying on the agent remembering."""
import json
import os
import subprocess
import sys

PROJECT_DIR = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
BACKEND_DIR = os.path.join(PROJECT_DIR, "backend")

try:
    payload = json.load(sys.stdin)
except Exception:
    sys.exit(0)

tool_input = payload.get("tool_input", {}) or {}
path = tool_input.get("file_path") or tool_input.get("path") or ""

if not path.endswith(".py"):
    sys.exit(0)

norm = os.path.normpath(path)
is_backend_file = (
    (os.sep + "backend" + os.sep) in (os.sep + norm)
    or norm.startswith("backend" + os.sep)
)
if not is_backend_file:
    sys.exit(0)

if not os.path.isdir(BACKEND_DIR):
    sys.exit(0)  # backend not scaffolded yet (pre-FD-002) - nothing to run

tests_dir = os.path.join(BACKEND_DIR, "tests")
if not os.path.isdir(tests_dir):
    sys.exit(0)  # no test suite yet

# Try to map backend/app/<mod>/<file>.py -> backend/tests/<mod>/test_<file>.py
target = None
if os.path.isabs(path) and path.startswith(BACKEND_DIR):
    rel = os.path.relpath(path, BACKEND_DIR)
elif norm.startswith("backend" + os.sep):
    rel = os.path.relpath(norm, "backend")
else:
    rel = norm

parts = rel.split(os.sep)
if len(parts) >= 2 and parts[0] == "app":
    candidate_name = "test_" + parts[-1]
    candidate_dir = os.path.join(tests_dir, *parts[1:-1])
    candidate = os.path.join(candidate_dir, candidate_name)
    if os.path.isfile(candidate):
        target = candidate

cmd = ["python", "-m", "pytest", "-q"]
if target:
    cmd.append(target)

try:
    result = subprocess.run(
        cmd, cwd=BACKEND_DIR, capture_output=True, text=True, timeout=120
    )
except Exception as e:
    print("Could not run tests automatically: {}".format(e), file=sys.stderr)
    sys.exit(0)  # don't block the edit just because the runner itself failed

output = (result.stdout or "") + (result.stderr or "")
if result.returncode != 0:
    print(
        "Tests failed after this edit - fix before considering the task done:\n"
        + output[-4000:],
        file=sys.stderr,
    )
else:
    print("Tests passed: {}".format(" ".join(cmd)), file=sys.stderr)

sys.exit(0)
