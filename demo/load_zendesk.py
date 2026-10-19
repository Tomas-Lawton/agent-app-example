"""Import the demo's support tickets into a Zendesk account, as Capital Bank of Australia's helpdesk.

Usage (from the repository root):
  python3 demo/load_zendesk.py <subdomain> [start] [--clear]   for https://<subdomain>.zendesk.com
  start:    skip the first N tickets (to resume after an interruption without duplicating)
  --clear:  first delete every ticket an earlier load tagged `demo`

Writing needs a write token, fetched fresh from the OAuth client in .env (ZENDESK_CLIENT_ID, ZENDESK_CLIENT_SECRET,
a Confidential client), or ZENDESK_LOADER as "<agent email>/token:<API token>". This is demo setup, not the brief,
which only ever reads with its own read only connection. Reads profiles/demo/data/tickets.csv
(run demo/make_data.py first) and creates the tickets through Zendesk's ticket import API, which keeps each ticket's
original date, in batches of 100. Then prints the read connection to add during setup.
Check Zendesk's current API docs if anything fails; the import API needs an admin and may change.
"""
import base64, csv, json, os, sys, time, urllib.error, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))
from core.config import env  # noqa: E402

if len(sys.argv) < 2:
    sys.exit(__doc__)
args = [a for a in sys.argv[1:] if not a.startswith("--")]
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

start = int(args[1]) if len(args) > 1 else 0
for n in range(start, len(rows), 100):
    batch = [{"subject": r["subject"], "comments": [{"value": r["description"], "created_at": f"{r['created_at']}T10:00:00Z"}],
              "description": r["description"], "created_at": f"{r['created_at']}T10:00:00Z", "tags": ["demo", r["channel"].replace(" ", "_")],
              "requester": {"name": f"Demo customer {r['ticket_id']}", "email": f"customer{r['ticket_id']}@capitalbank.example"}}
             for r in rows[n:n + 100]]
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
    print(f"imported {min(n + 100, len(rows))} of {len(rows)} (to resume: start {min(n + 100, len(rows))})")
    time.sleep(2)
print("connection for setup (an OAuth client of kind Confidential, its id and secret in .env):\n" + json.dumps({
    "id": "tickets", "type": "service", "label": "Zendesk tickets",
    "url": f"https://{sub}.zendesk.com/api/v2/tickets.json?sort_by=created_at&sort_order=desc&per_page=100&page={{page}}",
    "hosts": [f"{sub}.zendesk.com"], "itemsPath": "tickets",
    "auth": {"type": "client_credentials", "tokenUrl": f"https://{sub}.zendesk.com/oauth/tokens",
             "idEnv": "ZENDESK_CLIENT_ID", "secretEnv": "ZENDESK_CLIENT_SECRET", "scope": "read"},
    "columns": {"id": "id", "date": "created_at", "title": "subject", "text": "description"}, "maxPages": 10}, indent=2))
