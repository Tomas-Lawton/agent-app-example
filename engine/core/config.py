import datetime
import glob
import json
import os
import re
import sys
from zoneinfo import ZoneInfo

ENGINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(ENGINE)

PLAIN_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
PROFILE_SETTINGS = {"product", "title", "reader", "time window", "output", "icon", "colours", "tickets", "agent link"}
TRACKERS = ("github", "linear", "jira")
OUTPUTS = ("chat", "email", "both")


class Blocked(Exception):
    """A connection refused access. Record the reason; never work around it."""


class NotAllowed(Exception):
    """A request outside what the user scope approves."""


def env(name):
    """A setting or key from the environment, or from .env in the project root (never committed)."""
    if os.environ.get(name):
        return os.environ[name]
    path = os.path.join(ROOT, ".env")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        for line in f:
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            key, value = line.strip().split("=", 1)
            if key.strip() == name:
                return value.strip().strip("\"'")
    return None


def read_json(path):
    if not os.path.exists(path):
        sys.exit(f"FAIL: {os.path.relpath(path, ROOT)} not found")
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------- the profile


def profile(key):
    """Read PROFILE.md: `name: value` settings between --- lines at the top, then free text.

    Returns the raw settings (so unknown ones can be refused) and the settings the steps use.
    """
    path = os.path.join(ROOT, "profiles", key, "PROFILE.md")
    if not os.path.exists(path):
        sys.exit(f"FAIL: profiles/{key}/PROFILE.md not found")
    with open(path, encoding="utf8") as f:
        text = f.read()

    raw = {}
    if text.startswith("---") and text.count("---") >= 2:
        for line in text.split("---", 2)[1].splitlines():
            if ":" not in line or line.lstrip().startswith("#"):
                continue
            name, value = line.split(":", 1)
            value = re.sub(r"\s*\([^)]*\)\s*$", "", value)  # drop a trailing (note)
            raw[name.strip().lower()] = value.strip()

    colours = {}
    for part in raw.get("colours", "").split(","):
        words = part.split()
        if len(words) == 2:
            colours[words[0]] = words[1]

    window = raw.get("time window", "7").split()[0]
    settings = {
        "product": {"name": raw.get("product", key), "iconUrl": raw.get("icon") or None},
        "reader": raw.get("reader", ""),
        "windowDays": int(window) if window.isdigit() else 7,
        "delivery": (raw.get("output") or "both").lower(),
        "wording": {"title": raw.get("title", "Customer Pulse")},
        "theme": colours,
        "tickets": raw.get("tickets", "").split(),
        "agentLink": raw.get("agent link") or None,
    }
    return raw, settings


def profile_problems(settings, raw):
    problems = []
    if settings["delivery"] not in OUTPUTS:
        problems.append("PROFILE.md `output` must be chat, email or both")
    tickets = settings["tickets"]
    if tickets:
        tracker = tickets[0].lower()
        needed = 3 if tracker == "jira" else 2
        if tracker not in TRACKERS or len(tickets) < needed:
            problems.append(
                "PROFILE.md `tickets` must be `github owner/repo`, `linear TEAM` "
                "or `jira https://site.atlassian.net <project id>`"
            )
    if settings["agentLink"] and not settings["agentLink"].startswith("https://"):
        problems.append("PROFILE.md `agent link` must be an https address")
    for name in sorted(set(raw) - PROFILE_SETTINGS):
        problems.append(
            f"PROFILE.md sets `{name}`, which is not a profile setting "
            "(connections, recipients and schedule belong in user_scope.json)"
        )
    return problems


# ---------------------------------------------------------------- the user scope


def host_of(url):
    url = str(url or "")
    return url.split("/")[2] if url.startswith("https://") and url.count("/") >= 2 else ""


def service_problems(source, rules):
    """An online service: https, approved hosts only, page limit, and keys named, never stored."""
    sid, problems = source.get("id"), []
    hosts = source.get("hosts") or []
    host = host_of(source.get("url"))
    if not host or not hosts:
        problems.append(f"`{sid}` needs an https `url` and its `hosts`")
    elif "{" not in host and host not in hosts:
        problems.append(f"`{sid}` reads {host}, which is not in its hosts")
    if int(source.get("maxPages", 1)) > rules["maxPages"]:
        problems.append(f"`{sid}` maxPages is above the limit of {rules['maxPages']}")

    auth = source.get("auth")
    if not auth:
        return problems
    if auth.get("type") == "client_credentials":
        allowed = {"type", "tokenUrl", "idEnv", "secretEnv", "scope"}
        names_ok = PLAIN_NAME.match(str(auth.get("idEnv", ""))) and PLAIN_NAME.match(str(auth.get("secretEnv", "")))
        if not names_ok or host_of(auth.get("tokenUrl")) not in hosts or set(auth) - allowed:
            problems.append(
                f"`{sid}` client_credentials auth needs `tokenUrl` on an approved host "
                "and `idEnv` and `secretEnv` naming values in .env"
            )
    else:
        allowed = {"type", "env", "header", "param", "optional"}
        if (
            auth.get("type") not in rules["authTypes"]
            or not PLAIN_NAME.match(str(auth.get("env", "")))
            or set(auth) - allowed
        ):
            problems.append(
                f"`{sid}` auth must name a key in .env (`env`) with a type of {', '.join(rules['authTypes'])}; "
                "never put the key itself here"
            )
    return problems


