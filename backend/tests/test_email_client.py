import logging

import pytest

from app.email.client import EmailDeliveryError, send_email


def test_logs_instead_of_sending_when_smtp_host_is_not_configured(app, caplog):
    """TestingConfig forces SMTP_HOST="" regardless of .env, so this is
    the path every other test in this suite exercises by default - a
    real network send must never happen during the test run."""
    with app.app_context():
        with caplog.at_level(logging.INFO):
            send_email(to="someone@example.com", subject="Hello", body="World")

    assert any("someone@example.com" in record.message for record in caplog.records)


def test_raises_email_delivery_error_when_the_smtp_server_is_unreachable(app):
    """No real SMTP server is reachable in this dev environment (same
    gap documented for Docker/Redis) - pointing at a closed port
    confirms send_email translates the resulting connection failure into
    EmailDeliveryError rather than letting a raw socket exception escape."""
    app.config["SMTP_HOST"] = "127.0.0.1"
    app.config["SMTP_PORT"] = 1  # reliably refused - no service binds port 1 without root

    with app.app_context():
        with pytest.raises(EmailDeliveryError):
            send_email(to="someone@example.com", subject="Hello", body="World")
