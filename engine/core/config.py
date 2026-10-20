"""The three layers a run is built from, and the run folder.

  engine/scope.json               use case scope: what happens, the kinds of connection, the item shape, the limits
  profiles/<key>/user_scope.json  user scope: this user's connections, recipient, timezone and schedule. Set in
                                  setup, then locked. check() refuses anything outside the use case scope, every run.
  profiles/<key>/PROFILE.md       the profile: a few settings at the top (name, colours, time window, output format),
                                  then free text in the client's own words that the agent follows

Settings are always rebuilt from these source files, never from the run folder, so a run can't widen its own reach.
"""
import datetime, glob, json, os, re, sys
from zoneinfo import ZoneInfo

ENGINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(ENGINE)


class Blocked(Exception):
    """A connection refused access. Record the reason; never work around it."""


class NotAllowed(Exception):
    """A request outside what the user scope approves."""
NAME = re.compile(r"^[A-Za-z0-9_-]+$")


def env(name):
    """A setting or key from the environment or the local .env in the repository root (never committed)."""
    if os.environ.get(name):
        return os.environ[name]
    path = os.path.join(ROOT, ".env")
    if os.path.exists(path):
        for line in open(path):
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.strip().split("=", 1)
                if k.strip() == name:
                    return v.strip().strip("\"'")
    return None


def _read(path):
    if not os.path.exists(path):
        sys.exit(f"FAIL: {os.path.relpath(path, ROOT)} not found")
    return json.load(open(path))


SETTINGS = {"product", "brief name", "reader", "time window", "output", "icon", "colours", "tickets"}
TRACKERS = ("github", "linear", "jira")


def profile(key):
    """Read PROFILE.md: `key: value` settings between --- lines at the top, then free text for the agent.
    Unknown settings are refused, so reach (connections, recipients, schedule) can never be set here."""
    path = os.path.join(ROOT, "profiles", key, "PROFILE.md")
    if not os.path.exists(path):
        sys.exit(f"FAIL: profiles/{key}/PROFILE.md not found")
    text = open(path, encoding="utf8").read()
    head = text.split("---", 2)[1] if text.startswith("---") and text.count("---") >= 2 else ""
    raw = {}
    for line in head.splitlines():
        if ":" in line and line.strip() and not line.lstrip().startswith("#"):
            k, v = line.split(":", 1)
            raw[k.strip().lower()] = re.sub(r"\s*\([^)]*\)\s*$", "", v).strip()  # drop a trailing (note)
    colours = dict(part.split() for part in raw.get("colours", "").split(",") if len(part.split()) == 2)
    window = raw.get("time window", "7").split()[0]
    return raw, {"product": {"name": raw.get("product", key), "iconUrl": raw.get("icon") or None},
                 "reader": raw.get("reader", ""), "windowDays": int(window) if window.isdigit() else 7,
                 "delivery": raw.get("output", "chat").lower(), "wording": {"briefName": raw.get("brief name", "Customer Feedback Brief")},
                 "theme": colours, "tickets": raw.get("tickets", "").split()}


