"""Import the demo's support tickets into a Zendesk account, as Capital Bank of Australia's helpdesk.

Usage (from the repository root):
  python3 demo/load_zendesk.py <subdomain> [start] [--limit N] [--clear]   for https://<subdomain>.zendesk.com
  start:      skip the first N tickets (to resume after an interruption without duplicating)
  --limit N:  import at most N tickets (default 120; the survey in BigQuery supplies the rest of the volume)
  --clear:    first delete every ticket an earlier load tagged `demo`
  --only i,j: import just these row numbers (to retry ones a batch reported as failed)

Warning: on Zendesk trial accounts the ticket import API is tightly limited, and after a few dozen imported tickets
Zendesk has locked trial accounts against further writes ("this Zendesk account has expired"); reading still works.
Import a small set once (--limit 30), and use a paid or sandbox account for more.
Gentle on purpose: every ticket comes from the account's own admin user (no
made up customer accounts), in batches of 30 with a pause between them. Credentials can be passed as environment
variables for this one command; nothing needs to be saved.

Writing needs a write token, fetched fresh from the OAuth client in .env (ZENDESK_CLIENT_ID, ZENDESK_CLIENT_SECRET,
a Confidential client), or ZENDESK_LOADER as "<agent email>/token:<API token>". This is demo setup, not the brief,
which only ever reads with its own read only connection. Reads profiles/demo/data/tickets.csv
(run demo/make_data.py first) and creates the tickets through Zendesk's ticket import API, which keeps each ticket's
original date, in batches of 100. Then prints the read connection to add during setup.
Check Zendesk's current API docs if anything fails; the import API needs an admin and may change.
"""
import base64, csv, datetime, json, os, sys, time, urllib.error, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))
from core.config import env  # noqa: E402

if len(sys.argv) < 2:
    sys.exit(__doc__)
argv = sys.argv[1:]
limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else 120
only = [int(i) for i in argv[argv.index("--only") + 1].split(",")] if "--only" in argv else None
args = [a for n, a in enumerate(argv) if not a.startswith("--") and (n == 0 or argv[n - 1] not in ("--limit", "--only"))]
sub, creds, bearer = args[0], env("ZENDESK_LOADER"), None
if env("ZENDESK_CLIENT_ID") and env("ZENDESK_CLIENT_SECRET"):
    req = urllib.request.Request(f"https://{sub}.zendesk.com/oauth/tokens", method="POST", headers={"Content-Type": "application/json"},
                                 data=json.dumps({"grant_type": "client_credentials", "client_id": env("ZENDESK_CLIENT_ID"),
                                                  "client_secret": env("ZENDESK_CLIENT_SECRET"), "scope": "read write"}).encode())
    bearer = json.load(urllib.request.urlopen(req, timeout=30))["access_token"]
if not (bearer or creds):
    sys.exit("set ZENDESK_CLIENT_ID and ZENDESK_CLIENT_SECRET (a Confidential OAuth client), or ZENDESK_LOADER, in .env")
path = os.path.join(ROOT, "profiles", "demo", "data", "tickets.csv")
if not os.path.exists(path):
    sys.exit("run python3 demo/make_data.py first")
auth = f"Bearer {bearer}" if bearer else "Basic " + base64.b64encode(creds.encode()).decode()
rows = list(csv.DictReader(open(path)))


def post(url, payload):
    for attempt in range(10):
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                     headers={"Authorization": auth, "Content-Type": "application/json"})
        try:
            return json.load(urllib.request.urlopen(req, timeout=60))
        except urllib.error.HTTPError as e:
            if e.code == 429:  # trial accounts limit bulk imports: wait as long as Zendesk asks
                wait = int(e.headers.get("Retry-After") or 60)
                print(f"rate limited; waiting {wait}s"); time.sleep(wait); continue
            sys.exit(f"Zendesk answered {e.code}: {e.read().decode()[:400]}")
    sys.exit("still rate limited after 10 tries; run again later with the start number printed above")


