import smtplib, httpx
from email.mime.text import MIMEText
from email.utils import formataddr
from config import (GAS_WEB_APP_URL, EMAIL_BRIDGE_SECRET, GMAIL_USER,
                    MAIL_APP_PASSWORD, SENDER_NAME)

FOOTER_SL = ("\n\n—\n{name}\n"
             "To sporočilo ste prejeli kot poslovni kontakt. "
             "Če ne želite več prejemati sporočil, odgovorite z \"ODJAVA\".")

def _with_footer(body: str) -> str:
    return body + FOOTER_SL.format(name=SENDER_NAME)

def _send_gas(to: str, subject: str, body: str) -> tuple[bool, str]:
    try:
        r = httpx.post(GAS_WEB_APP_URL, timeout=45, json={
            "action": "send_email", "secret": EMAIL_BRIDGE_SECRET,
            "to": to, "subject": subject, "body": _with_footer(body)})
        r.raise_for_status()
        return r.json().get("ok", False), r.text
    except Exception as e:
        return False, f"GAS error: {e}"

def _send_smtp(to: str, subject: str, body: str) -> tuple[bool, str]:
    try:
        msg = MIMEText(_with_footer(body), "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = formataddr((SENDER_NAME, GMAIL_USER))
        msg["To"] = to
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(GMAIL_USER, MAIL_APP_PASSWORD)
            s.sendmail(GMAIL_USER, [to], msg.as_string())
        return True, "smtp ok"
    except Exception as e:
        return False, f"SMTP error: {e}"

def send_email(to: str, subject: str, body: str) -> tuple[bool, str]:
    if GAS_WEB_APP_URL and EMAIL_BRIDGE_SECRET:
        ok, info = _send_gas(to, subject, body)
        if ok:
            return True, "sent via GAS"
    if GMAIL_USER and MAIL_APP_PASSWORD:
        return _send_smtp(to, subject, body)
    return False, "no email transport configured"
