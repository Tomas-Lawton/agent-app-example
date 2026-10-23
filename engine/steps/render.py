import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # engine/
import datetime, html, json, shutil, string
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
from core import config, checks

cfg, info = config.open_run(config.key_arg())
errors = checks.run(cfg, info, "plan", "content")
if errors:
    sys.exit("FIX plan.json or live_content.json, then run render.py again:\n  " + "\n  ".join(errors))
x = json.load(open("live_content.json"))
for entry in (x.get("themes") or []) + (x.get("watch") or []):  # a quote's words may be under "text" or "quote"
    for q in entry.get("quotes") or []:
        q.setdefault("text", q.get("quote", ""))
S = json.load(open("summary.json"))
items = {i["id"]: i for i in json.load(open("items.json"))["items"]}
conns = {c["id"]: c for c in S.get("connections", [])}
TH = cfg.get("theme") or {}
BRAND, ACCENT = TH.get("brand", "#1f3a5f"), TH.get("accent", "#e07a2f")
KINDS = (("problem", "#c2410c"), ("request", "#2563eb"), ("praise", "#15803d"), ("question", "#7c3aed"))
KIND = {k: TH.get(k, default) for k, default in KINDS}
TREND = {"rising": "Rising this period", "easing": "Easing"}
NAME = cfg.get("wording", {}).get("title", "Customer Pulse")
PRODUCT = cfg.get("product", "")
TEMPLATE = os.path.join(config.ENGINE, "pulse.html")  # the page skeleton and its one stylesheet
e = lambda s: html.escape(str(s if s is not None else ""))
themes_by_id = {t["id"]: t for t in S["themes"]}
CITED = []  # item ids in order of first citation, numbered [1], [2] ... across the pulse
SRC_COLOURS = ["#334155", "#0f766e", "#9333ea", "#b45309", "#be123c"]
SRC_CLASS = {c["id"]: f"s{n % 5}" for n, c in enumerate(S.get("connections", []))}
TABLE = "<table role='presentation' width='100%' cellpadding='0' cellspacing='0'>"


CLAIMS = checks.claims(x, items)
VERDICTS = json.load(open("verdicts.json")) if os.path.exists("verdicts.json") else {}
verified = lambda where: bool(VERDICTS) and all(
    VERDICTS.get(c["id"], {}).get("supported") for c in CLAIMS if c["where"] == where
)


# ---------------------------------------------------------------- pieces
def stars(r, scale):
    if r is None or not scale:
        return ""
    n = round(r / scale * 5)
    return f"<span class='accent'>{'&#9733;' * n}</span><span class='off'>{'&#9733;' * (5 - n)}</span>"


def source_label(sid):
    c = conns.get(sid, {})
    label = e(c.get("label") or sid)
    return f"<a href='{e(c['link'])}'>{label}</a>" if c.get("link") else label


def source_tag(sid):
    return f"<span class='tag {SRC_CLASS.get(sid, 's0')}'>{source_label(sid)}</span>"


def source_counts(s):
    return "".join(f"{source_tag(k)}<span class='count'>{v}</span>" for k, v in (s.get("sources") or {}).items())


def row(inner, cls="pad"):
    return f"<tr><td class='{cls}'>{inner}</td></tr>"


def card(inner, cls=""):
    return row(f"<div class='box {cls}'>{inner}</div>")


def grid(boxes):
    """Two (inner, class) boxes side by side (they stack on a phone); an odd last box takes the full width."""
    cell = lambda inner, cls: f"<td class='col box {cls}' width='49%' valign='top'>{inner}</td>"
    pairs = zip(boxes[0:-1:2], boxes[1::2])  # the cells are the cards, so both are always the same height
    rows = [row(f"{TABLE}<tr>{cell(*a)}<td class='gap' width='2%'></td>{cell(*b)}</tr></table>") for a, b in pairs]
    return "".join(rows) + (card(*boxes[-1]) if len(boxes) % 2 else "")


def section(title, sub=""):
    sub = f"<div class='secsub'>{sub}</div>" if sub else ""
    return row(f"<div class='sectitle'>{e(title)}</div><div class='rule'></div>{sub}", "sec")


