"""Shared Flask extension instances, initialized against the app in create_app()."""
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
