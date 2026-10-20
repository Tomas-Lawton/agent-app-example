"""Step 2: count everything from the agent's tags, then check. The model judges; code counts.

Usage (from the repository root, after writing themes.json and tags/):  python3 engine/steps/summarise.py <key>

The agent reads every item (reading/part_NN.txt), writes themes.json, and tags every item in tags/part_NN.json
(item id -> theme ids, [] if none fits). This script checks every item is tagged, then counts each theme exactly:
items, share, average rating out of 5, share at one or two stars, items per connection, and two trends computed from
real dates: the first half of the window against the second, and the share against the previous run. Writes
`computed` on every theme and summary.json, then checks themes.json and stops with what to fix.

Score = impact (0-3, agent) + actionability (0-2, agent) + breadth (0-3, from share) + growth (0-2, from the trends).
"""
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
for p in ["tags/carried.json"] + sorted(glob.glob("tags/part_*.json")):  # this run's tags override carried ones
    if not os.path.exists(p):
        continue
    for iid, tids in json.load(open(p)).items():
        tags[iid] = [tids] if isinstance(tids, str) else list(tids or [])
missing = [i for i in by_id if i not in tags]
if missing:
    sys.exit(f"FIX: {len(missing)} of {len(items)} items are not tagged (for example {', '.join(missing[:5])}). "
             "Tag every item in tags/part_NN.json, using [] when no theme fits, then run summarise.py again.")

N = len(items) or 1
meta = json.load(open("items.json"))
window = json.load(open("window.json")) if os.path.exists("window.json") else items  # everything collected in the window
since, until = datetime.date.fromisoformat(info["since"]), datetime.date.fromisoformat(info["until"])
covered = max(since, datetime.date.fromisoformat(meta.get("coverageFrom") or info["since"]))  # the dates the agent read
mid = covered + (until - covered) / 2  # trends inside the run compare halves of the covered dates, never empty days


def five(it):
    r, s = it.get("rating"), it.get("ratingScale")
    return None if r is None or not s else r / s * 5


def stats(lst):
    rated = [five(i) for i in lst if five(i) is not None]
    return {"avgRating": round(sum(rated) / len(rated), 1) if rated else None,
            "lowShare": round(100 * sum(r <= 2 for r in rated) / len(rated)) if rated else None}


prev, prev_sum = None, None
if info.get("previous"):
    d = os.path.join(config.ROOT, info["previous"])
    if os.path.exists(os.path.join(d, "themes.json")):
        prev = {t["id"]: t["computed"] for t in json.load(open(os.path.join(d, "themes.json")))["themes"] if t.get("decision") == "keep" and t.get("computed")}
    if os.path.exists(os.path.join(d, "summary.json")):
        prev_sum = json.load(open(os.path.join(d, "summary.json")))


def trend(tid, ids, share):
    """Rising inside this window (second half against first), and new or growing against the previous run."""
    first = sum(1 for i in ids if datetime.date.fromisoformat(by_id[i]["date"]) <= mid)
    second = len(ids) - first
    rising = second >= 3 and second >= 1.5 * max(first, 1)
    if prev is not None and tid not in prev:
        return "new", 2 if share >= 4 else 1, first, second
    if prev is not None and share - prev[tid]["share"] >= max(5, prev[tid]["share"] * 0.5):
        return "growing", 2, first, second
    if rising:
        return "rising", 1, first, second
    if prev is not None and prev[tid]["share"] - share >= max(5, prev[tid]["share"] * 0.5):
        return "easing", 0, first, second
    return "steady", 0, first, second


