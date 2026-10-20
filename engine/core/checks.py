import datetime
import json
import os
import re

SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
CITE = re.compile(r"\[\s*([A-Za-z0-9_]+-\d{3}(?:\s*,\s*[A-Za-z0-9_]+-\d{3})*)\s*\]")
DATES = re.compile(
    r"\b\d{1,2}\s+[A-Z][a-z]{2,8}\b|\b[A-Z][a-z]{2,8}\s+\d{1,2}\b|\b(?:19|20)\d{2}\b|\b\d{4}-\d{2}-\d{2}\b"
)
PLAIN_PUNCTUATION = {"\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u2026": "...", "\u00a0": " "}
KINDS = ("problem", "request", "praise", "question")
DECISIONS = ("keep", "watch", "drop")


# ---------------------------------------------------------------- helpers


def load(path):
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def items_by_id():
    return {item["id"]: item for item in (load("items.json") or {"items": []})["items"]}


def themes_with(decision="keep"):
    """Themes in themes.json with this decision that summarise.py has counted."""
    themes = (load("themes.json") or {}).get("themes", [])
    return {t["id"]: t for t in themes if t.get("decision") == decision and t.get("computed")}


def norm(text):
    text = str(text or "")
    for fancy, plain in PLAIN_PUNCTUATION.items():
        text = text.replace(fancy, plain)
    return re.sub(r"\s+", " ", text).strip()


def verbatim(quote, item):
    """True if the quote appears word for word in the item."""
    quote = norm(quote).strip(" .\"'")
    return bool(quote) and (quote in norm(item.get("text")) or quote in norm(item.get("title")))


def citations(text):
    """Item ids cited in a piece of text, written like [tickets-012] or [tickets-012, survey-087]."""
    ids = []
    for group in CITE.findall(str(text or "")):
        ids += [i.strip() for i in group.split(",")]
    return ids


def sentences(text):
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z])", str(text or "").strip())
    return [part for part in parts if part.strip()]


def check_text(errors, path, value):
    if not isinstance(value, str) or not value.strip():
        errors.append(f"`{path}` is empty")
    elif re.search(r"https?://", value):
        errors.append(f"`{path}` contains a link; links are added at render time")


def check_cited(errors, path, text, allowed, by_id):
    """Every sentence cites at least one item; every cited item exists and belongs to the theme."""
    for n, sentence in enumerate(sentences(text), 1):
        ids = citations(sentence)
        if not ids:
            errors.append(
                f"`{path}` sentence {n} cites no items; end it with the ids it rests on, like [tickets-012, survey-087]"
            )
        for item_id in ids:
            if item_id not in by_id:
                errors.append(f"`{path}` cites `{item_id}`, which is not a collected item")
            elif allowed is not None and item_id not in allowed:
                errors.append(f"`{path}` cites `{item_id}`, which is not tagged with this theme")


def tagged_items(theme):
    return set((theme or {}).get("computed", {}).get("items") or [])


def checked_quotes(theme):
    return {(e.get("item"), norm(e.get("quote"))) for e in (theme or {}).get("evidence") or []}


def check_quotes(errors, path, quotes, allowed_quotes):
    for j, quote in enumerate(quotes):
        if (quote.get("item"), norm(quote.get("text") or quote.get("quote"))) not in allowed_quotes:
            errors.append(f"`{path}.quotes[{j}]` is not one of the theme's checked quotes")


# ---------------------------------------------------------------- items.json


def items(cfg, info):
    errors = []
    approved = {source["id"] for source in cfg["sources"]}
    for k, item in enumerate((load("items.json") or {"items": []})["items"]):
        if item.get("source") not in approved:
            errors.append(f"items[{k}] comes from `{item.get('source')}`, not an approved connection")
        if not info["since"] <= str(item.get("date")) <= info["until"]:
            errors.append(f"items[{k}] is dated {item.get('date')}, outside the window")
    return errors


# ---------------------------------------------------------------- themes.json


