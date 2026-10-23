import json, os, re, time, urllib.error, urllib.parse, urllib.request
from core.config import Blocked, NotAllowed

NAME = re.compile(r"^[A-Za-z0-9_-]{1,1024}$")
COL = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,299}$")
FIELDS = ("id", "date", "text", "title", "rating", "url")
HOST = "https://bigquery.googleapis.com/bigquery/v2"


def token():
    """A Google access token: GOOGLE_OAUTH_ACCESS_TOKEN, application default credentials, or the metadata server."""
    if os.environ.get("GOOGLE_OAUTH_ACCESS_TOKEN"):
        return os.environ["GOOGLE_OAUTH_ACCESS_TOKEN"]
    adc = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or os.path.expanduser(
        "~/.config/gcloud/application_default_credentials.json"
    )
    if os.path.exists(adc) and json.load(open(adc)).get("type") == "authorized_user":
        d = json.load(open(adc))
        body = urllib.parse.urlencode(
            {
                "client_id": d["client_id"],
                "client_secret": d["client_secret"],
                "refresh_token": d["refresh_token"],
                "grant_type": "refresh_token",
            }
        ).encode()
        return json.load(urllib.request.urlopen("https://oauth2.googleapis.com/token", body, timeout=30))[
            "access_token"
        ]
    try:  # running on Google Cloud: the identity the job runs as
        req = urllib.request.Request(
            "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
            headers={"Metadata-Flavor": "Google"},
        )
        return json.load(urllib.request.urlopen(req, timeout=5))["access_token"]
    except Exception:
        raise Blocked("no Google credentials for the warehouse; setup explains how to sign in")


def call(url, tok, payload=None):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode() if payload is not None else None,
        method="POST" if payload is not None else "GET",
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
    )
    try:
        return json.load(urllib.request.urlopen(req, timeout=120))
    except urllib.error.HTTPError as e:
        return {"_error": e.code, "_body": e.read().decode()[:2000]}


def build_sql(src, limit):
    """The one query this reader may run. Raises ValueError on any name it can't prove is a plain identifier."""
    for k in ("project", "dataset", "table"):
        if not NAME.match(str(src.get(k, ""))):
            raise ValueError(f"warehouse `{k}` must be a plain name, got {src.get(k)!r}")
    cols = src.get("columns") or {}
    for need in ("date", "text"):
        if need not in cols:
            raise ValueError(f"warehouse columns must map `{need}`")
    for k, c in cols.items():
        if k not in FIELDS:
            raise ValueError(f"warehouse column `{k}` is not a feedback field ({', '.join(FIELDS)})")
        if not COL.match(str(c)):
            raise ValueError(f"warehouse column name {c!r} is not a plain identifier")
    day = f"SAFE_CAST(SUBSTR(CAST(`{cols['date']}` AS STRING), 1, 10) AS DATE)"
    sel = [f"CAST(`{cols[k]}` AS STRING) AS `{k}`" for k in FIELDS if k in cols and k != "date"]
    sel.append(f"CAST(`{cols['date']}` AS STRING) AS `date`")  # the full timestamp; collect.py makes it a local date
    return (
        f"SELECT {', '.join(sel)} FROM `{src['project']}.{src['dataset']}.{src['table']}` "
        f"WHERE {day} >= DATE_SUB(@since, INTERVAL 1 DAY) ORDER BY `{cols['date']}` DESC LIMIT {int(limit)}"
    )


def fetch(src, since, limit, timeout=30, max_bytes=1_000_000_000):
    if src.get("engine", "bigquery") != "bigquery":
        raise NotAllowed(f"warehouse engine `{src.get('engine')}` is not supported")
    sql = build_sql(src, limit)
    job_project = src.get("jobProject") or src["project"]
    if not NAME.match(job_project):
        raise ValueError("warehouse `jobProject` must be a plain name")
    body = {
        "query": sql,
        "useLegacySql": False,
        "parameterMode": "NAMED",
        "timeoutMs": timeout * 1000,
        "maximumBytesBilled": str(int(max_bytes)),
        "maxResults": 1000,
        "queryParameters": [{"name": "since", "parameterType": {"type": "DATE"}, "parameterValue": {"value": since}}],
    }
    if src.get("location"):
        body["location"] = src["location"]
    tok = token()
    r = call(f"{HOST}/projects/{job_project}/queries", tok, body)
    if "_error" in r:
        if r["_error"] in (401, 403):
            raise Blocked(f"BigQuery refused access ({r['_error']}): {r['_body'][:200]}")
        raise RuntimeError(f"BigQuery error {r['_error']}: {r['_body'][:300]}")
    ref = r.get("jobReference", {})
    deadline = time.time() + timeout
    while not r.get("jobComplete"):
        if time.time() > deadline:
            raise TimeoutError("BigQuery query did not finish in time")
        time.sleep(1)
        loc = f"&location={ref['location']}" if ref.get("location") else ""
        r = call(f"{HOST}/projects/{job_project}/queries/{ref['jobId']}?maxResults=1000{loc}", tok)
        if "_error" in r:
            raise RuntimeError(f"BigQuery error {r['_error']}: {r['_body'][:300]}")
    names = [f["name"] for f in r.get("schema", {}).get("fields", [])]
    items = []
    for n, row in enumerate(r.get("rows", [])):
        v = dict(zip(names, (c.get("v") for c in row["f"])))
        if not v.get("text") or not v.get("date"):
            continue
        rating = v.get("rating")
        try:
            rating = float(rating) if rating not in (None, "") else None
        except ValueError:
            rating = None
        items.append(
            {
                "id": f"{src['id']}:{v.get('id') or n}",
                "url": v.get("url") or None,
                "date": v["date"],
                "title": v.get("title") or "",
                "text": v["text"].strip(),
                "rating": rating,
                "ratingScale": src.get("ratingScale") if rating is not None else None,
            }
        )
    return items