for t in data.get("themes", []):
    ids = [i for i, tids in tags.items() if t.get("id") in tids and i in by_id]
    share = round(100 * len(ids) / N, 1)
    breadth = 3 if share >= 20 else 2 if share >= 10 else 1 if share >= 4 else 0
    tr, growth, first, second = trend(t.get("id"), ids, share)
    sc = t.get("scores") or {}
    impact, act = min(max(int(sc.get("impact", 0) or 0), 0), 3), min(max(int(sc.get("actionability", 0) or 0), 0), 2)
    per, days = {}, {}
    for i in ids:
        per[by_id[i]["source"]] = per.get(by_id[i]["source"], 0) + 1
        days[by_id[i]["date"]] = days.get(by_id[i]["date"], 0) + 1
    peak = max(days.items(), key=lambda kv: (kv[1], kv[0])) if days else (None, 0)
    t["computed"] = {**stats([by_id[i] for i in ids]), "count": len(ids), "share": share, "sources": per,
                     "firstHalf": first, "secondHalf": second, "trend": tr,
                     "firstSeen": min(days) if days else None, "peakDay": peak[0], "peakCount": peak[1],
                     "previousShare": None if prev is None else (prev.get(t.get("id")) or {}).get("share", 0),
                     "breadth": breadth, "growth": growth, "score": impact + act + breadth + growth, "items": ids}
json.dump(data, open("themes.json", "w"), indent=2, ensure_ascii=False)

daily = []
for n in range((until - since).days + 1):
    d = (since + datetime.timedelta(days=n)).isoformat()
    day = [i for i in window if i["date"] == d]
    daily.append({"date": d, "count": len(day), "avgRating": stats(day)["avgRating"]})
totals = {"items": len(window), "analysed": len(items), **stats(window)}
change = None
if prev_sum:
    p = prev_sum["totals"]
    change = {"items": totals["items"] - p["items"],
              "avgRating": None if None in (totals["avgRating"], p["avgRating"]) else round(totals["avgRating"] - p["avgRating"], 1),
              "lowShare": None if None in (totals["lowShare"], p["lowShare"]) else totals["lowShare"] - p["lowShare"]}
kept_ids = {t["id"] for t in data["themes"] if t.get("decision") in ("keep", "watch")}
untagged = sum(1 for tids in tags.values() if not set(tids) & kept_ids)
kept = sorted((t for t in data["themes"] if t.get("decision") == "keep"), key=lambda t: -t["computed"]["score"])
summary = {
    "date": info["date"], "window": {"since": info["since"], "until": info["until"], "label": info["windowLabel"]},
    "totals": totals, "capped": meta.get("capped", False),
    "coverage": {"from": covered.isoformat(), "until": info["until"], "analysed": len(items), "collected": len(window)},
    "untaggedShare": round(100 * untagged / N), "previous": prev_sum["date"] if prev_sum else None, "change": change, "daily": daily,
    "themes": [{"id": t["id"], "title": t["title"], "kind": t.get("kind"),
                **{k: t["computed"][k] for k in ("count", "share", "avgRating", "lowShare", "trend", "firstHalf", "secondHalf", "previousShare", "score", "sources", "firstSeen", "peakDay", "peakCount")},
                "impact": (t.get("scores") or {}).get("impact"), "actionability": (t.get("scores") or {}).get("actionability")}
               for t in kept],
    "watch": [{"id": t["id"], "title": t["title"], "kind": t.get("kind"), **{k: t["computed"][k] for k in ("count", "share", "trend", "sources")}}
              for t in data["themes"] if t.get("decision") == "watch"],
    "sources": {st: sum(e["status"] == st for e in log["sources"]) for st in ("ok", "blocked", "error")},
    "connections": [{k: e.get(k) for k in ("id", "label", "type", "status", "kept", "collected", "private", "link", "reason", "note")} for e in log["sources"]],
}
json.dump(summary, open("summary.json", "w"), indent=2, ensure_ascii=False)
for t in kept:
    c = t["computed"]
    print(f"{c['score']:>2}  {t['id']:<30} {c['count']:>4} items  {c['share']:>5}%  {c['trend']}")
print(f"{len(items)} items, {len(kept)} kept themes, {summary['untaggedShare']}% fit no kept theme -> themes.json, summary.json")
errors = checks.run(cfg, info, "themes")
if summary["untaggedShare"] > cfg["scope"]["themes"]["maxUntaggedShare"]:
    errors.append(f"{summary['untaggedShare']}% of items fit no kept theme (limit {cfg['scope']['themes']['maxUntaggedShare']}%); "
                  "read the untagged items again, add or widen a theme, and retag")
if errors:
    sys.exit("FIX themes.json or tags/, then run summarise.py again:\n  " + "\n  ".join(errors))
print(f"next: write brief_plan.json and live_content.json, then run: python3 engine/steps/render.py {cfg['key']}")