def stat(label, value, sub=""):
    return (
        f"<td class='stat' width='25%'><div class='num'>{e(value)}</div><div class='lbl'>{e(label)}</div>"
        f"<div class='tiny'>{sub}</div></td>"
    )


def cite(text):
    """Escape the agent's text and turn its citations into numbered links to the evidence list."""

    def link(m):
        refs = []
        for i in [i.strip() for i in m.group(1).split(",")]:
            if i not in CITED:
                CITED.append(i)
            refs.append(f"<a href='#ev-{e(i)}'>{CITED.index(i) + 1}</a>")
        return f"<sup class='cite'>[{','.join(refs)}]</sup>"

    return checks.CITE.sub(link, e(text))


def label(where, n):
    """The small line under the agent's writing: its interpretation, how many items it cites, and whether verified."""
    tick = " &middot; <span class='ok'>&#10003; claims verified</span>" if verified(where) else ""
    return f"<div class='interp'>Agent's interpretation &middot; cites {n} item{'s' if n != 1 else ''}{tick}</div>"


def quote(q):
    it = items.get(q["item"], {})
    meta = " &middot; ".join(filter(None, [e(it.get("date")), stars(it.get("rating"), it.get("ratingScale"))]))
    link = f" &middot; <a href='{e(it['url'])}'>open</a>" if it.get("url") else ""
    return (
        f"<div class='quote'><div class='text'>&ldquo;{e(q['text'])}&rdquo;</div>"
        f"<div class='small'>{source_tag(it.get('source'))}{meta}{link}</div></div>"
    )


def action_ticket(a):
    """An action is its draft ticket: title, the issue, who owns it and the feedback it rests on."""
    tk = a.get("ticket") or {}
    refs = cite("[" + ", ".join(tk.get("items") or []) + "]") if tk.get("items") else ""
    return (
        f"<div class='lbl'>Draft ticket for {e(a.get('owner'))} &middot; not filed</div>"
        f"<div class='title'>{e(tk.get('title') or a.get('title'))}</div>"
        f"<div class='text'>{e(tk.get('issue'))}</div><div class='small'>Feedback: {refs}</div>"
    )


# ---------------------------------------------------------------- charts
def volume_chart():
    days = S["daily"]
    top = max([d["count"] for d in days] + [1])
    cols = "".join(
        f"<td valign='bottom' align='center'><div class='tiny'>{d['count']}</div>"
        f"<div class='vbar' style='height:{max(2, round(110 * d['count'] / top))}px'></div>"  # the bar's height is data
        f"<div class='tiny'>{d['date'][8:].lstrip('0')}</div>"
        f"<div class='tiny accent'>{d['avgRating'] if d['avgRating'] is not None else '&nbsp;'}</div></td>"
        for d in days
    )
    return (
        f"<div class='chart'>Feedback per day <span class='tiny'>(<span class='accent'>average rating</span> below)</span>"
        f"</div>{TABLE}<tr>{cols}</tr></table>"
    )


def themes_chart():
    ts = S["themes"]
    top = max([t["count"] for t in ts] + [1])
    rows = "".join(
        f"<tr><td width='40%' class='cell'>{e(t['title'])}</td><td>"
        f"<div class='bar b-{t['kind']}' style='width:{max(3, round(100 * t['count'] / top))}%'></div></td>"
        f"<td width='36' align='right' class='tiny'>{t['count']}</td></tr>"
        for t in ts
    )
    legend = " ".join(f"<span class='c-{k}'>&#9632; {k}</span>" for k in KIND)
    return (
        f"<div class='chart'>Items per theme</div>{TABLE}{rows}</table><div class='small'>{legend}</div>"
        f"<div class='small'>The agent gives each theme a kind after reading its feedback: <b>problem</b>, something "
        f"broken or in the way; <b>request</b>, something customers want added or changed; <b>praise</b>, something "
        f"working well; <b>question</b>, customers unsure how something works.</div>"
    )


# ---------------------------------------------------------------- the pulse
PRIVATE_NOTE = (
    "<div class='note'>No quotes: this feedback is private, so it is described and cited but not quoted "
    "(setup can allow quoting for a pulse that stays inside the company).</div>"
)
CAP_NOTE = f"Based on the newest {cfg['scope']['collect']['maxItems']} items in the window."


