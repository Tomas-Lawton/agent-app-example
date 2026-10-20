"""Step 4, the send gate: email the brief, only if it is inside the scope. Works with any email provider (SMTP).

Usage (from the repository root):  python3 engine/steps/send.py <key> [--to address] [--dry-run]

Before sending it (1) checks the recipient is the one in profiles/<key>/user_scope.json, (2) checks the engine, the
skill and the user scope are exactly the approved version in the shared repository (the upstream branch, so a
local commit can't launder a change), and (3) reruns every check on the run's files. Any failure stops the send; there is no other way to send. Drafts in the brief are never posted.

Email settings come from a .env file in the repository root (never committed), written by setup:
  SMTP_HOST=smtp.gmail.com   SMTP_PORT=587   SMTP_USER=you@example.com   SMTP_PASSWORD=<app password>
  SMTP_FROM=you@example.com  (optional, defaults to SMTP_USER)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # engine/
import argparse, email, json, smtplib, ssl
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
# 2. the rules themselves must be the ones that were approved: no change to the engine, the use case scope or this
#    user's scope since they were committed (setup commits the user scope when the user confirms it)
import shutil, subprocess  # noqa: E402
guarded = ["engine", "SKILL.md", f"profiles/{a.key}/user_scope.json"]
if os.path.isdir(os.path.join(config.ROOT, ".git")) and shutil.which("git"):
    git = lambda *args: subprocess.run(["git", *args], cwd=config.ROOT, capture_output=True, text=True)
    upstream = git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}").stdout.strip()
    if upstream:  # compare with the shared, reviewed repository: a local commit can't launder a change
        git("fetch", "-q")
        base = upstream
    else:
        base = "HEAD"
        print("warning: no remote to compare with; checking against the local commit only")
    changed = git("diff", "--name-only", base, "--", *guarded).stdout.split()
    changed += [line[3:] for line in git("status", "--porcelain", "--", *guarded).stdout.splitlines()]
    changed = sorted({c for c in changed if "__pycache__" not in c and not c.endswith(".pyc")})
    if changed:
        sys.exit(f"BLOCKED: these differ from the approved version in {base}: " + ", ".join(changed)
                 + ". The engine and the user scope can only change through a reviewed change to the repository, never during a run.")
else:
    print("warning: not a git checkout, so the engine and user scope can't be verified against an approved version")
errors = checks.run(cfg, info, "items", "themes", "plan", "content")
# 3. unattended runs need every cited claim confirmed by the independent verifier (SKILL.md, step 3)
if os.environ.get("BRIEF_UNATTENDED") == "1":
    claims = json.load(open("out/claims.json")) if os.path.exists("out/claims.json") else []
    verdicts = json.load(open("verdicts.json")) if os.path.exists("verdicts.json") else {}
    unverified = [c["id"] for c in claims if not verdicts.get(c["id"], {}).get("supported")]
    if not claims or unverified:
        errors.append(f"verify: {len(unverified) or 'all'} cited claims are not confirmed by the verifier (verdicts.json); "
                      "an unattended brief is only sent when every claim is supported by the items it cites")
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
