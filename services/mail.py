"""Email sending helpers (SMTP / Flask-Mail / SocketLabs)."""
from __future__ import annotations

import os
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

from flask import current_app, url_for

def _get_mail_server():
    s = os.getenv('MAIL_SERVER') or os.getenv('EMAIL_SERVER', '')
    if s and 'outlook.office365.com' in s.lower():
        return 'smtp.office365.com'  # SMTP uses smtp., not outlook.
    return s or 'smtp.office365.com'


def _get_mail_user():
    return os.getenv('MAIL_USERNAME') or os.getenv('EMAIL_ADDRESS', '')


def _get_mail_password():
    return os.getenv('MAIL_PASSWORD') or os.getenv('EMAIL_PASSWORD', '')


try:
    from flask_mail import Mail, Message  # noqa: F401
    _socketlabs_user = os.getenv("SOCKETLABS_USERNAME", "")
    _socketlabs_pwd = os.getenv("SOCKETLABS_PASSWORD", "")
    MAIL_AVAILABLE = bool(
        ((_get_mail_user() and _get_mail_password()) or (_socketlabs_user and _socketlabs_pwd))
    )
    mail = None  # bound from app.py after Mail(app) init
except Exception:
    mail = None
    Message = None  # type: ignore
    MAIL_AVAILABLE = False


def bind_mail(mail_instance, available: bool | None = None) -> None:
    """Called from app.py after Flask-Mail is initialized."""
    global mail, MAIL_AVAILABLE
    mail = mail_instance
    if available is not None:
        MAIL_AVAILABLE = available


def onboarding_login_url():
    import app as main
    return main.onboarding_login_url()


def onboarding_tasks_url():
    import app as main
    return main.onboarding_tasks_url()


def normalize_email(email):
    import app as main
    return main.normalize_email(email)


def _log_exception_to_file(exc):
    import app as main
    return main._log_exception_to_file(exc)


def _ensure_users_must_change_password_column():
    from db.migrations_runtime import _ensure_users_must_change_password_column as _fn
    return _fn()


def send_email(to_email, subject, body_html, body_text=None):
    """Send email via SocketLabs SMTP (if configured) or Flask-Mail (MAIL_* / EMAIL_*)."""
    if not MAIL_AVAILABLE or not to_email or not to_email.strip():
        return False
    to_email = to_email.strip()
    plain = body_text if body_text is not None else body_html.replace('<br>', '\n').replace('</p>', '\n')

    # SocketLabs: smtplib to smtp.socketlabs.com, STARTTLS, login with server ID + password
    sock_server = os.getenv('SOCKETLABS_SERVER', 'smtp.socketlabs.com')
    sock_port = int(os.getenv('SOCKETLABS_PORT', '587'))
    sock_user = os.getenv('SOCKETLABS_USERNAME', '')
    sock_pwd = os.getenv('SOCKETLABS_PASSWORD', '')
    sock_sender = os.getenv('SOCKETLABS_SENDER_EMAIL', 'noreply@ziebart.com')

    if sock_user and sock_pwd:
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = sock_sender
            msg['To'] = to_email
            msg.attach(MIMEText(plain, 'plain'))
            msg.attach(MIMEText(body_html, 'html'))
            with smtplib.SMTP(sock_server, sock_port) as smtp:
                smtp.starttls()
                smtp.login(sock_user, sock_pwd)
                smtp.sendmail(sock_sender, [to_email], msg.as_string())
            return True
        except Exception as e:
            current_app.logger.warning(f"SocketLabs send failed to {to_email}: {e}")
            _log_exception_to_file(e)
            return False

    # Flask-Mail (MAIL_* / EMAIL_*)
    try:
        msg = Message(
            subject=subject,
            recipients=[to_email],
            body=plain,
            html=body_html
        )
        mail.send(msg)
        return True
    except Exception as e:
        current_app.logger.warning(f"Email send failed to {to_email}: {e}")
        try:
            log_path = BASE_DIR / 'logs' / 'error.log'
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write("send_email env: MAIL_SERVER=%r MAIL_USERNAME=%r MAIL_PASSWORD=%s\n" % (
                    current_app.config.get('MAIL_SERVER'), current_app.config.get('MAIL_USERNAME'),
                    'SET' if current_app.config.get('MAIL_PASSWORD') else 'NOT SET'))
        except Exception:
            pass
        _log_exception_to_file(e)
        return False