def call(url, method="GET"):
    req = urllib.request.Request(url, method=method, headers={"Authorization": auth})
    for _ in range(10):
        try:
            body = urllib.request.urlopen(req, timeout=60).read()
            return json.loads(body) if body else {}
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = int(e.headers.get("Retry-After") or 60); print(f"rate limited; waiting {wait}s"); time.sleep(wait); continue
            sys.exit(f"Zendesk answered {e.code}: {e.read().decode()[:300]}")


if "--clear" in sys.argv:  # delete every ticket an earlier demo load created
    removed = 0
    while True:
        found = call(f"https://{sub}.zendesk.com/api/v2/search.json?query=type%3Aticket%20tags%3Ademo&per_page=100")
        ids = [str(r["id"]) for r in found.get("results", [])]
        if not ids:
            break
        call(f"https://{sub}.zendesk.com/api/v2/tickets/destroy_many.json?ids={','.join(ids)}", "DELETE")
        removed += len(ids); print(f"deleted {removed} demo tickets"); time.sleep(5)
    print(f"cleared {removed} demo tickets")

rows = [rows[i] for i in only] if only else rows[:limit]
me = call(f"https://{sub}.zendesk.com/api/v2/users/me.json")["user"]["id"]  # one requester: the admin running the import
start = int(args[1]) if len(args) > 1 else 0
def stamp(day):
    """10:00 UTC on the ticket's day, but never in the future (Zendesk refuses future dates)."""
    t = datetime.datetime.fromisoformat(f"{day}T10:00:00+00:00")
    now = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=10)
    return min(t, now).strftime("%Y-%m-%dT%H:%M:%SZ")


for n in range(start, len(rows), 30):
    batch = [{"subject": r["subject"], "comments": [{"value": r["description"], "created_at": stamp(r["created_at"])}],
              "description": r["description"], "created_at": stamp(r["created_at"]), "tags": ["demo", r["channel"].replace(" ", "_")],
              "requester_id": me}
             for r in rows[n:n + 30]]
    job = post(f"https://{sub}.zendesk.com/api/v2/imports/tickets/create_many", {"tickets": batch}).get("job_status", {})
    for _ in range(120):  # the import runs as a background job: wait for it and report what really happened
        st = call(job["url"]).get("job_status", {}) if job.get("url") else {}
        if st.get("status") in ("completed", "failed", "killed"):
            break
        time.sleep(5)
    results = st.get("results") or []
    failed = [r for r in results if r.get("error") or r.get("errors")]
    print(f"batch from {n}: job {st.get('status')}, {len(results) - len(failed)} created, {len(failed)} failed"
          + (f" (first error: {str(failed[0])[:200]})" if failed else "") + (f" {st.get('message')}" if st.get("status") != "completed" else ""))
    if st.get("status") != "completed" or failed:
        sys.exit(f"stopped; fix the error above, then resume with: start {n}")
    print(f"imported {min(n + 30, len(rows))} of {len(rows)} (to resume: start {min(n + 30, len(rows))})")
    time.sleep(20)
print("connection for setup (an OAuth client of kind Confidential, its id and secret in .env):\n" + json.dumps({
    "id": "tickets", "type": "service", "label": "Zendesk tickets",
    "url": f"https://{sub}.zendesk.com/api/v2/tickets.json?sort_by=created_at&sort_order=desc&per_page=100&page={{page}}",
    "hosts": [f"{sub}.zendesk.com"], "itemsPath": "tickets",
    "auth": {"type": "client_credentials", "tokenUrl": f"https://{sub}.zendesk.com/oauth/tokens",
             "idEnv": "ZENDESK_CLIENT_ID", "secretEnv": "ZENDESK_CLIENT_SECRET", "scope": "read"},
    "columns": {"id": "id", "date": "created_at", "title": "subject", "text": "description"}, "maxPages": 10}, indent=2))