def check_evidence(errors, path, theme, cfg, by_id):
    """Quotes must be word for word, from tagged items the brief may quote (private items need privateQuotes).
    A theme built only from private feedback is described and cited, not quoted."""
    limits = cfg["scope"]["themes"]
    private_ok = cfg["userScope"].get("privateQuotes", True)
    tagged = theme.get("computed", {}).get("items") or []
    quotable = [i for i in tagged if private_ok or not (by_id.get(i) or {}).get("private")]
    wanted = 1 if theme.get("decision") == "watch" else limits["minEvidence"]
    needed = min(wanted, len(quotable))

    evidence = theme.get("evidence") or []
    if len(evidence) < needed:
        errors.append(f"`{path}` needs at least {needed} quote{'s' if needed > 1 else ''}")
    for j, quote in enumerate(evidence):
        where = f"`{path}.evidence[{j}]`"
        item = by_id.get(quote.get("item"))
        if not item or quote["item"] not in tagged:
            errors.append(f"{where} must name an item tagged with this theme")
            continue
        if len(norm(quote.get("quote")).split()) < limits["minQuoteWords"]:
            errors.append(f"{where} is shorter than {limits['minQuoteWords']} words")
        if not verbatim(quote.get("quote"), item):
            errors.append(f"{where} does not appear word for word in `{quote['item']}`; copy it exactly")
        if item.get("private") and not private_ok:
            errors.append(f"{where} quotes a private item; describe it instead")


def themes(cfg, info):
    errors, limits, by_id = [], cfg["scope"]["themes"], items_by_id()
    seen, kept, watched = set(), 0, 0
    for k, theme in enumerate((load("themes.json") or {}).get("themes") or []):
        path = f"themes[{k}] ({theme.get('id')})"
        if not SLUG.match(str(theme.get("id", ""))) or theme.get("id") in seen:
            errors.append(f"`{path}.id` must be a unique lowercase slug")
        seen.add(theme.get("id"))
        if theme.get("kind") not in KINDS:
            errors.append(f"`{path}.kind` must be problem, request, praise or question")
        if theme.get("decision") not in DECISIONS or not str(theme.get("reason", "")).strip():
            errors.append(f"`{path}` needs a decision (keep, watch or drop) and a reason")
        for field in ("title", "summary"):
            check_text(errors, f"{path}.{field}", theme.get(field))

        scores, computed = theme.get("scores") or {}, theme.get("computed") or {}
        for field, top in (("impact", 3), ("actionability", 2)):
            if not isinstance(scores.get(field), int) or not 0 <= scores[field] <= top:
                errors.append(f"`{path}.scores.{field}` must be a whole number from 0 to {top}")

        score = computed.get("score", 0)
        if theme.get("decision") == "watch":  # rare but serious: below the keep score, still shown
            watched += 1
            share = computed.get("share", 0)
            if share > limits["watchMaxShare"]:
                errors.append(f"`{path}` is {share}% of feedback; the watchlist is for rare items (up to {limits['watchMaxShare']}%), so keep it")
            if scores.get("impact", 0) < 2:
                errors.append(f"`{path}` is on the watchlist, which is only for serious items (impact 2 or 3)")
            if not computed.get("count"):
                errors.append(f"`{path}` is on the watchlist but no item is tagged with it")
        elif theme.get("decision") == "keep":
            kept += 1
            if score < limits["keepScore"]:
                errors.append(
                    f"`{path}` is kept with score {score}; below {limits['keepScore']} drop it, or watch it if it is serious"
                )
        else:
            continue
        check_evidence(errors, path, theme, cfg, by_id)

    if kept > limits["maxThemes"]:
        errors.append(f"{kept} kept themes; keep at most {limits['maxThemes']}")
    if watched > limits["maxWatch"]:
        errors.append(f"{watched} watched themes; watch at most {limits['maxWatch']}")
    return errors


# ---------------------------------------------------------------- brief_plan.json


def plan(cfg, info):
    errors, limits, kept, watched = [], cfg["scope"]["themes"], themes_with("keep"), themes_with("watch")
    brief_plan = load("brief_plan.json")
    if not brief_plan:
        return ["brief_plan.json not found"]
    check_text(errors, "headline", brief_plan.get("headline"))

    actions, shown = brief_plan.get("actions") or [], brief_plan.get("themes") or []
    if not brief_plan.get("quietWeek") and not 1 <= len(actions) <= 3:
        errors.append("`actions` needs one to three items (or quietWeek: true)")
    for k, action in enumerate(actions):
        theme = kept.get(action.get("theme"))
        if not theme:
            errors.append(f"`actions[{k}].theme` is not a kept theme")
            continue
        if theme["computed"]["score"] < limits["actionScore"]:
            errors.append(
                f"`actions[{k}]` theme scores {theme['computed']['score']}; actions need {limits['actionScore']}"
            )
        if action["theme"] not in shown:
            errors.append(f"action theme `{action['theme']}` must also be in `themes`")

    if not 1 <= len(shown) <= limits["maxThemes"] or any(tid not in kept for tid in shown):
        errors.append(f"`themes` must list 1 to {limits['maxThemes']} kept theme ids")
    praise = [tid for tid, theme in kept.items() if theme.get("kind") == "praise"]
    if praise and not any(tid in praise for tid in shown):
        errors.append(f"`themes` must include at least one praise theme for \"What's working\": {', '.join(praise)}")
    if sorted(brief_plan.get("watch") or []) != sorted(watched):
        errors.append(f"`watch` must list every watched theme: {', '.join(sorted(watched)) or 'none'}")
    return errors


