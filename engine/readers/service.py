import datetime, email.utils, html, json, re, urllib.error, urllib.parse, urllib.request
from core.config import Blocked, NotAllowed, env

UA = "customer-pulse-agent/1.0 (reads customer feedback the user approved)"
TAG = re.compile(r"<[^>]+>")


def get(url, hosts, timeout=30, headers=None):
    """A plain GET over https to an approved host, returning the parsed JSON."""
    host = urllib.parse.urlsplit(url).hostname or ""
    if urllib.parse.urlsplit(url).scheme != "https":
        raise NotAllowed(f"{url} is not https")
    if host not in hosts:
        raise NotAllowed(f"{host} is not an approved host for this source ({', '.join(hosts) or 'none'})")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            final = urllib.parse.urlsplit(r.geturl()).hostname or ""
            if final not in hosts:
                raise Blocked(f"redirected to {final}, which is not approved (often a login page)")
            return json.loads(r.read().decode("utf8", "replace"))
    except urllib.error.HTTPError as e:
        if e.code in (401, 402, 403, 407, 429, 451):
            raise Blocked(f"{host} answered {e.code}: access refused or rate limited")
        raise


def _get(o, path):
    for part in str(path).split("."):
        if isinstance(o, list):
            o = o[0] if o else None
        o = o.get(part) if isinstance(o, dict) else None
    return o


def day_before(since):
    return (datetime.date.fromisoformat(since) - datetime.timedelta(days=1)).isoformat()


def _date(v):
    if v in (None, ""):
        return ""
    if isinstance(v, (int, float)) or str(v).isdigit():
        n = float(v) / (1000 if float(v) > 1e11 else 1)
        return datetime.datetime.fromtimestamp(n, datetime.timezone.utc).isoformat()
    v = str(v).strip()
    if v[:4].isdigit():
        return v  # the full timestamp; collect.py turns it into a date in the profile's timezone
    try:
        return email.utils.parsedate_to_datetime(v).isoformat()
    except Exception:
        return ""


def _clean(v):
    return re.sub(r"\s+", " ", html.unescape(TAG.sub(" ", str(v or "")))).strip()


def _token(a, hosts):
    """OAuth client credentials: swap the client id and secret for a short lived read only token, every run."""
    cid, csec = env(a["idEnv"]), env(a["secretEnv"])
    if not (cid and csec):
        raise Blocked(f"{a['idEnv']} or {a['secretEnv']} is not set on this computer; setup stores them in .env")
    if (urllib.parse.urlsplit(a["tokenUrl"]).hostname or "") not in hosts:
        raise NotAllowed("the token address is not an approved host")
    body = {
        "grant_type": "client_credentials",
        "client_id": cid,
        "client_secret": csec,
        "scope": a.get("scope", "read"),
    }
    req = urllib.request.Request(
        a["tokenUrl"],
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": UA},
    )
    try:
        return json.load(urllib.request.urlopen(req, timeout=30))["access_token"]
    except urllib.error.HTTPError as e:
        raise Blocked(f"the token request was refused ({e.code})")


def _auth(s):
    a = s.get("auth")
    if not a:
        return {}
    if a["type"] == "client_credentials":
        return {"Authorization": f"Bearer {_token(a, s['hosts'])}"}
    secret = env(a["env"])  # bearer
    if not secret:
        if a.get("optional"):
            return {}
        raise Blocked(f"the key {a['env']} is not set on this computer; setup stores it in .env")
    return {"Authorization": f"Bearer {secret}"}


def page(src):
    return src.get("page")


def _rating(v):
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _item(src, cols, e, key):
    """One entry mapped onto the item shape, or None when it is not a piece of feedback."""
    date = _date(_get(e, cols.get("date", "date")))
    title = _clean(_get(e, cols["title"])) if "title" in cols else ""
    text = _clean(_get(e, cols.get("text", "text"))) or title
    if not date or not text:
        return None  # not a piece of feedback (an empty post)
    r = _rating(_get(e, cols["rating"])) if "rating" in cols else None
    return {
        "id": f"{src['id']}:{_get(e, cols.get('id', 'id')) or key}",
        "url": _get(e, cols["url"]) if "url" in cols else src.get("page"),
        "date": date,
        "title": title,
        "text": text,
        "rating": r,
        "ratingScale": src.get("ratingScale") if r is not None else None,
    }


def fetch(src, since, limit, timeout=30, max_pages=20):
    headers, cols, items = _auth(src), src.get("columns") or {}, []
    for n in range(1, min(int(src.get("maxPages", 1)), max_pages) + 1):
        url = src["url"].replace("{page}", str(n)).replace("{since}", f"{since}T00:00:00Z")
        data = get(url, src["hosts"], timeout=timeout, headers=headers)
        entries = _get(data, src["itemsPath"]) if src.get("itemsPath") else data
        entries = entries if isinstance(entries, list) else [entries] if entries else []
        fresh = 0
        for k, e in enumerate(entries):
            if src.get("skipIf") and isinstance(e, dict) and e.get(src["skipIf"]):
                continue
            it = _item(src, cols, e, f"{n}-{k}")
            if not it or it["date"][:10] < day_before(since):
                continue
            fresh += 1
            items.append(it)
            if len(items) >= limit:
                return items
        if not entries or not fresh or "{page}" not in src["url"]:
            break
    return items