def source_problems(key, source, scope):
    """One connection, against the kinds of connection the use case allows."""
    sid, kind = source.get("id"), source.get("type")
    kinds, shape = scope["connectionTypes"], scope["itemShape"]
    if kind not in kinds:
        return [f"`{sid}` is a `{kind}`; the use case supports {', '.join(kinds)}"]

    problems = []
    if source.get("maxItems", 0) > scope["collect"]["maxItemsPerSource"]:
        problems.append(f"`{sid}` maxItems is above the limit of {scope['collect']['maxItemsPerSource']}")

    if kind in ("warehouse", "file"):
        columns = source.get("columns") or {}
        fields = shape["required"] + shape["optional"]
        problems += [f"`{sid}` must map the `{f}` column" for f in shape["required"] if f not in columns]
        problems += [f"`{sid}` maps `{f}`, not a feedback field" for f in columns if f not in fields]
        if "rating" in columns and not source.get("ratingScale"):
            problems.append(f"`{sid}` maps a rating but no `ratingScale` (5 for stars, 10 for 0 to 10 scores)")

    if kind == "warehouse":
        for name in ("project", "dataset", "table"):
            if not PLAIN_NAME.match(str(source.get(name, ""))):
                problems.append(f"`{sid}` needs a plain `{name}` name")

    if kind == "file":
        folder = os.path.normpath(os.path.join(ROOT, "profiles", key))
        path = os.path.normpath(os.path.join(folder, str(source.get("file", ""))))
        if not source.get("file") or not path.startswith(folder + os.sep):
            problems.append(f"`{sid}` needs a file inside the profile folder")

    if kind == "service":
        problems += service_problems(source, kinds["service"])
    return problems


def check(key, scope, user_scope, settings, raw=None):
    """Everything in the user scope and profile that goes beyond the use case scope (empty if none)."""
    problems = []
    try:
        ZoneInfo(user_scope.get("timezone", ""))
    except Exception:
        problems.append(f"timezone `{user_scope.get('timezone')}` is not a valid IANA name")

    most = scope["send"]["maxRecipients"]
    if not 1 <= len(user_scope.get("recipients") or []) <= most:
        problems.append(f"needs 1 to {most} recipients")

    sources = user_scope.get("sources") or []
    if not sources:
        problems.append("has no connections")
    seen = set()
    for source in sources:
        sid = source.get("id")
        if not PLAIN_NAME.match(str(sid)) or sid in seen:
            problems.append(f"every connection needs a unique, plain id ({sid})")
        seen.add(sid)
        problems += source_problems(key, source, scope)

    return problems + profile_problems(settings, raw or {})


# ---------------------------------------------------------------- runs


def load(key):
    """The merged settings for a profile, after checking it fits inside the use case scope."""
    scope = read_json(os.path.join(ENGINE, "scope.json"))
    user_scope = read_json(os.path.join(ROOT, "profiles", key, "user_scope.json"))
    raw, settings = profile(key)
    problems = check(key, scope, user_scope, settings, raw)
    if problems:
        sys.exit(
            f"BLOCKED: profiles/{key} is outside the use case scope:\n  "
            + "\n  ".join(problems)
            + "\nOnly setup can change the user scope (setup/SKILL.md)."
        )
    return dict(
        settings,
        key=key,
        scope=scope,
        userScope=user_scope,
        sources=user_scope["sources"],
        timezone=user_scope["timezone"],
        recipient=user_scope["recipients"][0],
        windowDays=min(settings["windowDays"], scope["collect"]["maxDays"]),
    )


def run_folders(key):
    return sorted(glob.glob(os.path.join(ROOT, "runs", key, "????-??-??")))


def start_run(key):
    """Create today's run folder (in the profile's timezone) with run.json, and move into it."""
    cfg = load(key)
    now = datetime.datetime.now(ZoneInfo(cfg["timezone"]))
    today = now.date()
    since = today - datetime.timedelta(days=cfg["windowDays"] - 1)

    previous = None
    for folder in reversed(run_folders(key)):
        if os.path.basename(folder) < today.isoformat() and os.path.exists(os.path.join(folder, "summary.json")):
            previous = os.path.relpath(folder, ROOT)
            break

    run = os.path.join(ROOT, "runs", key, today.isoformat())
    os.makedirs(os.path.join(run, "out"), exist_ok=True)
    info = {
        "key": key,
        "date": today.isoformat(),
        "dateLabel": f"{now:%A} {now.day} {now:%B %Y}",
        "since": since.isoformat(),
        "until": today.isoformat(),
        "windowLabel": f"{since.day} {since:%b} to {today.day} {today:%b} {today.year}",
        "previous": previous,
        "folder": os.path.relpath(run, ROOT),
        "startedAt": now.isoformat(timespec="seconds"),
    }
    with open(os.path.join(run, "run.json"), "w") as f:
        json.dump(info, f, indent=2)
    os.chdir(run)
    return cfg, info


def open_run(key):
    """Move into the profile's latest run folder; return the settings and run.json."""
    runs = run_folders(key)
    if not runs:
        sys.exit(f"FAIL: no run for `{key}` yet; start with: python3 engine/steps/collect.py {key}")
    os.chdir(runs[-1])
    return load(key), read_json("run.json")


def key_arg():
    if len(sys.argv) >= 2:
        return sys.argv[1]
    folder = os.path.join(ROOT, "profiles")
    keys = []
    if os.path.isdir(folder):
        keys = sorted(
            k for k in os.listdir(folder) if os.path.isdir(os.path.join(folder, k)) and not k.startswith(("_", "."))
        )
    script = os.path.relpath(sys.argv[0], ROOT)
    sys.exit(f"usage: python3 {script} <profile key>. Profiles: {', '.join(keys) or 'none yet (setup creates one)'}")
