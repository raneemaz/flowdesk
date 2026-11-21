"""Shared Flask extension instances, initialized against the app in create_app()."""
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
