# What to Get from Company Portal to Make Email Work Here

Company Portal sends email; this app uses the same SMTP settings but gets 535. To match the working setup, get the following from the **Company Portal** codebase.

---

## 1. How .env is loaded (so we load the same values)

- **Where is `load_dotenv` called?** (file and line)
- **Exact call:** no args `load_dotenv()`, or with path like `load_dotenv(Path(__file__).parent / '.env')`?
- **When does it run?** At app startup, or only when sending mail?
- Under IIS, **what is the app’s working directory** when the app starts? (If Company Portal uses `load_dotenv()` with no path, it’s using that directory’s `.env`.)

**Copy:** The 5–10 lines that load `.env` and any comment about “run from this directory” or “cwd”.

---

## 2. Where MAIL_* are read (and when)

- **Which file** reads `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_DEFAULT_SENDER`?
- **How:** `os.getenv('MAIL_SERVER')` after `load_dotenv()`, or from a config module, or from a class that reads the file?
- **When:** Once at startup and stored, or every time before sending?

**Copy:** The exact code that sets mail server, port, username, password, sender (the block that builds the config used for sending).

---

## 3. Exact “send one email” code

- **Which file and function** actually connect to SMTP and send? (e.g. `send_email()` or `mail.send()`.)
- **Exact sequence:** e.g. `smtplib.SMTP(server, port)` → `starttls()` → `login(user, pwd)` → `sendmail(...)`.
- **Libraries:** Plain `smtplib` + `email.mime`, or Flask-Mail, or something else?

**Copy:** The full function (or smallest block) that:
- Opens the SMTP connection
- Does TLS (or not)
- Logs in
- Sends the message (including how `From` / `To` / body are set)

---

## 4. Runtime values (optional but very useful)

If someone can add a **one-time debug** in Company Portal right before a successful send and log (or print) only:

- `MAIL_SERVER`
- `MAIL_PORT`
- `MAIL_USERNAME` (no password)
- Whether `MAIL_PASSWORD` is set (e.g. `"SET"` / `"NOT SET"`)

then we can confirm the running app really uses the same server/port/user and that the password is present. That tells us if the only difference is env loading.

---

## 5. Same .env or same values?

- Does Company Portal use a **literal copy** of the same `.env` file as this app, or a different file with the “same” values?
- If different file: **exact path** to that `.env` (e.g. `c:\Websites\CompanyPortal\.env`).

---

## Summary: what to bring back

| Item | What to copy / answer |
|------|------------------------|
| .env loading | Exact `load_dotenv(...)` call(s) and where they run |
| MAIL_* source | Code that reads MAIL_SERVER, MAIL_USERNAME, MAIL_PASSWORD, etc. |
| Send function | Full SMTP connect + TLS + login + send code |
| (Optional) | Log of MAIL_SERVER, MAIL_USERNAME, MAIL_PASSWORD SET/NOT SET at send time |
| .env location | Path to the .env file Company Portal actually uses |

With that, we can make this app load the same .env the same way and send mail the same way as Company Portal.
