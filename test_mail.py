"""
Test script: send a single email using this app's .env.

Uses SocketLabs if SOCKETLABS_USERNAME and SOCKETLABS_PASSWORD are set;
otherwise uses MAIL_* or EMAIL_* (Office 365).

Run from project root with venv active: python test_mail.py
"""
from pathlib import Path
from dotenv import load_dotenv
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

if os.getenv('USE_ENV_PATH'):
    env_path = Path(os.getenv('USE_ENV_PATH'))
else:
    script_env = Path(__file__).resolve().parent / '.env'
    cwd_env = Path.cwd() / '.env'
    env_path = script_env if script_env.exists() else cwd_env
load_dotenv(env_path)
print(f"Loaded .env from: {env_path}")
# Prefer SocketLabs when set
sock_user = os.getenv('SOCKETLABS_USERNAME', '')
sock_pwd = os.getenv('SOCKETLABS_PASSWORD', '')
if not (sock_user and sock_pwd):
    print("(SOCKETLABS_USERNAME/PASSWORD not set – uncomment SocketLabs block in .env to use SocketLabs)")

to_addr = 'asymons@ziebart.com'
plain = 'Test email from Ziebart Onboarding mail test. If you see this, the mail server is working.'
html = '<p>Test email from Ziebart Onboarding mail test. If you see this, the mail server is working.</p>'

# SocketLabs (same flow as the other app: SMTP → STARTTLS → login)
sock_user = os.getenv('SOCKETLABS_USERNAME', '')
sock_pwd = os.getenv('SOCKETLABS_PASSWORD', '')
if sock_user and sock_pwd:
    server = os.getenv('SOCKETLABS_SERVER', 'smtp.socketlabs.com')
    port = int(os.getenv('SOCKETLABS_PORT', '587'))
    sender = os.getenv('SOCKETLABS_SENDER_EMAIL', 'noreply@ziebart.com')
    print("Using SocketLabs:", repr(server), "port", port, "user", repr(sock_user))
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = 'Ziebart Onboarding – mail server test'
        msg['From'] = sender
        msg['To'] = to_addr
        msg.attach(MIMEText(plain, 'plain'))
        msg.attach(MIMEText(html, 'html'))
        with smtplib.SMTP(server, port) as smtp:
            smtp.starttls()
            smtp.login(sock_user, sock_pwd)
            smtp.sendmail(sender, [to_addr], msg.as_string())
        print('SUCCESS: Test email sent to', to_addr)
    except Exception as e:
        print('FAILED:', e)
        exit(1)
    exit(0)

# Office 365 / MAIL_* or EMAIL_*
def _server():
    s = os.getenv('MAIL_SERVER') or os.getenv('EMAIL_SERVER', '')
    if s and 'outlook.office365.com' in s.lower():
        return 'smtp.office365.com'
    return s or 'smtp.office365.com'

server = _server()
port = int(os.getenv('MAIL_PORT') or os.getenv('EMAIL_PORT', '587'))
user = os.getenv('MAIL_USERNAME') or os.getenv('EMAIL_ADDRESS')
pwd = os.getenv('MAIL_PASSWORD') or os.getenv('EMAIL_PASSWORD')
sender = os.getenv('MAIL_DEFAULT_SENDER') or user

print("Using Office 365 – MAIL_SERVER", repr(server), "MAIL_USERNAME", repr(user), "PASSWORD", "SET" if pwd else "NOT SET")

if not all([server, user, pwd]):
    print('Missing mail settings: set SOCKETLABS_* or MAIL_* / EMAIL_* in .env')
    exit(1)

try:
    msg = MIMEText(plain)
    msg['Subject'] = 'Ziebart Onboarding – mail server test'
    msg['From'] = sender
    msg['To'] = to_addr
    with smtplib.SMTP(server, port) as smtp:
        smtp.starttls()
        smtp.login(user, pwd)
        smtp.sendmail(sender, [to_addr], msg.as_string())
    print('SUCCESS: Test email sent to', to_addr)
except Exception as e:
    print('FAILED:', e)
    exit(1)
