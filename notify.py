"""Send the weekly email over SMTP. Configured only through environment
variables (GitHub Actions secrets) - nothing sensitive lives in the repo.

  SMTP_HOST, SMTP_PORT (465 = SSL, 587 = STARTTLS), SMTP_USERNAME, SMTP_PASSWORD,
  REPORT_TO (comma separated), REPORT_FROM (optional, defaults to SMTP_USERNAME)
"""

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage

log = logging.getLogger(__name__)


def configured():
    return all(os.environ.get(k) for k in ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "REPORT_TO"))


def send(subject, html_body, text_body, attachments):
    """attachments: [(filename, bytes, maintype, subtype)]. Returns True if sent."""
    if not configured():
        log.warning("Email not sent: SMTP_* / REPORT_TO secrets are not set")
        return False
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT") or 465)
    user = os.environ["SMTP_USERNAME"]
    pwd = os.environ["SMTP_PASSWORD"]
    to = [a.strip() for a in os.environ["REPORT_TO"].split(",") if a.strip()]
    sender = os.environ.get("REPORT_FROM") or user

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(to)
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")
    for name, data, maintype, subtype in attachments:
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)

    ctx = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=60) as s:
            s.login(user, pwd)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=60) as s:
            s.starttls(context=ctx)
            s.login(user, pwd)
            s.send_message(msg)
    log.info("Email sent to %s", ", ".join(to))
    return True
