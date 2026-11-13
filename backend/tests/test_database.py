from sqlalchemy import text

from app.extensions import db


def test_database_connection_executes_a_query(app):
    with app.app_context():
        result = db.session.execute(text("SELECT 1")).scalar()

    assert result == 1


def test_sessions_are_isolated_per_app_context(app):
    with app.app_context():
        first_session = db.session
        assert first_session.execute(text("SELECT 1")).scalar() == 1

    with app.app_context():
        second_session = db.session
        assert second_session.execute(text("SELECT 1")).scalar() == 1


def test_engine_pooling_options_are_applied(app):
    with app.app_context():
        assert db.engine.pool.size() == app.config["SQLALCHEMY_ENGINE_OPTIONS"]["pool_size"]
