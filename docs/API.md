# FlowDesk API Conventions

This is the human-readable companion to the contract in
[`backend/openapi.yaml`](../backend/openapi.yaml), served live at
`GET /api/v1/openapi.json` (interactive docs at `GET /api/v1/docs`).
Update **both** whenever an endpoint is added or changed — mandatory rule
#6 in the specification (Section 32).

## Versioning

All endpoints are path-versioned under `/api/v1`. Non-breaking additions
(new optional fields, new endpoints) stay on `v1`. A breaking change
(removing/renaming a field, changing a status code's meaning) gets a new
`/api/v2` prefix rather than silently changing `v1`'s behavior — see
Section 32 mandatory rule #9 ("preserve backward compatibility when
modifying existing endpoints").

## Response envelope

Every response uses one of two shapes, established in FD-002.

**Success:**

```json
{
  "success": true,
  "message": "Task created successfully",
  "data": { "id": "uuid", "title": "Prepare monthly report" }
}
```

**Error** (hybrid shape, chosen in FD-002 to reconcile the spec's two
conflicting examples — see `app/errors.py`):

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Validation failed",
    "details": { "due_date": "Due date cannot be earlier than start date" }
  }
}
```

Route/service code raises `app.errors.APIError(message, status_code, code, details)`
for expected, user-facing failures. Unhandled exceptions and standard
HTTP errors (404, 405, etc.) are converted to this same shape
automatically by the central error handlers — never build an error
response by hand.

## Pagination

Not demonstrated on a real endpoint yet (no list endpoints exist until
FD-008+), but established here so every future list endpoint is
consistent from the start.

List endpoints accept `page` (default `1`) and `per_page` (default `20`,
max `100`) query params, plus endpoint-specific `sort` and filter params.
The response adds a `meta` object alongside `data`:

```json
{
  "success": true,
  "message": "Tasks retrieved",
  "data": [ { "id": "uuid", "title": "..." } ],
  "meta": { "page": 1, "per_page": 20, "total": 134, "total_pages": 7 }
}
```

## Status codes

| Code | Meaning |
|---|---|
| 200 | Read/update success |
| 201 | Created |
| 204 | Success, no body |
| 400 | Malformed input |
| 401 | Unauthenticated |
| 403 | Authenticated but unauthorized |
| 404 | Missing or inaccessible (including cross-tenant records — never 403, to avoid confirming existence) |
| 405 | Method not allowed |
| 409 | Conflict |
| 422 | Semantic validation failure |
| 500 | Unexpected server error (never leaks internals — NFR-007) |

## Authentication

Not yet implemented (FD-009/FD-010). This section will be filled in once
the session/cookie mechanism is decided (spec Section 35, open decision
#3) and built.

## Current endpoints

| Method | Path | Purpose | Added in |
|---|---|---|---|
| GET | `/api/v1/health` | Liveness + DB connectivity check | FD-002, FD-004 |
| GET | `/api/v1/openapi.json` | This contract, as JSON | FD-007 |
| GET | `/api/v1/docs` | Interactive Swagger UI | FD-007 |

See `backend/openapi.yaml` for the full machine-readable contract.
