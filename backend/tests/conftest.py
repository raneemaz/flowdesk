import pytest

from app import create_app
from app.extensions import db


@pytest.fixture
def app():
    """Every test gets its own fresh Flask app (and therefore its own
    SQLAlchemy engine/connection pool, bound via db.init_app(app) inside
    create_app) - simplest possible test isolation, but with ~270+ tests
    each opening up to pool_size + max_overflow (5 + 10 = 15)
    connections and relying on Python GC to eventually dispose the old
    engine, connections accumulated faster than Postgres's
    max_connections (100) could absorb across a full suite run -
    producing nondeterministic deadlocks/FK violations/"row not found"
    errors confirmed via pg_stat_activity, not any bug in the code under
    test. db.session.remove() cleanly returns this test's connection to
    its pool before db.engine.dispose() closes every connection in that
    pool outright, so at most one test's worth of connections is ever
    open at a time, deterministically, regardless of GC timing."""
    app = create_app("testing")
    yield app
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


@pytest.fixture
def client(app):
    return app.test_client()
