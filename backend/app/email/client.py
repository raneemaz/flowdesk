"""Real SMTP email delivery (FD-016), resolving Section 35 open decision
#4. SMTP was chosen over a vendor-specific SDK (SendGrid/SES/Resend) so
development and production run the exact same code path here - only the
SMTP_* env vars differ between them, with no provider SDK dependency to
swap or mock.

Not reachable from a real mail server in this dev environment (same gap
documented for Docker/Redis elsewhere in this project - see
backend/README.md): SMTP_HOST is unset here, so send_email logs instead
of connecting. Tests that need to assert on *what* would have been sent
inject a stub in place of this module's send_email (see
app.invitations.service.create_invitation's send_email_fn parameter),
the same dependency-injection pattern used for fakeredis elsewhere.
"""

import logging
import smtplib
from email.message import EmailMessage

from flask import current_app

logger = logging.getLogger(__name__)


class EmailDeliveryError(Exception):
    """The SMTP send itself failed. Callers decide whether that should
    block the overall operation - see app.invitations.service, which
    treats a failed send as best-effort (the invitation record is still
    created) rather than rolling back real business data because of an
    external mail server being unreachable."""


def send_email(*, to: str, subject: str, body: str) -> None:
    config = current_app.config
    host = config["SMTP_HOST"]

    if not host:
        # Dev-only fallback (mirrors a "console" mail backend): no
        # SMTP_HOST configured means log the message instead of
        # silently dropping it or opening a socket that was never
        # going to connect. ProductionConfig can never reach this
        # branch - app.create_app() refuses to start without
        # SMTP_HOST set when FLASK_ENV=production.
        logger.info("EMAIL (no SMTP_HOST configured) to=%s subject=%r\n%s", to, subject, body)
        return

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = config["EMAIL_FROM_ADDRESS"]
    message["To"] = to
    message.set_content(body)

    try:
        with smtplib.SMTP(host, config["SMTP_PORT"], timeout=10) as client:
            if config["SMTP_USE_TLS"]:
                client.starttls()
            username = config["SMTP_USERNAME"]
            password = config["SMTP_PASSWORD"]
            if username and password:
                client.login(username, password)
            client.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise EmailDeliveryError(str(exc)) from exc
