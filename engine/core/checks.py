"""Every check on the files the agent writes. Imported by summarise.py, render.py and send.py, which stop on errors.

  items    only approved connections, inside the window
  themes   well formed, scored by code, above threshold; every quote word for word from a real, public item tagged with it
  plan     every pick is a kept, scored theme
  content  follows the plan; every quote is a checked quote; every action has a draft ticket; every number traces to
           summary.json or the feedback
"""
import json, os, re

SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SUBS = {"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2026": "...", "\u00a0": " "}


def load(p):
    return json.load(open(p)) if os.path.exists(p) else None


def norm(s):
    s = str(s or "")
    for a, b in SUBS.items():
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()


def verbatim(quote, item):
    q = norm(quote).strip(" .\"'")
    return bool(q) and (q in norm(item.get("text")) or q in norm(item.get("title")))


def _text(err, path, v):
    if not isinstance(v, str) or not v.strip(): err.append(f"`{path}` is empty")
    elif re.search(r"https?://", v): err.append(f"`{path}` contains a link; links are added at render time")


def items(cfg, info):
    err, d = [], load("items.json") or {"items": []}
    allowed = {s["id"] for s in cfg["sources"]}
    for k, it in enumerate(d["items"]):
        if it.get("source") not in allowed: err.append(f"items[{k}] comes from `{it.get('source')}`, not an approved connection")
        if not info["since"] <= str(it.get("date")) <= info["until"]: err.append(f"items[{k}] is dated {it.get('date')}, outside the window")
    return err


def themes(cfg, info):
    err, lim = [], cfg["scope"]["themes"]
    d, by_id = load("themes.json") or {}, {i["id"]: i for i in (load("items.json") or {"items": []})["items"]}
    ids, kept = set(), 0
    for k, t in enumerate(d.get("themes") or []):
        p = f"themes[{k}] ({t.get('id')})"
        if not SLUG.match(str(t.get("id", ""))) or t.get("id") in ids: err.append(f"`{p}.id` must be a unique lowercase slug")
        ids.add(t.get("id"))
        if t.get("kind") not in ("problem", "request", "praise", "question"): err.append(f"`{p}.kind` must be problem, request, praise or question")
        if t.get("decision") not in ("keep", "drop") or not str(t.get("reason", "")).strip(): err.append(f"`{p}` needs a decision and a reason")
        for f in ("title", "summary"): _text(err, f"{p}.{f}", t.get(f))
        sc, c = t.get("scores") or {}, t.get("computed") or {}
        for f, hi in (("impact", 3), ("actionability", 2)):
            if not isinstance(sc.get(f), int) or not 0 <= sc[f] <= hi: err.append(f"`{p}.scores.{f}` must be a whole number from 0 to {hi}")
        if t.get("decision") != "keep":
            continue
        kept += 1
        if c.get("score", 0) < lim["keepScore"]: err.append(f"`{p}` is kept with score {c.get('score')}; below {lim['keepScore']} must be dropped")
        ev = t.get("evidence") or []
        if len(ev) < lim["minEvidence"]: err.append(f"`{p}` needs at least {lim['minEvidence']} quotes")
        for j, e in enumerate(ev):
            it = by_id.get(e.get("item"))
            if not it or e["item"] not in (c.get("items") or []): err.append(f"`{p}.evidence[{j}]` must name an item tagged with this theme"); continue
            if len(norm(e.get("quote")).split()) < lim["minQuoteWords"]: err.append(f"`{p}.evidence[{j}]` is shorter than {lim['minQuoteWords']} words")
            if not verbatim(e.get("quote"), it): err.append(f"`{p}.evidence[{j}]` does not appear word for word in `{e['item']}`; copy it exactly")
            if it.get("private") and not cfg["userScope"].get("privateQuotes"): err.append(f"`{p}.evidence[{j}]` quotes a private item; describe it instead")
    if kept > lim["maxThemes"]: err.append(f"{kept} kept themes; keep at most {lim['maxThemes']}")
    return err


def _kept():
    return {t["id"]: t for t in (load("themes.json") or {}).get("themes", []) if t.get("decision") == "keep" and t.get("computed")}