def header_rows(img):
    """The profile's header image as a plain banner, if it has one, then the title on a brand colour strip."""
    banner = row(f"<img class='banner' src='{img('header')}' width='760' alt=''/>", "") if img("header") else ""
    logo = img("logo")
    logo_td = f"<td width='92' valign='middle'><img class='logo' src='{logo}' width='76' height='76' alt=''/></td>"
    title = (
        f"<div class='prod'>{e(PRODUCT)}</div><div class='name'>{e(NAME)}</div>"
        f"<div class='when'>{e(x['meta']['dateLabel'])} &middot; feedback from {e(x['meta']['windowLabel'])}</div>"
    )
    strip = f"{TABLE}<tr>{logo_td if logo else ''}<td valign='middle'>{title}</td></tr></table>"
    return banner + f"<tr><td class='hd' bgcolor='{BRAND}'>{strip}</td></tr>"


def stats_row():
    t, src, na = S["totals"], S["sources"], lambda v, unit="": "n/a" if v is None else f"{v}{unit}"
    stats = [
        stat("Items", t["items"], "newest in the window" if S.get("capped") else ""),
        stat("Avg rating", na(t["avgRating"])),
        stat("1 or 2 stars", na(t["lowShare"], "%")),
        stat(
            "Connections",
            f"{src['ok']} of {sum(src.values())}",
            f"{src['blocked']} blocked" if src["blocked"] else "all read",
        ),
    ]
    return row(TABLE.replace("<table", "<table class='stats'") + f"<tr>{''.join(stats)}</tr></table>", "top")


def read_from_row():
    chips = []
    for c in S.get("connections", []):
        ok = c["status"] == "ok"
        tail = f"{c.get('kept', 0)} items" if ok else c["status"]
        lock = " &middot; private" if c.get("private") else ""
        chips.append(
            f"<div class='small'>{source_tag(c['id'])}<span class='{'ink' if ok else 'bad'}'>"
            f"{e(c['type'])} &middot; {e(tail)}{lock}</span></div>"
        )
    cap = f"<div class='small'>{e(CAP_NOTE)}</div>" if S.get("capped") else ""
    return row(f"<div class='small'>Read from:</div>{''.join(chips)}{cap}", "top")


def theme_card(th):
    s = themes_by_id[th["id"]]
    trend = f"<span class='pill {s['trend']}'>{TREND[s['trend']]}</span>" if s["trend"] in TREND else ""
    rating = f" &middot; average rating {s['avgRating']}" if s["avgRating"] is not None else ""
    size = f"{s['count']} items &middot; {s['share']}% of all feedback &middot; {s['firstHalf']} then {s['secondHalf']} across the period"
    inner = (
        f"<a name='{e(th['id'])}' id='{e(th['id'])}'></a><div><span class='pill solid p-{s['kind']}'>{e(s['kind'])}</span>{trend}</div>"
        f"<div class='title'>{e(th['title'])}</div><div class='small'>{size}{rating}</div>"
        f"<div class='text'>{cite(th['summary'])}</div>"
        + label(f"theme {th['id']}", len(set(checks.citations(th["summary"]))))
        + ("".join(quote(q) for q in th["quotes"]) or PRIVATE_NOTE)
        + f"<div class='small'>From {source_counts(s)}</div>"
    )
    return inner, f"k-{s['kind']}"


def theme_rows():
    issues = [th for th in x["themes"] if themes_by_id[th["id"]]["kind"] != "praise"]
    working = [th for th in x["themes"] if themes_by_id[th["id"]]["kind"] == "praise"]
    rows = []
    if issues:
        rows.append(section("What customers are saying", "Every quote is word for word, with its source"))
        rows += [card(*theme_card(th)) for th in issues]
    if working:
        rows.append(section("What's working", "What customers praise: worth passing on to the teams behind it"))
        rows.append(grid([theme_card(th) for th in working]))
    return rows


def watch_box(w, s):
    count = s.get("count", 0)
    inner = (
        f"<div class='title'>{e(w['title'])}</div>"
        f"<div class='small'>{count} item{'s' if count != 1 else ''} &middot; From {source_counts(s)}</div>"
        f"<div class='text'>{cite(w['why'])}</div>"
        + label(f"watch {w['id']}", len(set(checks.citations(w["why"]))))
        + "".join(quote(q) for q in w.get("quotes") or [])
    )
    return inner, "watch"