# ---------------------------------------------------------------- live_content.json


def check_extras(errors, content):
    """The optional session link and the follow-up questions."""
    session = content.get("session") or {}
    resume = str(session.get("resume", ""))
    bad_url = session.get("url") and not str(session["url"]).startswith("https://")
    if session and (set(session) - {"url", "resume"} or bad_url or len(resume) > 200 or "\n" in resume):
        errors.append(
            '`session` is optional: {"url": "https://..."} or {"resume": "a one-line command"}, only if your harness gives you one'
        )

    questions = content.get("questions") or []
    if not 2 <= len(questions) <= 3:
        errors.append("`questions` needs 2 or 3 follow-up questions the reader could ask about this brief")
    for k, question in enumerate(questions):
        check_text(errors, f"questions[{k}]", question)
        if isinstance(question, str) and not question.strip().endswith("?"):
            errors.append(f"`questions[{k}]` should be a question")


def check_watchlist(errors, content, watched, by_id):
    for k, entry in enumerate(content.get("watch") or []):
        theme = watched.get(entry.get("id")) or {}
        allowed_quotes = checked_quotes(theme)
        quotes = entry.get("quotes") or []
        check_text(errors, f"watch[{k}].title", entry.get("title"))
        check_cited(errors, f"watch[{k}].why", entry.get("why"), tagged_items(theme), by_id)
        if not min(1, len(allowed_quotes)) <= len(quotes) <= 2:
            errors.append(f"`watch[{k}]` shows 1 or 2 quotes (none only if it has no quotable items)")
        check_quotes(errors, f"watch[{k}]", quotes, allowed_quotes)


def check_themes_shown(errors, content, kept, limits, by_id):
    for k, shown in enumerate(content.get("themes") or []):
        theme = kept.get(shown.get("id"))
        check_cited(errors, f"themes[{k}].summary", shown.get("summary"), tagged_items(theme), by_id)
        if shown.get("who"):  # optional: who is affected, as customers describe it
            check_cited(errors, f"themes[{k}].who", shown.get("who"), tagged_items(theme), by_id)

        allowed_quotes, quotes = checked_quotes(theme), shown.get("quotes") or []
        most = limits["maxQuotesPerTheme"]
        wanted = min(most, len(allowed_quotes))
        if not wanted <= len(quotes) <= most:
            errors.append(
                f"`themes[{k}]` shows {wanted} quotes (it has {len(allowed_quotes)} checked quotes; the most shown is {most})"
            )
        cited = set(citations(shown.get("summary")))
        for quote in quotes:
            if quote.get("item") not in cited:
                errors.append(f"`themes[{k}].summary` should cite `{quote.get('item')}`, the item its quote comes from")
        check_quotes(errors, f"themes[{k}]", quotes, allowed_quotes)


def check_actions(errors, content, kept, by_id):
    for k, action in enumerate(content.get("actions") or []):
        allowed = tagged_items(kept.get(action.get("theme")))
        ticket = action.get("ticket") or {}
        check_cited(errors, f"actions[{k}].detail", action.get("detail"), allowed, by_id)
        if "issue" not in ticket and ticket.get("body"):  # the older shape: citations inside the body
            check_cited(errors, f"actions[{k}].ticket.body", ticket.get("body"), allowed, by_id)
            check_text(errors, f"actions[{k}].ticket.title", ticket.get("title"))
            continue
        for field in ("title", "issue"):
            check_text(errors, f"actions[{k}].ticket.{field}", ticket.get(field))
        cited = ticket.get("items") or []
        if not cited:
            errors.append(f"`actions[{k}].ticket.items` must list the feedback the ticket rests on")
        for item_id in cited:
            if item_id not in by_id:
                errors.append(f"`actions[{k}].ticket.items` lists `{item_id}`, which is not a collected item")
            elif item_id not in allowed:
                errors.append(f"`actions[{k}].ticket.items` lists `{item_id}`, which is not tagged with this theme")


