import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # engine/
import datetime, glob, json
from core import config, checks

cfg, info = config.open_run(config.key_arg())
items = json.load(open("items.json"))["items"]
by_id = {i["id"]: i for i in items}
log = json.load(open("collect_log.json"))
if not os.path.exists("themes.json"):
    sys.exit("STOP: themes.json not found. Write it first (SKILL.md, step 2).")
data = json.load(open("themes.json"))

tags = {}
for p in sorted(glob.glob("tags/part_*.json")):
    for iid, tids in json.load(open(p)).items():
        tags[iid] = [tids] if isinstance(tids, str) else list(tids or [])
missing = [i for i in by_id if i not in tags]
if missing:
    sys.exit(
        f"FIX: {len(missing)} of {len(items)} items are not tagged (for example {', '.join(missing[:5])}). "
        "Tag every item in tags/part_NN.json, using [] when no theme fits, then run summarise.py again."
    )

N = len(items) or 1
capped = json.load(open("items.json")).get("capped", False)
since, until = datetime.date.fromisoformat(info["since"]), datetime.date.fromisoformat(info["until"])
mid = since + (until - since) / 2  # trends compare the two halves of the window


def five(it):
    r, s = it.get("rating"), it.get("ratingScale")
    return None if r is None or not s else r / s * 5


def stats(lst):
    rated = [five(i) for i in lst if five(i) is not None]
    return {
        "avgRating": round(sum(rated) / len(rated), 1) if rated else None,
        "lowShare": round(100 * sum(r <= 2 for r in rated) / len(rated)) if rated else None,
    }


def trend(ids):
    """Rising or easing inside this window: the second half of the window against the first."""
    first = sum(1 for i in ids if datetime.date.fromisoformat(by_id[i]["date"]) <= mid)
    second = len(ids) - first
    if second >= 3 and second >= 1.5 * max(first, 1):
        return "rising", 1, first, second
    if first >= 3 and first >= 1.5 * max(second, 1):
        return "easing", 0, first, second
    return "steady", 0, first, second


for t in data.get("themes", []):
    ids = [i for i, tids in tags.items() if t.get("id") in tids and i in by_id]
    share = round(100 * len(ids) / N, 1)
    breadth = 3 if share >= 20 else 2 if share >= 10 else 1 if share >= 4 else 0
    tr, growth, first, second = trend(ids)
    sc = t.get("scores") or {}
    impact, act = min(max(int(sc.get("impact", 0) or 0), 0), 3), min(max(int(sc.get("actionability", 0) or 0), 0), 2)
    per = {}
    for i in ids:
        per[by_id[i]["source"]] = per.get(by_id[i]["source"], 0) + 1
    t["computed"] = {
        **stats([by_id[i] for i in ids]),
        "count": len(ids),
        "share": share,
        "sources": per,
        "firstHalf": first,
        "secondHalf": second,
        "trend": tr,
        "breadth": breadth,
        "growth": growth,
        "score": impact + act + breadth + growth,
        "items": ids,
    }
json.dump(data, open("themes.json", "w"), indent=2, ensure_ascii=False)

daily = []
for n in range((until - since).days + 1):
    d = (since + datetime.timedelta(days=n)).isoformat()
    day = [i for i in items if i["date"] == d]
    daily.append({"date": d, "count": len(day), "avgRating": stats(day)["avgRating"]})
totals = {"items": len(items), **stats(items)}


def counted(t, fields):
    """A theme as summary.json shows it: its name and kind, with the numbers code counted."""
    return {"id": t["id"], "title": t["title"], "kind": t.get("kind"), **{k: t["computed"][k] for k in fields}}


THEME_FIELDS = ("count", "share", "avgRating", "lowShare", "trend", "firstHalf", "secondHalf", "score", "sources")
kept_ids = {t["id"] for t in data["themes"] if t.get("decision") in ("keep", "watch")}
untagged = sum(1 for tids in tags.values() if not set(tids) & kept_ids)
kept = sorted((t for t in data["themes"] if t.get("decision") == "keep"), key=lambda t: -t["computed"]["score"])
summary = {
    "date": info["date"],
    "window": {"since": info["since"], "until": info["until"], "label": info["windowLabel"]},
    "totals": totals,
    "capped": capped,
    "untaggedShare": round(100 * untagged / N),
    "daily": daily,
    "themes": [counted(t, THEME_FIELDS) for t in kept],
    "watch": [
        counted(t, ("count", "share", "trend", "sources")) for t in data["themes"] if t.get("decision") == "watch"
    ],
    "sources": {st: sum(e["status"] == st for e in log["sources"]) for st in ("ok", "blocked", "error")},
    "connections": [
        {k: e.get(k) for k in ("id", "label", "type", "status", "kept", "private", "link", "reason", "note")}
        for e in log["sources"]
    ],
}
json.dump(summary, open("summary.json", "w"), indent=2, ensure_ascii=False)
for t in kept:
    c = t["computed"]
    print(f"{c['score']:>2}  {t['id']:<30} {c['count']:>4} items  {c['share']:>5}%  {c['trend']}")
print(
    f"{len(items)} items, {len(kept)} kept themes, {summary['untaggedShare']}% fit no kept theme -> themes.json, summary.json"
)
errors = checks.run(cfg, info, "themes")
if summary["untaggedShare"] > cfg["scope"]["themes"]["maxUntaggedShare"]:
    errors.append(
        f"{summary['untaggedShare']}% of items fit no kept theme (limit {cfg['scope']['themes']['maxUntaggedShare']}%); "
        "read the untagged items again, add or widen a theme, and retag"
    )
if errors:
    sys.exit("FIX themes.json or tags/, then run summarise.py again:\n  " + "\n  ".join(errors))
print(f"next: write plan.json and live_content.json, then run: python3 engine/steps/render.py {cfg['key']}")
