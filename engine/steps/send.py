"""Step 4, the send gate: email the brief, only if it is inside the scope. Works with any email provider (SMTP).

Usage (from the repository root):  python3 engine/steps/send.py <key> [--to address] [--dry-run]

Before sending it (1) checks the recipient is the one in profiles/<key>/user_scope.json and (2) reruns every check
on the run's files. Any failure stops the send; there is no other way to send. Drafts in the brief are never posted.

Email settings come from a .env file in the repository root (never committed), written by setup:
  SMTP_HOST=smtp.gmail.com   SMTP_PORT=587   SMTP_USER=you@example.com   SMTP_PASSWORD=<app password>
  SMTP_FROM=you@example.com  (optional, defaults to SMTP_USER)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # engine/
import argparse, email, smtplib, ssl
from email import policy
from email.utils import formataddr
from core import config, checks

ap = argparse.ArgumentParser()
ap.add_argument("key"); ap.add_argument("--to"); ap.add_argument("--dry-run", action="store_true")
a = ap.parse_args()
cfg, info = config.open_run(a.key)
to = a.to or cfg["recipient"]

if to not in cfg["userScope"]["recipients"][: cfg["scope"]["send"]["maxRecipients"]]:
    sys.exit(f"BLOCKED: {to} is not the recipient in profiles/{a.key}/user_scope.json. "
             "A new recipient is a change to the user scope, made only through setup.")
errors = checks.run(cfg, info, "items", "themes", "plan", "content")
if errors or not os.path.exists("out/email.eml"):
    sys.exit("BLOCKED: checks failed:\n  " + "\n  ".join(errors or ["out/email.eml not found; run render.py first"]))
print("gate: recipient in the user scope, every check passed")

get = lambda k, d=None: config.env(k) or d
host, user, pw = get("SMTP_HOST"), get("SMTP_USER"), get("SMTP_PASSWORD")
if not (host and user and pw):
    sys.exit("NOT SET UP: email settings are missing. Setup asks for them (setup/SKILL.md, Email).")
port, sender = int(get("SMTP_PORT", "587")), get("SMTP_FROM", user)

m = email.message_from_bytes(open("out/email.eml", "rb").read(), policy=policy.default)
del m["From"]; del m["To"]
m["From"] = formataddr((cfg.get("wording", {}).get("briefName", "Feedback Brief"), sender))
m["To"] = to
if a.dry_run:
    sys.exit(f"dry run: would send \"{m['Subject']}\" from {sender} to {to} via {host}:{port}")
ctx = ssl.create_default_context()
with (smtplib.SMTP_SSL(host, port, context=ctx, timeout=30) if port == 465 else smtplib.SMTP(host, port, timeout=30)) as s:
    if port != 465:
        s.starttls(context=ctx)
    s.login(user, pw)
    s.send_message(m)
print(f"SENT \"{m['Subject']}\" to {to}")