def _html_to_plain_fallback(body_html):
    """Lightweight HTML→plaintext conversion for email fallbacks.

    Removes leading indentation, replaces common block tags with newlines,
    strips remaining tags, and collapses excess blank lines so that mail clients
    that fall back to text/plain render something readable.
    """
    import re
    import textwrap
    text = textwrap.dedent(body_html or '').strip()
    # Replace <br> and </p> / </div> / </li> with newlines
    text = re.sub(r'(?i)<br\s*/?>', '\n', text)
    text = re.sub(r'(?i)</\s*(p|div|li|h[1-6]|tr)\s*>', '\n', text)
    # Convert list items roughly
    text = re.sub(r'(?i)<\s*li[^>]*>', '- ', text)
    # Strip remaining tags
    text = re.sub(r'<[^>]+>', '', text)
    # Decode the most common HTML entities
    text = (text
            .replace('&nbsp;', ' ')
            .replace('&amp;', '&')
            .replace('&lt;', '<')
            .replace('&gt;', '>')
            .replace('&quot;', '"')
            .replace('&#39;', "'"))
    # Collapse 3+ blank lines into 2 and dedent each line
    lines = [ln.strip() for ln in text.splitlines()]
    cleaned = []
    blank = 0
    for ln in lines:
        if not ln:
            blank += 1
            if blank > 1:
                continue
        else:
            blank = 0
        cleaned.append(ln)
    return '\n'.join(cleaned).strip() + '\n'