def check(key, s, u, p, raw=None):
    """Problems with a user scope that is not inside the use case scope (empty = inside)."""
    out, types, shape = [], s["connectionTypes"], s["itemShape"]
    try:
        ZoneInfo(u.get("timezone", ""))
    except Exception:
        out.append(f"timezone `{u.get('timezone')}` is not a valid IANA name")
    if not 1 <= len(u.get("recipients") or []) <= s["send"]["maxRecipients"]:
        out.append(f"needs 1 to {s['send']['maxRecipients']} recipients")
    if not u.get("sources"):
        out.append("has no connections")
    ids = set()
    for src in u.get("sources") or []:
        sid, t = src.get("id"), src.get("type")
        if not NAME.match(str(sid)) or sid in ids:
            out.append(f"every connection needs a unique, plain id ({sid})")
        ids.add(sid)
        if t not in types:
            out.append(f"`{sid}` is a `{t}`; the use case supports {', '.join(types)}"); continue
        if src.get("maxItems", 0) > s["collect"]["maxItemsPerSource"]:
            out.append(f"`{sid}` maxItems is above the limit of {s['collect']['maxItemsPerSource']}")
        if t in ("warehouse", "file"):
            cols = src.get("columns") or {}
            out += [f"`{sid}` must map the `{f}` column" for f in shape["required"] if f not in cols]
            out += [f"`{sid}` maps `{f}`, not a feedback field" for f in cols if f not in shape["required"] + shape["optional"]]
        if t == "warehouse":
            out += [f"`{sid}` needs a plain `{f}` name" for f in ("project", "dataset", "table") if not NAME.match(str(src.get(f, "")))]
        if t == "file":
            pdir = os.path.join(ROOT, "profiles", key)
            path = os.path.normpath(os.path.join(pdir, str(src.get("file", ""))))
            if not src.get("file") or not path.startswith(os.path.normpath(pdir) + os.sep):
                out.append(f"`{sid}` needs a file inside the profile folder")
        if t == "service":
            svc, url, hosts = types["service"], str(src.get("url", "")), src.get("hosts") or []
            host = url.split("/")[2] if url.startswith("https://") and url.count("/") >= 2 else ""
            if not host or not hosts:
                out.append(f"`{sid}` needs an https `url` and its `hosts`")
            elif "{" not in host and host not in hosts:
                out.append(f"`{sid}` reads {host}, which is not in its hosts")
            if int(src.get("maxPages", 1)) > svc["maxPages"]:
                out.append(f"`{sid}` maxPages is above the limit of {svc['maxPages']}")
            a = src.get("auth")
            if a and a.get("type") == "client_credentials":
                tok_host = str(a.get("tokenUrl", "")).split("/")[2] if str(a.get("tokenUrl", "")).startswith("https://") else ""
                if (not NAME.match(str(a.get("idEnv", ""))) or not NAME.match(str(a.get("secretEnv", ""))) or tok_host not in hosts
                        or set(a) - {"type", "tokenUrl", "idEnv", "secretEnv", "scope"}):
                    out.append(f"`{sid}` client_credentials auth needs `tokenUrl` on an approved host and `idEnv` and `secretEnv` naming values in .env")
            elif a and (a.get("type") not in svc["authTypes"] or not NAME.match(str(a.get("env", ""))) or set(a) - {"type", "env", "header", "param", "optional"}):
                out.append(f"`{sid}` auth must name a key in .env (`env`) with a type of {', '.join(svc['authTypes'])}; never put the key itself here")
    if p.get("delivery", "chat") not in ("chat", "email", "both"):
        out.append("PROFILE.md `output` must be chat, email or both")
    tk = p.get("tickets") or []
    if tk and (tk[0].lower() not in TRACKERS or len(tk) < 2 or (tk[0].lower() == "jira" and len(tk) < 3)):
        out.append("PROFILE.md `tickets` must be `github owner/repo`, `linear TEAM` or `jira https://site.atlassian.net <project id>`")
    for f in sorted(set(raw or {}) - SETTINGS):
        out.append(f"PROFILE.md sets `{f}`, which is not a profile setting (connections, recipients and schedule belong in user_scope.json)")
    return out


def load(key):
    """Merged settings for a profile, after checking its user scope fits inside the use case scope."""
    pdir = os.path.join(ROOT, "profiles", key)
    s, u = _read(os.path.join(ENGINE, "scope.json")), _read(os.path.join(pdir, "user_scope.json"))
    raw, p = profile(key)
    problems = check(key, s, u, p, raw)
    if problems:
        sys.exit(f"BLOCKED: profiles/{key} is outside the use case scope:\n  " + "\n  ".join(problems)
                 + "\nOnly setup can change the user scope (setup/SKILL.md).")
    return dict(p, key=key, scope=s, userScope=u, sources=u["sources"], timezone=u["timezone"], recipient=u["recipients"][0],
                windowDays=min(int(p.get("windowDays") or 7), s["collect"]["maxDays"]))


def start_run(key):
    """Create today's run folder (in the profile timezone) and run.json, and move into it."""
    cfg = load(key)
    now = datetime.datetime.now(ZoneInfo(cfg["timezone"]))
    today = now.date()
    since = today - datetime.timedelta(days=cfg["windowDays"] - 1)
    run = os.path.join(ROOT, "runs", key, today.isoformat())
    previous = next((os.path.relpath(d, ROOT) for d in sorted(glob.glob(os.path.join(ROOT, "runs", key, "????-??-??")), reverse=True)
                     if os.path.basename(d) < today.isoformat() and os.path.exists(os.path.join(d, "summary.json"))), None)
    os.makedirs(os.path.join(run, "out"), exist_ok=True)
    short = lambda d: f"{d.day} {d.strftime('%b')}"
    info = {"key": key, "date": today.isoformat(), "dateLabel": f"{now.strftime('%A')} {now.day} {now.strftime('%B %Y')}",
            "since": since.isoformat(), "until": today.isoformat(), "windowLabel": f"{short(since)} to {short(today)} {today.year}",
            "previous": previous, "folder": os.path.relpath(run, ROOT), "startedAt": now.isoformat(timespec="seconds")}
    json.dump(info, open(os.path.join(run, "run.json"), "w"), indent=2)
    os.chdir(run)
    return cfg, info


def open_run(key):
    """Move into the profile's latest run folder; return the settings and run.json."""
    runs = sorted(glob.glob(os.path.join(ROOT, "runs", key, "????-??-??")))
    if not runs:
        sys.exit(f"FAIL: no run for `{key}` yet; start with: python3 engine/steps/collect.py {key}")
    os.chdir(runs[-1])
    return load(key), json.load(open("run.json"))


def key_arg():
    if len(sys.argv) < 2:
        pdir = os.path.join(ROOT, "profiles")
        keys = sorted(k for k in os.listdir(pdir) if os.path.isdir(os.path.join(pdir, k)) and not k.startswith(("_", ".")))
        sys.exit(f"usage: python3 {os.path.relpath(sys.argv[0], ROOT)} <profile key>. Profiles: {', '.join(keys)}")
    return sys.argv[1]