def watch_rows():
    if not x.get("watch"):
        return []
    watch_by_id = {w["id"]: w for w in S.get("watch", [])}
    boxes = [watch_box(w, watch_by_id.get(w["id"], {})) for w in x["watch"]]
    return [section("Watchlist", "Rare but serious: only a few items, but worth knowing about"), grid(boxes)]


def action_rows():
    if not x.get("actions"):
        return []
    rows = [section("Take action", "Ranked by impact, reach and growth, each with a draft ticket for the owning team")]
    for n, a in enumerate(x["actions"], 1):
        badge = f"<td width='40' valign='top'><div class='badge'>{n}</div></td>"
        rows.append(card(f"{TABLE}<tr>{badge}<td valign='top'>{action_ticket(a)}</td></tr></table>"))
    return rows


def ask_rows():
    qs = "".join(f"<li>&ldquo;{e(q)}&rdquo;</li>" for q in x.get("questions") or [])
    return [
        section("Ask your agent"),
        card(
            f"<div class='text'>Ask the agent in the conversation where this pulse was made, or open the project in "
            f"your agent harness. It answers from this pulse's evidence, with every claim cited. For example:"
            f"<ul>{qs}</ul></div><div class='small'>You can also ask it to change the pulse "
            f"(&ldquo;make it shorter&rdquo;) or add a connection.</div>"
        ),
    ]


def footer_row():
    srcs = []
    for c in S.get("connections", []):
        tail = f"{c.get('kept', 0)} items" if c["status"] == "ok" else f"{c['status']}: {c.get('reason', '')}"
        if c.get("note"):
            tail += f" ({c['note']})"
        srcs.append(f"{source_label(c['id'])}{' (private)' if c.get('private') else ''}: {e(tail)}")
    return row(
        f"<b>Sources.</b> {'; '.join(srcs)}.<br/>{e(x['footer'])}<br/>Written by an AI agent. Every quote was checked "
        f"word for word against the collected feedback, every number was computed by code, and private feedback is "
        f"quoted only when setup allows it. Names, emails and reference numbers are removed before anything is written.",
        "foot",
    )


def evidence_row(n, i):
    it = items.get(i, {})
    link = f" &middot; <a href='{e(it['url'])}'>open</a>" if it.get("url") else ""
    text = (f"{it['title']}: " if it.get("title") else "") + it.get("text", "")
    if len(text) > 160:  # one short line per item keeps the email small; the full text stays with the run
        text = text[:157].rsplit(" ", 1)[0] + "…"
    return (
        f"<tr id='ev-{e(i)}'><td class='ev'><b>[{n}]</b> {source_tag(it.get('source'))}<span class='tiny'>{e(i)} "
        f"&middot; {e(it.get('date'))} {stars(it.get('rating'), it.get('ratingScale'))}{link}</span><br/>{e(text)}</td></tr>"
    )


def evidence():
    """The items the pulse cites, numbered. Everything collected stays with the run, for the agent to answer questions from."""
    rows = "".join(evidence_row(n, i) for n, i in enumerate(CITED, 1))
    more = f"<div class='small'>All {len(items)} items collected are kept with this run; ask your agent about any of them.</div>"
    return section("Evidence", "Every item the pulse cites") + card(f"{TABLE}{rows}</table>{more}")


def body(img):
    rows = [
        header_rows(img),
        row(cite(x["headline"]), "headline"),
        stats_row(),
        read_from_row(),
        section("At a glance"),
        card(volume_chart()),
        card(themes_chart()),
    ]
    rows += theme_rows() + watch_rows() + action_rows() + ask_rows()
    rows += [footer_row(), evidence()]  # the evidence comes last, once every citation is numbered
    return "".join(rows)


def colour_rules():
    """Stylesheet rules for the theme kinds and the connections, in the profile's colours."""
    rules = [
        f".k-{k}{{border-left:4px solid {c}}}.b-{k},.p-{k}{{background:{c};border-color:{c}}}.c-{k}{{color:{c}}}"
        for k, c in KIND.items()
    ]
    return "\n".join(rules + [f".s{n}{{color:{c};border-color:{c}}}" for n, c in enumerate(SRC_COLOURS)])