def numbers_in(text):
    """Numbers a reader would check (above 10, or with a decimal point), ignoring dates."""
    found = []
    for number in re.findall(r"\d+(?:\.\d+)*", DATES.sub(" ", str(text or ""))):
        if number.count(".") > 1:
            found.append(number)
        elif "." in number or int(number) > 10:
            found.append(f"{float(number):g}")
    return found


def known_numbers(value, known):
    """Every number in summary.json, as written, rounded, and without its sign."""
    if isinstance(value, dict):
        for v in value.values():
            known_numbers(v, known)
    elif isinstance(value, list):
        for v in value:
            known_numbers(v, known)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        for v in (value, abs(value)):
            for places in (0, 1):
                known.add(f"{round(v, places):g}")


def check_numbers(errors, content, by_id):
    """Every number in the writing must come from summary.json or the feedback itself."""
    known = set()
    known_numbers(load("summary.json"), known)
    for item in by_id.values():
        known |= set(numbers_in(f"{item.get('title', '')} {item.get('text', '')}"))

    fields = [(f, content.get(f)) for f in ("headline", "preheader", "subject")]
    for k, action in enumerate(content.get("actions") or []):
        ticket = action.get("ticket") or {}
        fields += [(f"actions[{k}].title", action.get("title")), (f"actions[{k}].detail", action.get("detail"))]
        fields += [
            (f"actions[{k}].ticket.title", ticket.get("title")),
            (f"actions[{k}].ticket.issue", ticket.get("issue") or ticket.get("body")),
        ]
    for k, theme in enumerate(content.get("themes") or []):
        fields += [(f"themes[{k}].title", theme.get("title")), (f"themes[{k}].summary", theme.get("summary"))]

    for path, text in fields:
        for number in numbers_in(CITE.sub(" ", str(text or ""))):  # item ids in citations aren't numbers
            if number not in known:
                errors.append(f"`{path}` uses the number {number}, which is not in summary.json or the feedback")


def content(cfg, info):
    errors, limits = [], cfg["scope"]["themes"]
    live = load("live_content.json")
    if not live:
        return ["live_content.json not found"]
    brief_plan, kept, watched, by_id = (
        load("brief_plan.json") or {},
        themes_with("keep"),
        themes_with("watch"),
        items_by_id(),
    )

    meta = live.get("meta") or {}
    if meta.get("dateLabel") != info["dateLabel"] or meta.get("windowLabel") != info["windowLabel"]:
        errors.append(
            f"`meta` must copy dateLabel \"{info['dateLabel']}\" and windowLabel \"{info['windowLabel']}\" from run.json"
        )
    for field in ("subject", "preheader", "headline", "footer"):
        check_text(errors, field, live.get(field))
    check_extras(errors, live)

    if [a.get("theme") for a in live.get("actions") or []] != [a.get("theme") for a in brief_plan.get("actions") or []]:
        errors.append("`actions` must follow the plan")
    if [t.get("id") for t in live.get("themes") or []] != brief_plan.get("themes"):
        errors.append("`themes` must be the plan's themes, in order")
    if [w.get("id") for w in live.get("watch") or []] != (brief_plan.get("watch") or []):
        errors.append("`watch` must be the plan's watched themes, in order")

    check_watchlist(errors, live, watched, by_id)
    check_themes_shown(errors, live, kept, limits, by_id)
    check_actions(errors, live, kept, by_id)
    for item_id in citations(live.get("headline")):
        if item_id not in by_id:
            errors.append(f"`headline` cites `{item_id}`, which is not a collected item")
    check_numbers(errors, live, by_id)
    return errors


# ---------------------------------------------------------------- run


CHECKS = {"items": items, "themes": themes, "plan": plan, "content": content}


def run(cfg, info, *names):
    """Run the named checks; return every error, labelled, and log failures for the run's metrics."""
    errors = [f"{name}: {error}" for name in names for error in CHECKS[name](cfg, info)]
    if errors:
        entry = {"at": datetime.datetime.now().isoformat(timespec="seconds"), "checks": list(names), "errors": errors}
        with open("checks_log.jsonl", "a") as f:
            f.write(json.dumps(entry) + "\n")
    return errors