def generate_temporary_password(length=12):
    """Generate a random temporary password for email reset flows."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(max(8, length)))


def send_password_reset_email(user, temporary_password):
    """Email a temporary password and login instructions to the user."""
    to_email = normalize_email(getattr(user, 'email', None))
    if not to_email:
        return False
    login_url = onboarding_login_url()
    display_name = (getattr(user, 'full_name', None) or getattr(user, 'username', None) or '').strip() or 'there'
    subject = 'Your Ziebart Onboarding temporary password'
    body_html = f'''
    <p>Hello {display_name},</p>
    <p>An administrator sent you a temporary password for the Ziebart Onboarding portal.</p>
    <p><strong>Email:</strong> {to_email}<br>
    <strong>Temporary password:</strong> {temporary_password}</p>
    <p>Log in with the temporary password, then you will be prompted to choose a new password.</p>
    <p><a href="{login_url}">Log in to Ziebart Onboarding</a></p>
    <p>If the button does not work, copy and paste this link into your browser:<br>{login_url}</p>
    <p>If you did not expect this email, contact your manager or onboarding administrator.</p>
    <p>Thank you,<br>Onboarding Team</p>
    '''
    body_text = (
        f"Hello {display_name},\n\n"
        "An administrator sent you a temporary password for the Ziebart Onboarding portal.\n\n"
        f"Email: {to_email}\n"
        f"Temporary password: {temporary_password}\n\n"
        "Log in with the temporary password, then you will be prompted to choose a new password.\n\n"
        f"Log in here:\n{login_url}\n\n"
        "If you did not expect this email, contact your manager or onboarding administrator.\n\n"
        "Thank you,\n"
        "Onboarding Team"
    )
    return send_email(to_email, subject, body_html, body_text=body_text)


def send_onboarding_welcome_email(first_name, last_name, to_email, password):
    """Email new hire a get-started link plus login credentials after onboarding is created."""
    import html as html_module
    to_email = normalize_email(to_email)
    if not to_email or not password:
        return False
    login_url = onboarding_login_url()
    display_name = (f'{first_name or ""} {last_name or ""}').strip() or 'there'
    safe_name = html_module.escape(display_name)
    safe_email = html_module.escape(to_email)
    safe_password = html_module.escape(password)
    safe_login_url = html_module.escape(login_url, quote=True)
    subject = 'Welcome to Ziebart Onboarding - get started'
    # Table-based CTA: inline-block/button styles often fail in Outlook/desktop clients
    body_html = f'''
    <p>Hello {safe_name},</p>
    <p>Your Ziebart onboarding account is ready. Use the link below to log in and get started with your training and forms.</p>
    <p><strong>Email:</strong> {safe_email}<br>
    <strong>Password:</strong> {safe_password}</p>
    <table role="presentation" cellspacing="0" cellpadding="0" border="0" style="margin:16px 0;">
      <tr>
        <td align="center" bgcolor="#FE0100" style="background-color:#FE0100;border-radius:6px;">
          <a href="{safe_login_url}" target="_blank" style="display:inline-block;padding:12px 20px;font-family:Arial,Helvetica,sans-serif;font-size:16px;font-weight:bold;color:#ffffff;text-decoration:none;">Get started</a>
        </td>
      </tr>
    </table>
    <p><a href="{safe_login_url}" target="_blank">Or open the login page here</a></p>
    <p>If the links do not work, copy and paste this into your browser:<br>{html_module.escape(login_url)}</p>
    <p>If you have questions, contact your manager or onboarding administrator.</p>
    <p>Welcome aboard,<br>Onboarding Team</p>
    '''
    body_text = (
        f"Hello {display_name},\n\n"
        "Your Ziebart onboarding account is ready. Use the link below to log in and get started "
        "with your training and forms.\n\n"
        f"Email: {to_email}\n"
        f"Password: {password}\n\n"
        f"Get started:\n{login_url}\n\n"
        "If you have questions, contact your manager or onboarding administrator.\n\n"
        "Welcome aboard,\n"
        "Onboarding Team"
    )
    return send_email(to_email, subject, body_html, body_text=body_text)


def send_email_with_attachment(to_email, subject, body_html, attachment_filename, attachment_bytes, body_text=None):
    """Send email with a single PDF (or other) attachment. Uses same config as send_email."""
    if not MAIL_AVAILABLE or not to_email or not to_email.strip():
        return False
    to_email = to_email.strip()
    import textwrap
    body_html = textwrap.dedent(body_html or '').strip()
    plain = body_text if body_text is not None else _html_to_plain_fallback(body_html)

    sock_server = os.getenv('SOCKETLABS_SERVER', 'smtp.socketlabs.com')
    sock_port = int(os.getenv('SOCKETLABS_PORT', '587'))
    sock_user = os.getenv('SOCKETLABS_USERNAME', '')
    sock_pwd = os.getenv('SOCKETLABS_PASSWORD', '')
    sock_sender = os.getenv('SOCKETLABS_SENDER_EMAIL', 'noreply@ziebart.com')

    if sock_user and sock_pwd:
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            from email.mime.base import MIMEBase
            from email import encoders
            msg = MIMEMultipart('mixed')
            msg['Subject'] = subject
            msg['From'] = sock_sender
            msg['To'] = to_email
            alt = MIMEMultipart('alternative')
            alt.attach(MIMEText(plain, 'plain', 'utf-8'))
            alt.attach(MIMEText(body_html, 'html', 'utf-8'))
            msg.attach(alt)
            part = MIMEBase('application', 'pdf')
            part.set_payload(attachment_bytes)
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', 'attachment', filename=attachment_filename)
            msg.attach(part)
            with smtplib.SMTP(sock_server, sock_port) as smtp:
                smtp.starttls()
                smtp.login(sock_user, sock_pwd)
                smtp.sendmail(sock_sender, [to_email], msg.as_string())
            return True
        except Exception as e:
            current_app.logger.warning(f"SocketLabs send with attachment failed to {to_email}: {e}")
            _log_exception_to_file(e)
            return False

    try:
        from flask_mail import Message as MailMessage
        msg = MailMessage(
            subject=subject,
            recipients=[to_email],
            body=plain,
            html=body_html
        )
        msg.attach(attachment_filename, 'application/pdf', attachment_bytes)
        mail.send(msg)
        return True
    except Exception as e:
        current_app.logger.warning(f"Email with attachment failed to {to_email}: {e}")
        _log_exception_to_file(e)
        return False


_users_access_revoked_at_migrated = False

