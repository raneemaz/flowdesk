# FlowDesk Backend

Flask API for FlowDesk. Domain modules (auth, organizations, employees,
tasks, etc.) are added incrementally per the backlog in
[`docs/FlowDesk_Specification.md`](../docs/FlowDesk_Specification.md);
only the application skeleton exists so far (FD-002).

## Structure

```
backend/
  wsgi.py              Entry point (`app = create_app()`)
  app/
    __init__.py        Application factory, blueprint registration
    config.py           Per-environment config (FLASK_ENV: development/testing/production)
    errors.py            APIError + central error handlers (hybrid envelope)
    health/              GET /api/v1/health
  tests/                 Pytest suite
```

## Response envelope

Success: `{"success": true, "message": "...", "data": {...}}`

Error: `{"success": false, "error": {"code": "...", "message": "...", "details": {...}}}`

Route/service code should raise `app.errors.APIError(message, status_code, code, details)`
for expected, user-facing failures rather than building a JSON response by hand.
Unhandled exceptions and standard HTTP errors (404, 405, etc.) are converted
to the same envelope automatically.

## Setup

```bash
cd backend
py -3.12 -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
```

Copy the root `.env.example` to `.env` (at the project root) and adjust as
needed; `python-dotenv` loads it automatically.

## Running

```bash
FLASK_ENV=development ./.venv/Scripts/python.exe -m flask --app wsgi run
```

## Testing

```bash
FLASK_ENV=testing ./.venv/Scripts/python.exe -m pytest -v
```