def page(img):
    """The pulse as one email-safe page: tables, one stylesheet in the head, no scripts."""
    greys = {"ink": "#111827", "muted": "#6b7280", "line": "#e5e7eb", "bg": "#f5f6f8"}
    colours = dict(
        {k: TH.get(k, v) for k, v in greys.items()}, brand=BRAND, brand2=TH.get("brand2", ACCENT), accent=ACCENT
    )
    page_body = body(img)
    template = string.Template(open(TEMPLATE).read())
    return template.substitute(
        colours, title=e(x["subject"]), preheader=e(x["preheader"]), kinds=colour_rules(), body=page_body
    )


def chat_summary():
    """The short version for the chat (and the email's plain text part), from the same computed numbers."""
    out = [f"# {NAME}", f"*{PRODUCT} · {x['meta']['dateLabel']} · feedback from {x['meta']['windowLabel']}*"]
    out += ["", x["headline"]] + (["", f"*{CAP_NOTE}*"] if S.get("capped") else [])
    if x.get("actions"):
        out += ["", "## Top actions"]
        for n, a in enumerate(x["actions"], 1):
            tk = a.get("ticket") or {}
            out.append(
                f"{n}. **{tk.get('title') or a.get('title', '')}** ({a.get('owner', '')}): {tk.get('issue', '')}"
            )
    out += ["", "## Themes"]
    for th in x["themes"]:
        s = themes_by_id[th["id"]]
        out.append(f"- {th['title']} ({s['count']} items, {s['share']}%)")
    if x.get("watch"):
        counts = {w["id"]: w.get("count", 0) for w in S.get("watch", [])}
        out += ["", "## Watchlist"] + [f"- {w['title']} ({counts.get(w['id'], 0)} items)" for w in x["watch"]]
    out += ["", "## Ask your agent"] + [f"- {q}" for q in x.get("questions") or []]
    out += ["", "The full pulse, with quotes and evidence, is in preview.html."]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- write
def images():
    """The profile's own images (assets/header and assets/logo, PNG or JPG), copied next to the preview."""
    found, assets = {}, os.path.join(config.ROOT, "profiles", cfg["key"], "assets")
    for name in ("header", "logo"):
        paths = [os.path.join(assets, f"{name}.{ext}") for ext in ("png", "jpg", "jpeg")]
        path = next((p for p in paths if os.path.exists(p)), None)
        if path:
            found[name] = os.path.basename(shutil.copy(path, "out"))
    return found


def email_message(html_part, text_part, files, cids):
    m = EmailMessage()
    m["Subject"], m["To"] = x["subject"], cfg["recipient"]
    m["Date"] = format_datetime(datetime.datetime.now().astimezone())
    m.set_content(text_part)
    m.add_alternative(html_part, subtype="html")
    for name, cid in cids.items():  # embedded, so Gmail shows them without fetching
        kind = "png" if files[name].endswith(".png") else "jpeg"
        data = open(f"out/{files[name]}", "rb").read()
        m.get_payload()[1].add_related(data, "image", kind, cid=f"<{cid}>", disposition="inline", filename=files[name])
    return m


os.makedirs("out", exist_ok=True)
files = images()
cids = {name: make_msgid(domain="pulse.local")[1:-1] for name in files}
html_part = page(lambda name: f"cid:{cids[name]}" if name in cids else "")
preview = html_part
for name, cid in cids.items():  # the same page; in a browser the images are the files next to it
    preview = preview.replace(f"cid:{cid}", files[name])
summary_text = chat_summary()
open("out/preview.html", "w").write(preview)
open("out/pulse.md", "w").write(summary_text)
json.dump(CLAIMS, open("out/claims.json", "w"), indent=1, ensure_ascii=False)
open("out/email.eml", "wb").write(bytes(email_message(html_part, summary_text, files, cids)))
print(f"wrote {info['folder']}/out/pulse.md, preview.html, claims.json and email.eml")
print(f"preview: {os.path.abspath('out/preview.html')}")
