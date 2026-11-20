"""FD-059: Celery app factory + the one scheduled job registration
(Section 14: "Weekly business/AI summary | Once per week, per
organization, in the org's own timezone"). Follows Flask's own
recommended Celery integration pattern (`celery_init_app`, Celery
5.3+'s `Task` subclassing) - every task runs inside a real Flask app
context, so `current_app`/`db`/config are always available the same
way they are in an HTTP request.

This is the Celery equivalent of `wsgi.py` - a separate entry point,
never imported by the Flask app itself (`app/__init__.py` never
imports this module, the same way `wsgi.py` is never imported by
anything either). Two separate long-running processes read it, read
by the `celery` CLI, not run directly:

    celery -A app.celery_app.celery_app worker --loglevel=info
    celery -A app.celery_app.celery_app beat --loglevel=info

(see `backend/README.md`'s own "Running" section for the full setup,
including the "no real Redis in this dev environment" gap this
shares with every other FD-006-dependent feature in this project).

The actual per-organization logic (`run_due_weekly_reports`, Section
35 open decision #11's resolution) lives in `app.ai_reports.tasks` as
a plain, Celery-free function - this module only wraps it in the one
`@celery_app.task` Beat actually schedules, so that function stays
directly unit-testable with no Celery/broker involved at all, and so
no test ever needs to import *this* module (which eagerly builds its
own separate Flask app at import time - importing it from a test
process would create a second, differently-configured app and is
deliberately avoided everywhere in this codebase's test suite)."""

from celery import Celery, Task
from celery.schedules import crontab

from app import create_app


def celery_init_app(app) -> Celery:
    class FlaskTask(Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery_app = Celery(app.name, task_cls=FlaskTask)
    celery_app.config_from_object(
        {
            "broker_url": app.config["CELERY_BROKER_URL"],
            "result_backend": app.config["CELERY_RESULT_BACKEND"],
            "task_ignore_result": True,
            "timezone": "UTC",
            "beat_schedule": {
                "generate-weekly-ai-reports": {
                    "task": "generate_weekly_reports_task",
                    # Every hour, on the hour, in UTC - app.ai_reports.tasks
                    # checks each organization's own LOCAL time against
                    # Monday 06:00 itself; this single fixed-UTC cadence is
                    # what makes "per-organization timezone" scheduling
                    # work with one Beat entry (Section 35 open decision
                    # #11), rather than needing one schedule entry per
                    # timezone.
                    "schedule": crontab(minute=0),
                },
            },
        }
    )
    celery_app.set_default()
    app.extensions["celery"] = celery_app
    return celery_app


flask_app = create_app()
celery_app = celery_init_app(flask_app)


@celery_app.task(name="generate_weekly_reports_task")
def generate_weekly_reports_task():
    from app.ai_reports.tasks import run_due_weekly_reports

    run_due_weekly_reports()
