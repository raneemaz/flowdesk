"""Shared Flask extension instances, initialized against the app in create_app()."""
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_session import Session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import MetaData

# Alembic's own recommended naming convention, so every constraint/index
# gets a deterministic name autogenerate can reliably diff and reference.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

db = SQLAlchemy(metadata=MetaData(naming_convention=NAMING_CONVENTION))
migrate = Migrate()
sess = Session()

# FD-064 (Section 13's "auth rate limiting" item). Per-IP, backed by the
# same Redis instance already used for sessions (RATELIMIT_STORAGE_URI,
# set per-config in app/config.py) rather than Limiter's own in-memory
# default - an in-memory store would reset every limit on every worker
# process restart and never share counts across multiple app workers,
# making the limit trivially bypassable in any real multi-process
# deployment. No default limit is applied here (`default_limits=[]`,
# implicit) - only the specific auth routes that opt in via `@limiter.limit(...)`
# are throttled, never a blanket limit on every route.
limiter = Limiter(key_func=get_remote_address)

# FD-065: the frontend (Vercel) and backend (Render) are separate
# origins in production, unlike local dev where Vite's own proxy
# (vite.config.ts) makes every request same-origin from the browser's
# point of view - a real cross-origin deployment needs actual CORS
# headers, which nothing in this codebase set before this task.
# `supports_credentials=True` is required for the session cookie to be
# sent/received cross-site at all; paired with SESSION_COOKIE_SAMESITE=
# "None" (required in that env, see app/config.py) once genuinely
# cross-site. Scoped to API_PREFIX only, never a wildcard origin (which
# the browser rejects outright alongside credentials=true anyway) -
# config.py's `FRONTEND_URL` (already the one source of truth for "the
# frontend's own origin", previously only used to build invitation
# email links) is reused here rather than a second, near-duplicate env
# var for the same value.
cors = CORS()
