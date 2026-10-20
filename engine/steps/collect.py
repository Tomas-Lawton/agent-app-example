"""Step 1: start a run and collect feedback from every connection in the user scope, and nothing else.

Usage (from the repository root):  python3 engine/steps/collect.py <profile key>

Creates runs/<key>/<today> with run.json (today, the window, the previous run), then for each connection in
profiles/<key>/user_scope.json: checks it is a kind the use case supports, runs that kind's reader, records
`blocked` with the reason if access is refused (and never tries another way round), maps every item to the
use case's item shape, removes emails, phone numbers and long reference numbers, and drops exact duplicates.
Keeps the most recent items up to the use case cap (scope.json -> collect.maxItems), gives each a short id
(`<connection>-001`), and writes items.json (the evidence for the whole run) and collect_log.json. Then runs
cluster.py, which groups similar items for reading and for the map.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # engine/
import importlib, json, re
from core import config, checks


key = config.key_arg()
cfg, info = config.start_run(key)
scope, types = cfg["scope"], cfg["scope"]["connectionTypes"]
pdir = os.path.join(config.ROOT, "profiles", key)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{7,}\d(?!\w)")
LONGNUM = re.compile(r"(?<![\w.])\d{6,}(?!\w|\.\d)")


def scrub(s):
    return LONGNUM.sub("[number]", PHONE.sub("[phone]", EMAIL.sub("[email]", s or "")))


def reader(src):
    t = src["type"]
    if t == "service":
        return importlib.import_module("readers.service"), {"max_pages": types["service"]["maxPages"]}
    if t == "file":
        return importlib.import_module("readers.csv_file"), {"profile_dir": pdir}
    return importlib.import_module("readers.bigquery"), {"max_bytes": scope["collect"]["warehouseMaxBytesBilled"]}


log, items, seen, dupes = [], [], set(), 0
for src in cfg["sources"]:
    t = src["type"]
    private = bool(src.get("private", types[t].get("private", bool(src.get("auth")))))
    entry = {"id": src["id"], "type": t, "label": src.get("label", src["id"]), "private": private}
    limit = min(int(src.get("maxItems", scope["collect"]["maxItemsPerSource"])), scope["collect"]["maxItemsPerSource"])
    try:
        mod, kw = reader(src)
        got, meta = mod.fetch(src, info["since"], limit, timeout=scope["collect"]["timeoutSeconds"], **kw)
        kept = []
        for it in got:
            it = dict(it, source=src["id"], connection=t, sourceLabel=entry["label"], private=private,
                      text=scrub(it.get("text")), title=scrub(it.get("title")))
            n = re.sub(r"\W+", " ", it["text"].lower()).strip()
            if n and n not in seen:
                seen.add(n); kept.append(it)
            else:
                dupes += bool(n)
        items += kept
        entry.update(status="ok", kept=len(kept), coverageFrom=meta.get("coverageFrom"))
        if hasattr(mod, "page"): entry["link"] = mod.page(src)
        if meta.get("limitReached") and (meta.get("coverageFrom") or "") > info["since"]:
            entry["note"] = f"item limit reached; covers {meta['coverageFrom']} to {info['until']}, not the whole window"
    except config.Blocked as e:
        entry.update(status="blocked", reason=str(e))
    except Exception as e:
        entry.update(status="error", reason=f"{type(e).__name__}: {e}")
    log.append(entry)
    print(f"{src['id']:<16} {entry['status']:<8} {entry.get('kept', 0):>4} items  {entry.get('reason') or entry.get('note') or ''}")

# the most recent items, up to the use case cap, each with a short id the agent can tag
# The headline numbers (volume, ratings, items per day and per connection) count everything collected in the window;
# the agent reads the newest items up to the cap, and the run records exactly which dates those cover.
cap = scope["collect"]["maxItems"]
items.sort(key=lambda i: i["date"], reverse=True)
window = [{"date": i["date"], "rating": i.get("rating"), "ratingScale": i.get("ratingScale"), "source": i["source"]} for i in items]
collected = {}
for i in items:
    collected[i["source"]] = collected.get(i["source"], 0) + 1
capped = len(items) > cap
items = items[:cap]
coverage = items[-1]["date"] if capped and items else info["since"]
counts = {}
for n, i in enumerate(items, 1):
    i["nativeId"], i["id"] = i["id"], f"{i['source']}-{n:03d}"
    counts[i["source"]] = counts.get(i["source"], 0) + 1
for e in log:
    if e.get("status") == "ok":
        e["kept"], e["collected"] = counts.get(e["id"], 0), collected.get(e["id"], 0)
json.dump({"items": items, "capped": capped, "coverageFrom": coverage}, open("items.json", "w"), indent=1, ensure_ascii=False)
json.dump(window, open("window.json", "w"), ensure_ascii=False)
json.dump({"duplicatesDropped": dupes, "capped": capped, "sources": log}, open("collect_log.json", "w"), indent=2, ensure_ascii=False)

errors = checks.run(cfg, info, "items")
print(f"run folder: {info['folder']}  |  {info['dateLabel']}  |  window {info['since']} to {info['until']}  |  previous: {info['previous'] or 'none'}")
print(f"{len(items)} items from {sum(e['status'] == 'ok' for e in log)} of {len(log)} connections -> items.json"
      + (f" (the {cap} most recent of {len(window)}, covering {coverage} to {info['until']}; the headline numbers count all {len(window)})" if capped else ""))
if errors or not items:
    sys.exit("STOP:\n  " + "\n  ".join(errors or ["no feedback collected; report the reasons above, never look elsewhere"]))
import subprocess  # noqa: E402
r = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "cluster.py"), key], cwd=config.ROOT)
sys.exit(r.returncode)
