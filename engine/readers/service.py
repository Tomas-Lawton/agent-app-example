import base64, datetime, email.utils, html, json, re, urllib.error, urllib.parse, urllib.request, urllib.robotparser
import xml.etree.ElementTree as ET
from core.config import Blocked, NotAllowed, env

UA = "customer-pulse-agent/1.0 (reads customer feedback the user approved)"
CAPTCHA = re.compile(r"captcha|are you a robot|verify you are human|access denied", re.I)


def _robots_ok(url, timeout):
    p = urllib.parse.urlsplit(url)
    rp = urllib.robotparser.RobotFileParser()
    try:
        req = urllib.request.Request(f"{p.scheme}://{p.netloc}/robots.txt", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            rp.parse(r.read().decode("utf8", "replace").splitlines())
    except Exception:
        return True  # no robots.txt, or unreachable: no rule to follow
    return rp.can_fetch(UA, url)


def get(url, hosts, timeout=30, as_json=False, check_robots=True, headers=None):
    host = urllib.parse.urlsplit(url).hostname or ""
    if urllib.parse.urlsplit(url).scheme != "https":
        raise NotAllowed(f"{url} is not https")
    if host not in hosts:
        raise NotAllowed(f"{host} is not an approved host for this source ({', '.join(hosts) or 'none'})")
    if check_robots and not _robots_ok(url, timeout):
        raise Blocked(f"robots.txt on {host} does not allow this address")
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept": "application/json, application/xml, text/xml, */*", **(headers or {})}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            final = urllib.parse.urlsplit(r.geturl()).hostname or ""
            if final not in hosts:
                raise Blocked(f"redirected to {final}, which is not approved (often a login page)")
            body = r.read().decode("utf8", "replace")
    except urllib.error.HTTPError as e:
        if e.code in (401, 402, 403, 407, 429, 451):
            raise Blocked(f"{host} answered {e.code}: access refused or rate limited")
        raise
    if CAPTCHA.search(body[:5000]) and not body.lstrip().startswith(("{", "[", "<?xml", "<rss", "<feed")):
        raise Blocked(f"{host} returned a captcha or access check")
    return json.loads(body) if as_json else body


ATOM = "{http://www.w3.org/2005/Atom}"
TAG = re.compile(r"<[^>]+>")


def _get(o, path):
    for part in str(path).split("."):
        if isinstance(o, list):
            o = o[0] if o else None
        o = o.get(part) if isinstance(o, dict) else None
    if isinstance(o, dict):  # feeds often wrap values: {"label": "..."} or {"#text": "..."}
        o = o.get("label", o.get("#text", o.get("value")))
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


def _xml_entries(body):
    root, out = ET.fromstring(body), []
    for e in root.findall(".//item"):
        out.append(
            {
                "id": e.findtext("guid") or e.findtext("link"),
                "title": e.findtext("title"),
                "text": e.findtext("description"),
                "date": e.findtext("pubDate"),
                "url": e.findtext("link"),
            }
        )
    for e in root.findall(f".//{ATOM}entry"):
        link = e.find(f"{ATOM}link")
        out.append(
            {
                "id": e.findtext(f"{ATOM}id"),
                "title": e.findtext(f"{ATOM}title"),
                "text": e.findtext(f"{ATOM}content") or e.findtext(f"{ATOM}summary"),
                "date": e.findtext(f"{ATOM}updated") or e.findtext(f"{ATOM}published"),
                "url": link.get("href") if link is not None else None,
            }
        )
    return out


def _auth(s):
    a = s.get("auth")
    if not a:
        return {}, ""
    if a["type"] == "client_credentials":  # OAuth: swap the client id and secret for a short lived token, every run
        cid, csec = env(a["idEnv"]), env(a["secretEnv"])
        if not (cid and csec):
            raise Blocked(f"{a['idEnv']} or {a['secretEnv']} is not set on this computer; setup stores them in .env")
        if (urllib.parse.urlsplit(a["tokenUrl"]).hostname or "") not in s["hosts"]:
            raise NotAllowed("the token address is not an approved host")
        body = json.dumps(
            {
                "grant_type": "client_credentials",
                "client_id": cid,
                "client_secret": csec,
                "scope": a.get("scope", "read"),
            }
        ).encode()
        req = urllib.request.Request(
            a["tokenUrl"], data=body, method="POST", headers={"Content-Type": "application/json", "User-Agent": UA}
        )
        try:
            tok = json.load(urllib.request.urlopen(req, timeout=30))["access_token"]
        except urllib.error.HTTPError as e:
            raise Blocked(f"the token request was refused ({e.code})")
        return {"Authorization": f"Bearer {tok}"}, ""
    secret = env(a["env"])
    if not secret:
        if a.get("optional"):
            return {}, ""
        raise Blocked(f"the key {a['env']} is not set on this computer; setup stores it in .env")
    if a["type"] == "bearer":
        return {"Authorization": f"Bearer {secret}"}, ""
    if a["type"] == "basic":  # the env value is "user:token"
        return {"Authorization": "Basic " + base64.b64encode(secret.encode()).decode()}, ""
    if a["type"] == "header":
        return {a["header"]: secret}, ""
    return {}, f"{a['param']}={urllib.parse.quote(secret)}"  # query


def page(src):
    return src.get("page")


def fetch(src, since, limit, timeout=30, max_pages=20):
    headers, query = _auth(src)
    cols = src.get("columns") or {}
    items, oldest = [], None
    for n in range(1, min(int(src.get("maxPages", 1)), max_pages) + 1):
        url = src["url"].replace("{page}", str(n)).replace("{since}", f"{since}T00:00:00Z")
        if query:
            url += ("&" if "?" in url else "?") + query
        body = get(
            url,
            src["hosts"],
            timeout=timeout,
            headers=headers,
            check_robots=not src.get("auth") and src.get("robots", True),
        )
        if body.lstrip().startswith(("{", "[")):
            data = json.loads(body)
            entries = _get(data, src["itemsPath"]) if src.get("itemsPath") else data
            entries = entries if isinstance(entries, list) else [entries] if entries else []
        else:
            entries, cols = _xml_entries(body), {k: k for k in ("id", "title", "text", "date", "url")}
        fresh = 0
        for k, e in enumerate(entries):
            if src.get("skipIf") and isinstance(e, dict) and e.get(src["skipIf"]):
                continue
            date = _date(_get(e, cols.get("date", "date")))
            title = _clean(_get(e, cols["title"])) if "title" in cols else ""
            text = _clean(_get(e, cols.get("text", "text"))) or title
            if not date or not text:
                continue  # not a piece of feedback (a feed header, an empty post)
            oldest = min(oldest or date, date)
            if date[:10] < day_before(since):
                continue
            fresh += 1
            r = _get(e, cols["rating"]) if "rating" in cols else None
            try:
                r = float(r) if r not in (None, "") else None
            except (TypeError, ValueError):
                r = None
            items.append(
                {
                    "id": f"{src['id']}:{_get(e, cols.get('id', 'id')) or f'{n}-{k}'}",
                    "url": _get(e, cols["url"]) if "url" in cols else src.get("page"),
                    "date": date,
                    "title": title,
                    "text": text,
                    "rating": r,
                    "ratingScale": src.get("ratingScale") if r is not None else None,
                }
            )
            if len(items) >= limit:
                return items, {"coverageFrom": oldest, "limitReached": True}
        if not entries or not fresh or "{page}" not in src["url"]:
            break
    return items, {"coverageFrom": oldest, "limitReached": False}