def plan(cfg, info):
    err, lim, d, kept = [], cfg["scope"]["themes"], load("brief_plan.json"), _kept()
    if not d: return ["brief_plan.json not found"]
    _text(err, "headline", d.get("headline"))
    acts, show = d.get("actions") or [], d.get("themes") or []
    if not d.get("quietWeek") and not 1 <= len(acts) <= 3: err.append("`actions` needs one to three items (or quietWeek: true)")
    for k, a in enumerate(acts):
        t = kept.get(a.get("theme"))
        if not t: err.append(f"`actions[{k}].theme` is not a kept theme"); continue
        if t["computed"]["score"] < lim["actionScore"]: err.append(f"`actions[{k}]` theme scores {t['computed']['score']}; actions need {lim['actionScore']}")
        if a["theme"] not in show: err.append(f"action theme `{a['theme']}` must also be in `themes`")
    if not 1 <= len(show) <= lim["maxThemes"] or any(tid not in kept for tid in show): err.append(f"`themes` must list 1 to {lim['maxThemes']} kept theme ids")
    return err


def content(cfg, info):
    err, lim, x, p, kept = [], cfg["scope"]["themes"], load("live_content.json"), load("brief_plan.json") or {}, _kept()
    if not x: return ["live_content.json not found"]
    by_id = {i["id"]: i for i in load("items.json")["items"]}
    m = x.get("meta") or {}
    if m.get("dateLabel") != info["dateLabel"] or m.get("windowLabel") != info["windowLabel"]:
        err.append(f"`meta` must copy dateLabel \"{info['dateLabel']}\" and windowLabel \"{info['windowLabel']}\" from run.json")
    for f in ("subject", "preheader", "headline", "footer"): _text(err, f, x.get(f))
    if [a.get("theme") for a in x.get("actions") or []] != [a.get("theme") for a in p.get("actions") or []]: err.append("`actions` must follow the plan")
    if [t.get("id") for t in x.get("themes") or []] != p.get("themes"): err.append("`themes` must be the plan's themes, in order")
    for k, t in enumerate(x.get("themes") or []):
        ev = {(e.get("item"), norm(e.get("quote"))) for e in (kept.get(t.get("id")) or {}).get("evidence") or []}
        if not 1 <= len(t.get("quotes") or []) <= lim["maxQuotesPerTheme"]: err.append(f"`themes[{k}]` shows 1 to {lim['maxQuotesPerTheme']} quotes")
        for j, q in enumerate(t.get("quotes") or []):
            if (q.get("item"), norm(q.get("text"))) not in ev: err.append(f"`themes[{k}].quotes[{j}]` is not one of the theme's checked quotes")
    for k, a in enumerate(x.get("actions") or []):
        tk = a.get("ticket") or {}
        for f in ("title", "body"): _text(err, f"actions[{k}].ticket.{f}", tk.get(f))
    known = set()
    _harvest(load("summary.json"), known)
    for i in by_id.values():
        known |= set(_numbers(f"{i.get('title', '')} {i.get('text', '')}"))
    fields = [(f, x.get(f)) for f in ("headline", "preheader", "subject")]
    fields += [(f"actions[{k}].{f}", a.get(f)) for k, a in enumerate(x.get("actions") or []) for f in ("title", "detail")]
    fields += [(f"themes[{k}].{f}", t.get(f)) for k, t in enumerate(x.get("themes") or []) for f in ("title", "summary")]
    fields += [(f"actions[{k}].ticket.{f}", (a.get("ticket") or {}).get(f)) for k, a in enumerate(x.get("actions") or []) for f in ("title", "body")]
    for path, text in fields:
        for n in _numbers(text):
            if n not in known: err.append(f"`{path}` uses the number {n}, which is not in summary.json or the feedback")
    return err


DATES = re.compile(r"\b\d{1,2}\s+[A-Z][a-z]{2,8}\b|\b[A-Z][a-z]{2,8}\s+\d{1,2}\b|\b(?:19|20)\d{2}\b|\b\d{4}-\d{2}-\d{2}\b")


def _harvest(o, acc):
    if isinstance(o, dict): [_harvest(v, acc) for v in o.values()]
    elif isinstance(o, list): [_harvest(v, acc) for v in o]
    elif isinstance(o, (int, float)) and not isinstance(o, bool):
        acc |= {f"{round(v, n):g}" for v in (o, abs(o)) for n in (0, 1)}


def _numbers(text):
    out = []
    for n in re.findall(r"\d+(?:\.\d+)*", DATES.sub(" ", str(text or ""))):
        if n.count(".") > 1: out.append(n)
        elif "." in n or int(n) > 10: out.append(f"{float(n):g}")
    return out


def run(cfg, info, *names):
    """Run the named checks; return every error, labelled."""
    return [f"{n}: {e}" for n in names for e in globals()[n](cfg, info)]
