import os

from alembic.runtime.migration import MigrationContext
from flask_migrate import downgrade, upgrade

from app.extensions import NAMING_CONVENTION, db

MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "migrations")


def _current_revision():
    with db.engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def test_upgrade_head_applies_the_baseline_revision(app):
    with app.app_context():
        downgrade(directory=MIGRATIONS_DIR, revision="base")
        upgrade(directory=MIGRATIONS_DIR, revision="head")

        assert _current_revision() is not None


def test_downgrade_base_clears_the_current_revision(app):
    with app.app_context():
        upgrade(directory=MIGRATIONS_DIR, revision="head")
        downgrade(directory=MIGRATIONS_DIR, revision="base")

        assert _current_revision() is None

        # Leave the database migrated for any other test run against it.
        upgrade(directory=MIGRATIONS_DIR, revision="head")


def test_metadata_uses_the_alembic_naming_convention():
    assert db.metadata.naming_convention == NAMING_CONVENTION
