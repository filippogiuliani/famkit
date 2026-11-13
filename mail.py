"""Sending email over SMTP ({PREFIX}_SMTP_HOST, _SMTP_PORT, _SMTP_USER, _SMTP_PASSWORD, _MAIL_FROM).
Without SMTP the emails are only written to the log: handy during development."""
import smtplib
import ssl
import threading
from email.message import EmailMessage

from . import config

SMTP_HOST = SMTP_USER = SMTP_PASSWORD = SENDER = ''
SMTP_PORT = 587


def load():
    global SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SENDER
    SMTP_HOST = config.env('SMTP_HOST')
    SMTP_PORT = int(config.env('SMTP_PORT', '587'))
    SMTP_USER = config.env('SMTP_USER')
    SMTP_PASSWORD = config.env('SMTP_PASSWORD')
    SENDER = config.env('MAIL_FROM', f'{config.NAME} <noreply@localhost>')


def _send(to, subject, body):
    msg = EmailMessage()
    msg['From'], msg['To'], msg['Subject'] = SENDER, to, subject
    msg.set_content(body)
    try:
        if SMTP_PORT == 465:
            server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ssl.create_default_context(), timeout=20)
        else:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20)
            server.starttls(context=ssl.create_default_context())
        with server:
            if SMTP_USER:
                server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
    except Exception as e:  # a failure must not break the request
        print(f'[mail] sending to {to} failed: {e}', flush=True)


def send(to, subject, body):
    if not SMTP_HOST:
        print(f'[mail] (SMTP not configured) To: {to} | {subject}\n{body}\n', flush=True)
        return
    threading.Thread(target=_send, args=(to, subject, body), daemon=True).start()
