"""
Test SMTP connection using the same .env as the app.
Run from project root with venv active:
  python test_email_connection.py
  python test_email_connection.py --send you@example.com   (optional: send a test email)
"""
import sys
from pathlib import Path

# Load .env from project root (same as app)
script_dir = Path(__file__).resolve().parent
env_path = script_dir / '.env'
try:
    from dotenv import load_dotenv
    load_dotenv(env_path, override=True)
except ImportError:
    pass

import os
import smtplib

def main():
    server = os.getenv('MAIL_SERVER', 'smtp.office365.com')
    port = int(os.getenv('MAIL_PORT', '587'))
    use_tls = os.getenv('MAIL_USE_TLS', 'true').lower() == 'true'
    username = os.getenv('MAIL_USERNAME', '')
    password = os.getenv('MAIL_PASSWORD', '')
    from_addr = os.getenv('MAIL_DEFAULT_SENDER', username)

    print(f"Using .env at: {env_path}")
    print(f"  MAIL_SERVER={server}")
    print(f"  MAIL_PORT={port}")
    print(f"  MAIL_USE_TLS={use_tls}")
    print(f"  MAIL_USERNAME={username}")
    print(f"  MAIL_PASSWORD={'*' * 8 if password else '(empty)'}")
    print()

    if not username or not password:
        print("ERROR: MAIL_USERNAME and MAIL_PASSWORD must be set in .env")
        sys.exit(1)

    try:
        print("Connecting...")
        with smtplib.SMTP(server, port, timeout=15) as smtp:
            if use_tls:
                print("Starting TLS...")
                smtp.starttls()
            print("Logging in...")
            smtp.login(username, password)
            print("OK: Login succeeded.")
    except smtplib.SMTPAuthenticationError as e:
        print(f"FAIL: Authentication failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"FAIL: {type(e).__name__}: {e}")
        sys.exit(1)

    # Optional: send a test email
    send_to = None
    if len(sys.argv) > 1 and sys.argv[1] == '--send' and len(sys.argv) > 2:
        send_to = sys.argv[2].strip()

    if send_to:
        try:
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            msg = MIMEMultipart('alternative')
            msg['Subject'] = 'Test from Ziebart Onboarding (test_email_connection.py)'
            msg['From'] = from_addr
            msg['To'] = send_to
            msg.attach(MIMEText('This is a plain text test.', 'plain'))
            msg.attach(MIMEText('<p>This is an <b>HTML</b> test.</p>', 'html'))
            with smtplib.SMTP(server, port) as smtp:
                if use_tls:
                    smtp.starttls()
                smtp.login(username, password)
                smtp.sendmail(from_addr, [send_to], msg.as_string())
            print(f"Test email sent to {send_to}.")
        except Exception as e:
            print(f"Sending test email failed: {e}")
            sys.exit(1)
    else:
        print("Tip: run with --send your@email.com to send a test message.")

if __name__ == '__main__':
    main()
