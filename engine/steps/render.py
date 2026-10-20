import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # engine/
import base64, datetime, glob, hashlib, html, json, urllib.parse
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
from core import config, checks

cfg, info = config.open_run(config.key_arg())
errors = checks.run(cfg, info, "plan", "content")
if errors:
    sys.exit("FIX brief_plan.json or live_content.json, then run render.py again:\n  " + "\n  ".join(errors))
x = json.load(open("live_content.json"))
S = json.load(open("summary.json"))
items = {i["id"]: i for i in json.load(open("items.json"))["items"]}
conns = {c["id"]: c for c in S.get("connections", [])}
TH = cfg.get("theme") or {}
BRAND, ACCENT = TH.get("brand", "#1f3a5f"), TH.get("accent", "#e07a2f")
BRAND2 = TH.get("brand2", ACCENT)
INK, MUTED, LINE, BG = (
    TH.get("ink", "#111827"),
    TH.get("muted", "#6b7280"),
    TH.get("line", "#e5e7eb"),
    TH.get("background", "#f5f6f8"),
)
TINT = TH.get("tint", "#e9efe9")
KIND = {
    "problem": TH.get("problem", "#c2410c"),
    "request": TH.get("request", "#2563eb"),
    "praise": TH.get("praise", "#15803d"),
    "question": TH.get("question", "#7c3aed"),
}
TREND = {
    "new": ("New", ACCENT),
    "growing": ("Growing", ACCENT),
    "rising": ("Rising this period", ACCENT),
    "easing": ("Easing", "#15803d"),
}
NAME = cfg.get("wording", {}).get("briefName", "Customer feedback brief")
PRODUCT = cfg.get("product", {})
F = "font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Arial,Helvetica,sans-serif;"  # no quotes: styles sit in single quoted attributes
e = lambda s: html.escape(str(s if s is not None else ""))
themes_by_id = {t["id"]: t for t in S["themes"]}
PALETTE = [BRAND, ACCENT, "#c2410c", "#7c3aed", "#15803d", "#0891b2", "#be185d", "#4d7c0f"]
THEME_COLOUR = {
    th["id"]: PALETTE[n % len(PALETTE)] for n, th in enumerate(x["themes"])
}  # the same colour and number on every chart
kept_themes = {t["id"]: t for t in json.load(open("themes.json"))["themes"] if t.get("decision") == "keep"}
CITED = []  # item ids in order of first citation, numbered [1], [2] ... across the brief


def claims():
    """Every sentence the agent wrote with citations, with the text of the items it cites, for the verifier."""
    out = []
    fields = [("headline", x.get("headline"))]
    fields += [(f"theme {t['id']}", t.get("summary")) for t in x.get("themes") or []]
    fields += [(f"theme {t['id']}", t.get("who")) for t in x.get("themes") or [] if t.get("who")]
    fields += [(f"watch {w['id']}", w.get("why")) for w in x.get("watch") or []]
    for a in x.get("actions") or []:
        fields += [
            (f"action {a['theme']}", a.get("detail")),
            (f"ticket {a['theme']}", (a.get("ticket") or {}).get("body")),
        ]
    for where, text in fields:
        for sentence in checks.sentences(text):
            ids = checks.citations(sentence)
            if ids:
                plain = checks.CITE.sub("", sentence).strip()
                out.append(
                    {
                        "id": hashlib.sha1(f"{where}|{plain}".encode()).hexdigest()[:10],
                        "where": where,
                        "claim": plain,
                        "cited": [
                            {
                                "id": i,
                                "text": (
                                    (items.get(i, {}).get("title") or "") + " " + items.get(i, {}).get("text", "")
                                ).strip(),
                            }
                            for i in ids
                        ],
                    }
                )
    return out


CLAIMS = claims()
VERDICTS = json.load(open("verdicts.json")) if os.path.exists("verdicts.json") else {}
verified = lambda where: bool(VERDICTS) and all(
    VERDICTS.get(c["id"], {}).get("supported") for c in CLAIMS if c["where"] == where
)
SRC_COLOURS = ["#334155", "#0f766e", "#9333ea", "#b45309", "#be123c"]
SRC_MARKERS = ["o", "^", "s", "D", "P"]
SRC_SYMBOLS = ["&#9679;", "&#9650;", "&#9632;", "&#9670;", "&#10010;"]  # the same shapes, for the html
SRC_STYLE = {
    c["id"]: (SRC_COLOURS[n % 5], SRC_MARKERS[n % 5], SRC_SYMBOLS[n % 5])
    for n, c in enumerate(S.get("connections", []))
}


# ---------------------------------------------------------------- pieces
def stars(r, scale):
    if r is None or not scale:
        return ""
    n = round(r / scale * 5)
    return f"<span style='color:{ACCENT}'>{'&#9733;' * n}</span><span style='color:{LINE}'>{'&#9733;' * (5 - n)}</span>"


def pill(text, colour, solid=False):
    style = f"background:{colour};color:#fff;" if solid else f"color:{colour};border:1px solid {colour};"
    return (
        f"<span style='display:inline-block;{F}font-size:11px;font-weight:600;{style}border-radius:999px;"
        f"padding:2px 9px;margin:0 6px 4px 0;text-transform:uppercase;letter-spacing:.4px'>{e(text)}</span>"
    )


def link_button(href, label):
    """A plain link styled as a button: works in every email client, unlike scripts."""
    blank = " target='_blank' rel='noopener'" if href.startswith("https://") else ""
    return (
        f"<a href='{e(href)}'{blank} style='display:inline-block;{F}font-size:13px;font-weight:600;color:{BRAND};background:#ffffff;"
        f"border:1px solid {BRAND};border-radius:8px;padding:7px 12px;margin:6px 6px 0 0;text-decoration:none'>{e(label)}</a>"
    )


def create_link(title, body):
    """A link that opens a new ticket in the profile's tracker with the title and description filled in.
    Nothing is filed: the reader reviews it and presses Create."""
    tk, q = cfg.get("tickets") or [], urllib.parse.quote
    body = body[:1500]
    if not tk:
        return None
    kind = tk[0].lower()
    if kind == "github":
        return f"https://github.com/{tk[1]}/issues/new?title={q(title)}&body={q(body)}", "Create GitHub issue"
    if kind == "linear":
        return f"https://linear.new?team={q(tk[1])}&title={q(title)}&description={q(body)}", "Create Linear issue"
    return (
        f"{tk[1].rstrip('/')}/secure/CreateIssueDetails!init.jspa?pid={q(tk[2])}&issuetype={q(tk[3] if len(tk) > 3 else '10001')}"
        f"&summary={q(title)}&description={q(body)}"
    ), "Create Jira issue"


def copy_button(text, preview, label="Copy"):
    if not preview:
        return ""
    return (
        f"<button onclick='copyText(this)' data-t='{e(text)}' "
        f"style='{F}font-size:13px;font-weight:600;color:#fff;background:{BRAND};border:0;border-radius:8px;padding:8px 12px;"
        f"margin:6px 6px 0 0;cursor:pointer'>{e(label)}</button>"
    )


def source_label(sid):
    c = conns.get(sid, {})
    label = e(c.get("label") or sid)
    return f"<a href='{e(c['link'])}' style='color:{BRAND}'>{label}</a>" if c.get("link") else label


def box_style(accent=None):
    edge = f"border-left:4px solid {accent};" if accent else ""
    return (
        f"background:#ffffff;border:1px solid {LINE};{edge}border-radius:12px;"
        f"padding:16px 18px;box-shadow:0 1px 2px rgba(16,24,40,.05)"
    )


def box(inner, accent=None):
    return {"inner": inner, "accent": accent}  # drawn by full() or grid()


def _div(b):
    return f"<div style='{box_style(b['accent'])}'>{b['inner']}</div>"


def full(b):
    return f"<tr><td style='padding:8px 24px'>{_div(b)}</td></tr>"


def card(inner, accent=None):
    return full(box(inner, accent))


def grid(boxes):
    """Two boxes side by side (they stack on a phone); an odd last box takes the full width."""
    rows = []
    for k in range(0, len(boxes) - 1, 2):  # the cells are the cards, so both are always the same height
        a, b = boxes[k], boxes[k + 1]
        rows.append(
            f"<tr><td style='padding:8px 24px'><table role='presentation' width='100%' cellpadding='0' cellspacing='0'><tr>"
            f"<td class='col' width='49%' valign='top' style='{box_style(a['accent'])}'>{a['inner']}</td>"
            f"<td class='gap' width='2%' style='font-size:0;line-height:0'>&nbsp;</td>"
            f"<td class='col' width='49%' valign='top' style='{box_style(b['accent'])}'>{b['inner']}</td></tr></table></td></tr>"
        )
    if len(boxes) % 2:
        rows.append(full(boxes[-1]))
    return "".join(rows)


def split(left, right):
    """Two cards stacked on the left, one card on the right that stretches to the full height (stacks on a phone)."""
    stack = "".join(
        f"<div style='{box_style(b['accent'])};margin-top:{16 if n else 0}px'>{b['inner']}</div>"
        for n, b in enumerate(left)
    )
    return (
        f"<tr><td style='padding:8px 24px'><table role='presentation' width='100%' cellpadding='0' cellspacing='0'><tr>"
        f"<td class='col' width='49%' valign='top' style='padding:0'>{stack}</td>"
        f"<td class='gap' width='2%' style='font-size:0;line-height:0'>&nbsp;</td>"
        f"<td class='col' width='49%' valign='top' style='{box_style(right['accent'])}'>{right['inner']}</td></tr></table></td></tr>"
    )


def section(title, sub=""):
    sub = f"<div style='{F}font-size:13px;color:{MUTED};margin-top:4px'>{sub}</div>" if sub else ""
    return (
        f"<tr><td style='padding:30px 24px 6px'><div style='{F}font-size:22px;font-weight:800;color:{BRAND};letter-spacing:-.2px'>{e(title)}</div>"
        f"<div style='width:40px;height:3px;background:{ACCENT};border-radius:2px;margin-top:6px'></div>{sub}</td></tr>"
    )


def stat(label, value, sub=""):
    return (
        f"<td class='stat' width='25%' style='padding:14px 8px;text-align:center'>"
        f"<div style='{F}font-size:24px;font-weight:700;color:{INK}'>{e(value)}</div>"
        f"<div style='{F}font-size:11px;color:{MUTED};text-transform:uppercase;letter-spacing:.5px;margin-top:2px'>{e(label)}</div>"
        f"<div style='{F}font-size:11px;color:{MUTED};margin-top:2px'>{sub}</div></td>"
    )


def delta(v, unit="", better="up"):
    if v is None:
        return "first edition"
    if v == 0:
        return "no change"
    good = (v > 0) == (better == "up")
    return (
        f"<span style='color:{'#15803d' if good else '#c2410c'}'>{'+' if v > 0 else ''}{v:g}{unit} vs last run</span>"
    )


def source_tag(sid):
    """A small coloured tag naming the connection, with the same shape it has on the map."""
    colour, _, symbol = SRC_STYLE.get(sid, ("#334155", "o", "&#9679;"))
    return (
        f"<span style='display:inline-block;{F}font-size:11px;font-weight:600;color:{colour};background:#ffffff;"
        f"border:1px solid {colour};border-radius:999px;padding:1px 8px;margin-right:6px'>{symbol} {source_label(sid)}</span>"
    )


def cite(text):
    """Escape the agent's text and turn its citations into numbered links to the evidence list."""

    def link(m):
        refs = []
        for i in [i.strip() for i in m.group(1).split(",")]:
            if i not in CITED:
                CITED.append(i)
            refs.append(f"<a href='#ev-{e(i)}' style='color:{BRAND};text-decoration:none'>{CITED.index(i) + 1}</a>")
        return f"<sup style='{F}font-size:10px'>[{','.join(refs)}]</sup>"

    return checks.CITE.sub(link, e(text))


def label(kind, where=None, n=0):
    """Small labels that show which parts code checked and which are the agent's reading."""
    if kind == "checked":
        return f"<span style='{F}font-size:11px;color:#15803d;font-weight:600'>&#10003; Word for word, checked against the source</span>"
    tick = " &middot; <span style='color:#15803d'>&#10003; claims verified</span>" if where and verified(where) else ""
    return f"<div style='{F}font-size:11px;color:{MUTED};margin-top:4px;font-style:italic'>Agent's interpretation &middot; cites {n} item{'s' if n != 1 else ''}{tick}</div>"


def quote(q):
    it = items.get(q["item"], {})
    meta = source_tag(it.get("source")) + " &middot; ".join(
        filter(None, [e(it.get("date")), stars(it.get("rating"), it.get("ratingScale"))])
    )
    link = f" &middot; <a href='{e(it['url'])}' style='color:{BRAND}'>open</a>" if it.get("url") else ""
    return (
        f"<div style='background:{BG};border-radius:10px;padding:10px 14px;margin:10px 0 0'>"
        f"<div style='{F}font-size:14px;line-height:1.55;color:{INK}'>&ldquo;{e(q['text'])}&rdquo;</div>"
        f"<div style='{F}font-size:12px;color:{MUTED};margin-top:4px'>{meta}{link}</div></div>"
    )


def ticket(a, preview):
    tk = a.get("ticket") or {}
    if not tk:
        return ""
    return (
        f"<div style='background:{TINT};border-radius:10px;padding:10px 12px;margin-top:10px'>"
        f"<div style='{F}font-size:11px;color:{MUTED};text-transform:uppercase;letter-spacing:.5px'>Draft ticket, not filed</div>"
        f"<div style='{F}font-size:14px;font-weight:700;color:{INK};margin-top:3px'>{e(tk.get('title'))}</div>"
        f"<div style='{F}font-size:13px;line-height:1.55;color:{INK};margin-top:4px;white-space:pre-line'>{cite(tk.get('body'))}</div>"
        f"{ticket_buttons(tk, preview)}</div>"
    )


def ticket_buttons(tk, preview):
    title, body = tk.get("title", ""), ticket_text(tk.get("body", ""))
    out = copy_button(title + chr(10) + chr(10) + body, preview, "Copy ticket")
    made = create_link(title, body)
    if made:
        out += link_button(*made)
    return out + link_button(email_link(title, body[:1500], preview), "Email this")


def email_link(subject, body, preview):
    """In an email, mailto opens a reply in the reader's own mail client. A browser often has no mail app set up for
    mailto, so the preview opens the compose page of the sending account's webmail instead (from SMTP_HOST, not a secret).
    """
    q, host = urllib.parse.quote, (config.env("SMTP_HOST") or "").lower()
    if preview and "gmail" in host:
        return f"https://mail.google.com/mail/?view=cm&fs=1&su={q(subject)}&body={q(body)}"
    if preview and ("office365" in host or "outlook" in host):
        return f"https://outlook.office.com/mail/deeplink/compose?subject={q(subject)}&body={q(body)}"
    return f"mailto:?subject={q(subject)}&body={q(body)}"


def ticket_text(body):
    """A copied ticket keeps its evidence: each citation becomes the item's source, date and link."""

    def ref(m):
        out = []
        for i in [i.strip() for i in m.group(1).split(",")]:
            it = items.get(i, {})
            out.append(
                f"{it.get('sourceLabel', i)} {it.get('date', '')}" + (f" {it['url']}" if it.get("url") else f" ({i})")
            )
        return "(" + "; ".join(out) + ")"

    return checks.CITE.sub(ref, body)


# ---------------------------------------------------------------- the brief
def mix_chart():
    """How ratings are spread across the window, 5 stars to 1: an average can hide a split between love and hate."""
    mix = S.get("ratingMix")
    if not mix or not sum(mix.values()):
        return ""
    total, colour = sum(mix.values()), {"5": "#15803d", "4": "#65a30d", "3": "#ca8a04", "2": "#ea580c", "1": "#b91c1c"}
    rows = "".join(
        f"<tr><td width='34' style='{F}font-size:12px;color:{INK};padding:3px 6px 3px 0'>{s}&#9733;</td>"
        f"<td style='padding:3px 0'><div style='width:{max(2, round(100 * n / total))}%;height:12px;border-radius:6px;background:{colour[s]}'></div></td>"
        f"<td width='44' align='right' style='{F}font-size:12px;color:{MUTED}'>{round(100 * n / total)}%</td></tr>"
        for s, n in mix.items()
    )
    return (
        f"<div style='{F}font-size:13px;font-weight:600;color:{INK};margin:0 0 8px'>Rating mix "
        f"<span style='font-weight:400;color:{MUTED}'>({total} rated items)</span></div>"
        f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0'>{rows}</table>"
    )


def volume_chart():
    days = S["daily"]
    top = max([d["count"] for d in days] + [1])
    cols = []
    for d in days:
        h = max(2, round(110 * d["count"] / top))
        r = f"{d['avgRating']}" if d["avgRating"] is not None else "&nbsp;"
        cols.append(
            f"<td valign='bottom' align='center' style='padding:0 3px'>"
            f"<div style='{F}font-size:11px;color:{MUTED}'>{d['count']}</div>"
            f"<div style='height:{h}px;background:{BRAND};background-image:linear-gradient(180deg,{BRAND2},{BRAND});border-radius:6px 6px 0 0'></div>"
            f"<div style='{F}font-size:11px;color:{MUTED};margin-top:4px'>{d['date'][8:].lstrip('0')}</div>"
            f"<div style='{F}font-size:11px;color:{ACCENT}'>{r}</div></td>"
        )
    return (
        f"<div style='{F}font-size:13px;font-weight:600;color:{INK};margin-bottom:8px'>Feedback per day "
        f"<span style='font-weight:400;color:{MUTED}'>(<span style='color:{ACCENT}'>average rating</span> below)</span></div>"
        f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0' style='table-layout:fixed'><tr>{''.join(cols)}</tr></table>"
    )


def themes_chart():
    ts = S["themes"]
    top = max([t["count"] for t in ts] + [1])
    rows = "".join(
        f"<tr><td width='40%' style='{F}font-size:12px;color:{INK};padding:4px 8px 4px 0'>{e(t['title'])}</td>"
        f"<td style='padding:4px 0'><div style='width:{max(3, round(100 * t['count'] / top))}%;height:14px;border-radius:7px;"
        f"background:{KIND.get(t['kind'], BRAND)}'></div></td>"
        f"<td width='36' align='right' style='{F}font-size:12px;color:{MUTED}'>{t['count']}</td></tr>"
        for t in ts
    )
    legend = " ".join(f"<span style='color:{c}'>&#9632; {k}</span>" for k, c in KIND.items())
    return (
        f"<div style='{F}font-size:13px;font-weight:600;color:{INK};margin:0 0 8px'>Items per theme</div>"
        f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0'>{rows}</table>"
        f"<div style='{F}font-size:12px;color:{MUTED};margin-top:6px'>{legend}</div>"
        f"<div style='{F}font-size:12px;line-height:1.5;color:{MUTED};margin-top:4px'>The agent gives each theme a kind after reading "
        f"its feedback: <b>problem</b>, something broken or in the way; <b>request</b>, something customers want added or changed; "
        f"<b>praise</b>, something working well; <b>question</b>, customers unsure how something works.</div>"
    )


def ratings_chart():
    """Average rating per theme against the overall average: which themes drag the rating down."""
    overall = S["totals"].get("avgRating")
    ts = [t for t in S["themes"] if t.get("avgRating") is not None]
    if overall is None or not ts:
        return ""
    rows = "".join(
        f"<tr><td width='40%' style='{F}font-size:12px;color:{INK};padding:4px 8px 4px 0'>{e(t['title'])}</td>"
        f"<td style='padding:4px 0'><div style='width:{max(3, round(100 * t['avgRating'] / 5))}%;height:14px;border-radius:7px;"
        f"background:{'#b91c1c' if t['avgRating'] < overall else '#15803d'}'></div></td>"
        f"<td width='36' align='right' style='{F}font-size:12px;color:{MUTED}'>{t['avgRating']}</td></tr>"
        for t in sorted(ts, key=lambda t: t["avgRating"])
    )
    return (
        f"<div style='{F}font-size:13px;font-weight:600;color:{INK};margin:0 0 8px'>Rating by theme "
        f"<span style='font-weight:400;color:{MUTED}'>(out of 5; overall {overall}. Red is below the overall average)</span></div>"
        f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0'>{rows}</table>"
    )


PRIVATE_NOTE = (
    f"<div style='{F}font-size:12px;color:{MUTED};margin-top:10px;font-style:italic'>No quotes: this feedback is private, "
    "so it is described and cited but not quoted (setup can allow quoting for a brief that stays inside the company).</div>"
)


def day(d):
    d = datetime.date.fromisoformat(d)
    return f"{d:%a} {d.day} {d:%b}"


def when_text(s):
    """Since when and the peak day, counted by code from the items' dates (plain text)."""
    if not s.get("firstSeen"):
        return ""
    start = (S.get("coverage") or {}).get("from") or S["window"]["since"]
    first = "Throughout the period" if s["firstSeen"] <= start else f"First seen {day(s['firstSeen'])}"
    return first + (f", peaked {day(s['peakDay'])} ({s['peakCount']})" if s.get("peakCount", 0) > 1 else "")


def body(preview, img):
    t, ch = S["totals"], S.get("change") or {}
    icon = img("logo.png") or PRODUCT.get("iconUrl")  # optional: the profile's logo, else nothing
    icon_td = (
        (
            f"<td width='92' valign='middle'><img src='{e(icon)}' width='76' height='76' alt='' "
            f"style='display:block;border-radius:14px'/></td>"
        )
        if icon
        else ""
    )
    rows = [
        f"<tr><td bgcolor='{BRAND}' background='{img('header.png')}' style='background:{BRAND};background-image:"
        + (f"url({img('header.png')})" if img("header.png") else f"linear-gradient(135deg,{BRAND} 0%,{BRAND2} 100%)")
        + f";background-size:cover;background-position:center;padding:34px 24px'>"
        f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0'><tr>{icon_td}<td valign='middle'>"
        f"<div style='{F}font-size:12px;color:#ffffff;opacity:.9;text-transform:uppercase;letter-spacing:1px'>{e(PRODUCT.get('name'))}</div>"
        f"<div style='{F}font-size:26px;font-weight:700;color:#ffffff;margin-top:2px'>{e(NAME)}</div>"
        f"<div style='{F}font-size:13px;color:#ffffff;opacity:.9;margin-top:4px'>{e(x['meta']['dateLabel'])} &middot; feedback from {e(x['meta']['windowLabel'])}</div>"
        f"</td></tr></table></td></tr>",
        f"<tr><td style='padding:22px 24px 4px'><div style='{F}font-size:18px;line-height:1.5;color:{INK}'>{cite(x['headline'])}</div></td></tr>",
        f"<tr><td style='padding:14px 24px 0'><table role='presentation' width='100%' cellpadding='0' cellspacing='0' "
        f"style='background:#ffffff;border:1px solid {LINE};border-radius:12px'><tr>"
        + stat("Items", t["items"], delta(ch.get("items"), better="none") if ch else "first edition")
        + stat(
            "Avg rating",
            t["avgRating"] if t["avgRating"] is not None else "n/a",
            delta(ch.get("avgRating")) if ch else "",
        )
        + stat(
            "1 or 2 stars",
            f"{t['lowShare']}%" if t["lowShare"] is not None else "n/a",
            delta(ch.get("lowShare"), " pts", better="down") if ch else "",
        )
        + stat(
            "Connections",
            f"{S['sources']['ok']} of {sum(S['sources'].values())}",
            f"{S['sources']['blocked']} blocked" if S["sources"]["blocked"] else "all read",
        )
        + "</tr></table></td></tr>",
    ]
    if not preview:  # an email can't run scripts: link to the interactive versions, when there are real ones
        ss, base = x.get("session") or {}, config.env("BRIEF_PREVIEW_BASE")
        links = ""
        if base:  # a scheduled run's hosted preview (Cloud Storage, behind sign-in)
            links += link_button(
                f"{base.rstrip('/')}/{info['folder'].split('runs/', 1)[-1]}/out/preview.html",
                "Open the interactive version",
            )
        if ss.get("url"):
            links += link_button(ss["url"], "Continue in your agent")
        if links:
            rows.append(f"<tr><td style='padding:14px 24px 0'>{links}</td></tr>")
    chips = []
    for c in S.get("connections", []):
        ok = c["status"] == "ok"
        tail = f"{c.get('collected', c.get('kept', 0))} items" if ok else c["status"]
        lock = " &middot; private" if c.get("private") else ""
        chips.append(
            f"<span style='display:inline-block;margin:8px 4px 0 0'>{source_tag(c['id'])}"
            f"<span style='{F}font-size:12px;color:{INK if ok else '#c2410c'}'>{e(c['type'])} &middot; {e(tail)}{lock}</span></span>"
        )
    rows.append(
        f"<tr><td style='padding:6px 24px 0'><span style='{F}font-size:12px;color:{MUTED}'>Read from:</span> {''.join(chips)}</td></tr>"
    )
    if S.get("capped"):
        cv = S["coverage"]
        rows.append(
            f"<tr><td style='padding:8px 24px 0'><div style='{F}font-size:12px;color:{MUTED}'>The numbers above count all {cv['collected']} items in the window. "
            f"Themes come from the newest {cv['analysed']}, from {e(cv['from'])} to {e(cv['until'])}.</div></td></tr>"
        )

    if img("map.png"):
        rows.append(
            section(
                "Feedback map", "Each dot is one piece of feedback, placed near similar feedback and coloured by theme"
            )
        )
        rows.append(
            card(
                f"<img src='{img('map.png')}' width='544' alt='Every item placed by similarity, coloured by theme' style='width:100%;height:auto;display:block'/>"
                f"<div style='{F}font-size:12px;line-height:1.5;color:{MUTED};margin-top:6px'><b>How the map is made:</b> code turns each piece of "
                f"feedback into numbers from the words it uses (TF-IDF), compresses them so words that tend to appear together count as "
                f"related (LSA), groups similar items with K-means so the agent reads them together, and flattens everything onto two "
                f"dimensions (PCA), so feedback that says similar things sits close together. The colours are the agent's themes, "
                f"from reading every item; grey dots fit no theme. The axes have no units: only closeness matters.</div>"
            )
        )
    rows.append(section("At a glance"))
    left = [box(volume_chart())] + ([box(mix_chart())] if mix_chart() else [])
    rows.append(split(left, box(themes_chart())))
    if ratings_chart():
        rows.append(card(ratings_chart()))

    def when(s):
        w = when_text(s)
        return f"<div style='{F}font-size:12px;color:{INK};margin-top:6px'><b>When:</b> {e(w)}</div>" if w else ""

    def theme_card(th):
        s = themes_by_id[th["id"]]
        trend = pill(*TREND[s["trend"]]) if s["trend"] in TREND else ""
        who = (
            (f"<div style='{F}font-size:12px;color:{INK};margin-top:3px'><b>Who:</b> {cite(th['who'])}</div>")
            if th.get("who")
            else ""
        )
        rating = f" &middot; average rating {s['avgRating']}" if s["avgRating"] is not None else ""
        size = f"{s['count']} items &middot; {s['share']}% of all feedback &middot; {s['firstHalf']} then {s['secondHalf']} across the period"
        prev = f" &middot; {s['previousShare']}% last run" if s.get("previousShare") is not None else ""
        srcs = "".join(
            f"{source_tag(k)}<span style='margin-right:8px'>{v}</span>" for k, v in (s.get("sources") or {}).items()
        )
        return box(
            f"<a name='{e(th['id'])}' id='{e(th['id'])}'></a><div>{pill(s['kind'], KIND.get(s['kind'], BRAND), solid=True)}{trend}</div>"
            f"<div style='{F}font-size:17px;font-weight:700;color:{INK};margin-top:4px'>{e(th['title'])}</div>"
            f"<div style='{F}font-size:12px;color:{MUTED};margin-top:3px'>{size}{prev}{rating}</div>"
            f"<div style='{F}font-size:14px;line-height:1.55;color:{INK};margin-top:8px'>{cite(th['summary'])}</div>"
            + when(s)
            + who
            + label(
                "interpretation",
                f"theme {th['id']}",
                len(set(checks.citations(th["summary"])) | set(checks.citations(th.get("who")))),
            )
            + ("".join(quote(q) for q in th["quotes"]) or PRIVATE_NOTE)
            + f"<div style='{F}font-size:12px;color:{MUTED};margin-top:10px'>From {srcs}</div>",
            accent=KIND.get(s["kind"], BRAND),
        )

    issues = [th for th in x["themes"] if themes_by_id[th["id"]]["kind"] != "praise"]
    working = [th for th in x["themes"] if themes_by_id[th["id"]]["kind"] == "praise"]
    if issues:
        rows.append(section("What customers are saying", "Every quote is word for word, with its source"))
        rows += [full(theme_card(th)) for th in issues]
    if img("matrix.png"):
        rows.append(section("Where to focus", "Each theme by how many customers it reaches and how much it hurts them"))
        rows.append(
            card(
                f"<img src='{img('matrix.png')}' width='544' alt='Themes by reach and impact' style='width:100%;height:auto;display:block'/>"
                f"<div style='{F}font-size:12px;color:{MUTED};margin-top:6px'>Reach is counted by code; impact is the agent's judgement "
                f"(0 to 3, with ease of acting nudging it up). Top right is where to act first.</div>"
            )
        )
    if working:
        rows.append(section("What's working", "What customers praise: worth passing on to the teams behind it"))
        rows.append(grid([theme_card(th) for th in working]))

    if x.get("watch"):
        watch_by_id = {w["id"]: w for w in S.get("watch", [])}
        rows.append(section("Watchlist", "Rare but serious: only a few items, but worth knowing about"))
        boxes = []
        for w in x["watch"]:
            s = watch_by_id.get(w["id"], {})
            srcs = "".join(
                f"{source_tag(k)}<span style='margin-right:8px'>{v}</span>" for k, v in (s.get("sources") or {}).items()
            )
            boxes.append(
                box(
                    f"<div style='{F}font-size:16px;font-weight:700;color:{INK}'>{e(w['title'])}</div>"
                    f"<div style='{F}font-size:12px;color:{MUTED};margin-top:3px'>{s.get('count', 0)} item{'s' if s.get('count') != 1 else ''} &middot; From {srcs}</div>"
                    f"<div style='{F}font-size:14px;line-height:1.55;color:{INK};margin-top:8px'>{cite(w['why'])}</div>"
                    + label("interpretation", f"watch {w['id']}", len(set(checks.citations(w["why"]))))
                    + "".join(quote(q) for q in w.get("quotes") or []),
                    accent="#b91c1c",
                )
            )
        rows.append(grid(boxes))

    if x.get("actions"):
        rows.append(
            section(
                "Things to act on", "Ranked by impact, reach and growth, each with a draft ticket for the owning team"
            )
        )
        for n, a in enumerate(x["actions"], 1):
            rows.append(
                card(
                    f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0'><tr>"
                    f"<td width='40' valign='top'><div style='{F}width:30px;height:30px;border-radius:15px;background:{ACCENT};color:#fff;"
                    f"font-weight:700;font-size:15px;line-height:30px;text-align:center'>{n}</div></td>"
                    f"<td valign='top'><div style='{F}font-size:16px;font-weight:700;color:{INK}'>{e(a['title'])}</div>"
                    f"<div style='{F}font-size:14px;line-height:1.55;color:{INK};margin-top:4px'>{cite(a['detail'])}</div>"
                    + label("interpretation", f"action {a['theme']}", len(set(checks.citations(a["detail"]))))
                    + f"<div style='{F}font-size:12px;color:{MUTED};margin-top:6px'>Owner: {e(a['owner'])}</div>"
                    + ticket(a, preview)
                    + f"</td></tr></table>"
                )
            )

    qs = "".join(f"<li style='margin:2px 0'>&ldquo;{e(q)}&rdquo;</li>" for q in x.get("questions") or [])
    ss = x.get("session") or {}
    back = (
        link_button(ss["url"], "Continue in your agent")
        if ss.get("url")
        else (
            f"<div style='{F}font-size:13px;color:{INK};margin-top:8px'>To continue this conversation, run in the project folder: "
            f"<code style='background:{BG};padding:2px 6px;border-radius:4px'>{e(ss['resume'])}</code></div>"
            if ss.get("resume")
            else ""
        )
    )
    how = (
        "Ask the agent directly, in the conversation where this brief was made. It answers from this brief's evidence, "
        "with every claim cited. For example:"
        if preview
        else (
            "Follow-up questions can't be answered by email yet. Continue in your agent, where this brief was made, for example:"
            if back
            else "Follow-up questions can't be answered by email yet. Open the project in your agent harness and ask there, for example:"
        )
    )
    rows.append(section("Ask your agent"))
    rows.append(
        card(
            f"<div style='{F}font-size:14px;line-height:1.6;color:{INK}'>{how}"
            f"<ul style='margin:6px 0 0 18px;padding:0'>{qs}</ul>{back}"
            f"<div style='{F}font-size:12px;color:{MUTED};margin-top:8px'>You can also ask it to change the brief "
            f"(&ldquo;make it shorter&rdquo;) or add a connection.</div></div>"
        )
    )

    srcs = []
    for c in S.get("connections", []):
        tail = f"{c.get('kept', 0)} items" if c["status"] == "ok" else f"{c['status']}: {c.get('reason', '')}"
        if c.get("note"):
            tail += f" ({c['note']})"
        srcs.append(f"{source_label(c['id'])}{' (private)' if c.get('private') else ''}: {e(tail)}")
    rows.append(
        f"<tr><td style='padding:22px 24px 26px'><div style='{F}font-size:12px;line-height:1.65;color:{MUTED}'>"
        f"<b>Sources.</b> {'; '.join(srcs)}.<br/>{e(x['footer'])}<br/>"
        f"Written by an AI agent. Every quote was checked word for word against the collected feedback, every number was "
        f"computed by code, and private feedback is described but never quoted. Names, emails and reference numbers are "
        f"removed before anything is written.</div></td></tr>"
    )
    rows.append(evidence(preview))
    return "".join(rows)


def evidence_row(i, n=None, short=False):
    it = items.get(i, {})
    num = f"<b>[{n}]</b> " if n else ""
    link = f" &middot; <a href='{e(it['url'])}' style='color:{BRAND}'>open</a>" if it.get("url") else ""
    text = (f"{it['title']}: " if it.get("title") else "") + it.get("text", "")
    if short and len(text) > 120:  # one line per item in the email; the full text is in the preview and the run
        text = text[:117].rsplit(" ", 1)[0] + "…"
    return (
        f"<tr id='ev-{e(i)}'><td style='{F}font-size:12px;line-height:1.5;color:{INK};padding:6px 0;border-top:1px solid {LINE}'>"
        f"{num}{source_tag(it.get('source'))}<span style='color:{MUTED}'>{e(i)} &middot; {e(it.get('date'))} "
        f"{stars(it.get('rating'), it.get('ratingScale'))}{link}</span><br/>{e(text)}</td></tr>"
    )


def evidence(preview):
    """The items the brief cites, numbered. Everything collected stays with the run, for the agent to answer questions from."""
    cited = "".join(evidence_row(i, n, short=not preview) for n, i in enumerate(CITED, 1))
    table = f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0'>{cited}</table>"
    if preview:  # collapsed until opened; clicking a citation opens it (COPY_JS)
        table = (
            f"<details id='evidence-list'><summary style='{F}font-size:13px;font-weight:600;color:{BRAND};cursor:pointer'>"
            f"Show the {len(CITED)} cited items</summary>{table}</details>"
        )
    more = (
        f"<div style='{F}font-size:12px;color:{MUTED};margin-top:8px'>All {len(items)} items collected are kept with this run; "
        f"ask your agent about any of them.</div>"
    )
    return section("Evidence", "Every item the brief cites") + card(table + more)


COPY_JS = """<script>
function copyText(b) {
  var t = b.getAttribute('data-t'), label = b.textContent;
  function done() { b.textContent = 'Copied'; setTimeout(function () { b.textContent = label; }, 1500); }
  function fallback() {  // file:// pages and embedded previews often block the clipboard API
    var a = document.createElement('textarea'); a.value = t; a.style.position = 'fixed'; a.style.opacity = '0';
    document.body.appendChild(a); a.focus(); a.select();
    try { document.execCommand('copy') ? done() : (b.textContent = 'Press Ctrl+C'); } catch (e) { b.textContent = 'Press Ctrl+C'; }
    document.body.removeChild(a);
  }
  if (navigator.clipboard && window.isSecureContext) { navigator.clipboard.writeText(t).then(done, fallback); } else { fallback(); }
}
document.addEventListener('click', function (ev) {  // a citation opens the collapsed evidence list before jumping to it
  var a = ev.target.closest && ev.target.closest('a[href^="#ev-"]'), d = document.getElementById('evidence-list');
  if (a && d) { d.open = true; }
});
</script>"""


def mix(a, b, w):
    """Blend two hex colours: w=0 gives a, w=1 gives b."""
    a, b = [[int(c.lstrip("#")[k : k + 2], 16) for k in (0, 2, 4)] for c in (a, b)]
    return "#" + "".join(f"{round(x + (y - x) * w):02x}" for x, y in zip(a, b))


def page(img, preview=False):
    DEEP = mix(BRAND, "#000000", 0.35)  # the primary colour, a bit darker
    css = (
        "@media (max-width:620px){.wrap{width:100%!important}.stat{display:block!important;width:100%!important;"
        "border-bottom:1px solid "
        + LINE
        + "}.col{display:block!important;width:auto!important;margin-bottom:12px}.gap{display:none!important}}"
    )
    strip = ""
    if preview:
        to = f"<br/><b>To:</b> {e(cfg['recipient'])}" if cfg.get("delivery") in ("email", "both") else ""
        strip = (
            f"<div style='{F}width:92%;max-width:1100px;margin:0 auto 12px;font-size:12px;color:#ffffff'>"
            f"<b>Subject:</b> {e(NAME)}{to}</div>"
        )
    return (
        f"<!doctype html><html><head><meta charset='utf-8'/><meta name='viewport' content='width=device-width,initial-scale=1'/>"
        f"<title>{e(x['subject'])}</title><style>{css}</style>{COPY_JS if preview else ''}</head>"
        f"<body style='margin:0;padding:24px 0;min-height:100vh;background:{DEEP};"
        f"background-image:linear-gradient(135deg,{DEEP} 0%,{mix(DEEP, BRAND, .5)} 70%,{mix(BRAND, ACCENT, .12)} 100%);background-attachment:fixed'>{strip}"
        f"<div style='display:none;max-height:0;overflow:hidden'>{e(x['preheader'])}</div>"
        + (
            f"<table role='presentation' class='wrap' width='100%' align='center' cellpadding='0' cellspacing='0' "
            f"style='width:92%;max-width:1100px;margin:0 auto;background:{BG};border-radius:16px;overflow:hidden;"
            if preview
            else f"<table role='presentation' class='wrap' width='640' align='center' cellpadding='0' cellspacing='0' "
            f"style='width:640px;max-width:640px;margin:0 auto;background:{BG};border-radius:16px;overflow:hidden;"
        )
        + f"box-shadow:0 24px 60px rgba(0,0,0,.35),0 4px 14px rgba(0,0,0,.18)'>{body(preview, img)}</table></body></html>"
    )


def text():
    out = [NAME, f"{x['meta']['dateLabel']}, feedback from {x['meta']['windowLabel']}", "", x["headline"], ""]
    for n, a in enumerate(x.get("actions") or [], 1):
        out += [f"{n}. {a['title']}", f"   {a['detail']}", f"   Owner: {a['owner']}"]
    for th in x["themes"]:
        s = themes_by_id[th["id"]]
        out += ["", f"* {th['title']} ({s['count']} items, {s['share']}%)", f"  {th['summary']}"]
        out += [f"  \"{q['text']}\" ({items.get(q['item'], {}).get('sourceLabel', '')})" for q in th["quotes"]]
    for w in x.get("watch") or []:
        out += ["", f"Watchlist: {w['title']}", f"  {w['why']}"]
        out += [f"  \"{q['text']}\" ({items.get(q['item'], {}).get('sourceLabel', '')})" for q in w.get("quotes") or []]
    for a in x.get("actions") or []:
        tk = a.get("ticket") or {}
        out += ["", f"Draft ticket: {tk.get('title', '')}", tk.get("body", "")]
    if x.get("questions"):
        out += [
            "",
            "Follow-up questions can't be answered by email yet; open the project in your agent harness and ask there, for example:",
        ]
        out += [f"  - {q}" for q in x["questions"]]
    out += ["", x["footer"]]
    return "\n".join(out)


def markdown():
    """The same order as the email: summary, map, charts as numbers, themes, then actions with their tickets."""
    t, ch = S["totals"], S.get("change") or {}
    out = [
        f"# {NAME}",
        f"*{PRODUCT.get('name', '')} · {x['meta']['dateLabel']} · feedback from {x['meta']['windowLabel']}*",
        "",
        x["headline"],
        "",
    ]
    nums = [f"**{t['items']}** items"]
    if t["avgRating"] is not None:
        nums.append(
            f"average rating **{t['avgRating']}**"
            + (f" ({ch['avgRating']:+g} vs last run)" if ch.get("avgRating") else "")
        )
    if t["lowShare"] is not None:
        nums.append(f"**{t['lowShare']}%** at the lowest ratings")
    reads = ", ".join(f"[{c['label']}]({c['link']})" if c.get("link") else c["label"] for c in S.get("connections", []))
    out += [" · ".join(nums), f"Read from: {reads}", ""]
    if S.get("capped"):
        cv = S["coverage"]
        out += [
            f"*The numbers count all {cv['collected']} items in the window. Themes come from the newest {cv['analysed']}, from {cv['from']} to {cv['until']}.*",
            "",
        ]
    if os.path.exists("out/map.png"):
        out += ["![Feedback map](map.png)", ""]
    if os.path.exists("out/matrix.png"):
        out += ["![Where to focus: themes by reach and impact](matrix.png)", ""]
    groups = [
        ("What customers are saying", [th for th in x["themes"] if themes_by_id[th["id"]]["kind"] != "praise"]),
        ("What's working", [th for th in x["themes"] if themes_by_id[th["id"]]["kind"] == "praise"]),
    ]
    for heading, group in groups:
        if not group:
            continue
        out += [f"## {heading}", ""]
        for th in group:
            s = themes_by_id[th["id"]]
            trend = f" · {TREND[s['trend']][0]}" if s["trend"] in TREND else ""
            srcs = ", ".join(f"{conns.get(k, {}).get('label', k)} {v}" for k, v in (s.get("sources") or {}).items())
            out += [
                f"### {th['title']}",
                f"*{s['kind']} · {s['count']} items · {s['share']}% of feedback{trend} · sources: {srcs}*",
                "",
                th["summary"],
                "",
            ]
            out += [f"**When:** {when_text(s)}"] if when_text(s) else []
            out += [f"**Who:** {th['who']}"] if th.get("who") else []
            out += [""]
            for q in th["quotes"]:
                it = items.get(q["item"], {})
                src = f"[{it.get('sourceLabel', '')}]({it['url']})" if it.get("url") else it.get("sourceLabel", "")
                out += [f"> \u201c{q['text']}\u201d", f"> \u2014 {src}, {it.get('date', '')}", ""]
    if x.get("watch"):
        out += ["## Watchlist", "*Rare but serious: only a few items, but worth knowing about.*", ""]
        for w in x["watch"]:
            out += [f"### {w['title']}", "", w["why"], ""]
            for q in w.get("quotes") or []:
                it = items.get(q["item"], {})
                out += [f"> \u201c{q['text']}\u201d", f"> \u2014 {it.get('sourceLabel', '')}, {it.get('date', '')}", ""]
    if x.get("actions"):
        out += ["## Things to act on", ""]
        for n, a in enumerate(x["actions"], 1):
            tk = a.get("ticket") or {}
            out += [
                f"{n}. **{a['title']}** {a['detail']} *Owner: {a['owner']}*",
                f"   > **Draft ticket: {tk.get('title', '')}**  ",
                f"   > {tk.get('body', '')}",
                "",
            ]
    if CITED:
        out += ["## Evidence", ""]
        for n, i in enumerate(CITED, 1):
            it = items.get(i, {})
            src = f"[{it.get('sourceLabel', '')}]({it['url']})" if it.get("url") else it.get("sourceLabel", "")
            out.append(f"{n}. `{i}` · {src} · {it.get('date', '')}: {it.get('text', '')[:200]}")
        out.append("")
    if x.get("questions"):
        out += [
            "## Ask me",
            "",
            "Ask me directly here; I answer from this brief's evidence, with every claim cited. For example:",
            "",
        ]
        out += [f"- {q}" for q in x["questions"]] + [""]
    out += [
        "---",
        x["footer"],
        "",
        "*Summaries and actions are the agent's interpretation, with the items they cite; quotes and numbers are checked by code.*",
    ]
    return "\n".join(out)


# ---------------------------------------------------------------- write
def _plt():
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        return plt
    except ImportError:
        print(
            "matplotlib is missing, so the brief has no map or header art; install it with: python3 -m pip install -r requirements.txt"
        )
        return None


def draw_map():
    """Every item at its position from cluster.py: colour shows its theme, shape shows its connection."""
    plt = _plt()
    if not plt or not os.path.exists("clusters.json"):
        return False
    pos = json.load(open("clusters.json"))["positions"]
    tags = {}
    for p in ["tags/carried.json"] + sorted(glob.glob("tags/part_*.json")):
        if os.path.exists(p):
            tags.update(json.load(open(p)))
    shown = [th["id"] for th in x["themes"]]
    colour = THEME_COLOUR
    fig, ax = plt.subplots(figsize=(8, 5.6), dpi=160)
    fig.patch.set_facecolor("white")
    ax.set_facecolor(TINT)
    for iid, (px, py) in pos.items():
        tid = next((t for t in (tags.get(iid) or []) if t in colour), None)
        _, marker, _ = SRC_STYLE.get(items.get(iid, {}).get("source"), ("", "o", ""))
        ax.scatter(
            px,
            py,
            s=26 if tid else 12,
            marker=marker,
            color=colour.get(tid, "#c3cad3"),
            alpha=0.9 if tid else 0.5,
            edgecolors="white",
            linewidths=0.4,
            zorder=3 if tid else 2,
        )
    keys = []
    for n, tid in enumerate(
        shown, 1
    ):  # a small number at the centre of each theme's points; the names go in the key below
        pts = [pos[i] for i in pos if tid in (tags.get(i) or [])]
        if pts:
            cx, cy = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
            ax.annotate(
                str(n),
                (cx, cy),
                fontsize=8,
                fontweight="bold",
                color="white",
                ha="center",
                va="center",
                zorder=4,
                bbox=dict(boxstyle="circle,pad=0.3", fc=colour[tid], ec="white", lw=1),
            )
        keys.append(
            plt.Line2D(
                [],
                [],
                marker="o",
                color=colour[tid],
                linestyle="",
                markersize=7,
                label=f"{n}. {themes_by_id[tid]['title'][:60]}",
            )
        )
    handles = [
        plt.Line2D([], [], marker=SRC_STYLE[c["id"]][1], color="#55606e", linestyle="", markersize=6, label=c["label"])
        for c in S.get("connections", [])
        if c["id"] in SRC_STYLE
    ]
    ax.add_artist(
        ax.legend(
            handles=handles,
            loc="upper right",
            frameon=True,
            fontsize=7.5,
            framealpha=0.9,
            title="Shape = source",
            title_fontsize=7.5,
        )
    )
    ax.legend(
        handles=keys,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.02),
        ncol=2,
        frameon=False,
        fontsize=7.5,
        handletextpad=0.3,
        columnspacing=1.2,
    )
    ax.set_xticks([])
    ax.set_yticks([])
    for side in ax.spines.values():
        side.set_visible(False)
    fig.tight_layout()
    fig.savefig("out/map.png", facecolor="white", bbox_inches="tight")
    plt.close(fig)
    return True


def draw_matrix():
    """Priority matrix: each theme by reach (share of feedback, counted by code) and impact (the agent's score)."""
    plt = _plt()
    ts = [themes_by_id[th["id"]] for th in x["themes"] if themes_by_id[th["id"]].get("impact") is not None]
    if not plt or len(ts) < 2:
        return False
    fig, ax = plt.subplots(figsize=(8, 4.6), dpi=160)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    top = max(t["share"] for t in ts)
    xmid = top / 2
    ax.axvline(xmid, color=LINE, lw=1, zorder=1)
    ax.axhline(1.75, color=LINE, lw=1, zorder=1)
    ax.fill_between([xmid, top * 1.15], 1.75, 3.9, color=TINT, zorder=0)
    ax.text(top * 1.12, 3.8, "act first", ha="right", va="top", fontsize=8, color=MUTED, style="italic")
    keys = []
    for n, th in enumerate(x["themes"], 1):
        t = themes_by_id[th["id"]]
        if t.get("impact") is None:
            continue
        y = t["impact"] + 0.25 * (
            t.get("actionability") or 0
        )  # ease of acting nudges a theme up within its impact band
        ax.scatter(
            t["share"],
            y,
            s=120 + 18 * t["count"] ** 0.8,
            color=THEME_COLOUR[th["id"]],
            alpha=0.85,
            edgecolors="white",
            lw=1.2,
            zorder=3,
        )
        ax.annotate(
            str(n), (t["share"], y), fontsize=8, fontweight="bold", color="white", ha="center", va="center", zorder=4
        )
        keys.append(
            plt.Line2D(
                [],
                [],
                marker="o",
                color=THEME_COLOUR[th["id"]],
                linestyle="",
                markersize=7,
                label=f"{n}. {th['title'][:60]}",
            )
        )
    ax.set_xlim(0, top * 1.15)
    ax.set_ylim(-0.3, 3.9)
    ax.set_xlabel("Reach: share of all feedback (%)", fontsize=8, color=MUTED)
    ax.set_ylabel("Impact (agent's judgement)", fontsize=8, color=MUTED)
    ax.set_yticks([0, 1, 2, 3])
    ax.set_yticklabels(["none", "minor", "major", "blocking"], fontsize=7.5, color=MUTED)
    ax.tick_params(axis="x", labelsize=7.5, colors=MUTED)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.legend(
        handles=keys,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.14),
        ncol=2,
        frameon=False,
        fontsize=7.5,
        handletextpad=0.3,
        columnspacing=1.2,
    )
    fig.tight_layout()
    fig.savefig("out/matrix.png", facecolor="white", bbox_inches="tight")
    plt.close(fig)
    return True


def asset(name):
    """The profile's own image, if it has one: profiles/<key>/assets/<name>.png or .jpg."""
    for ext in ("png", "jpg", "jpeg"):
        p = os.path.join(config.ROOT, "profiles", cfg["key"], "assets", f"{name}.{ext}")
        if os.path.exists(p):
            return p
    return None


def draw_logo():
    """The profile's logo (assets/logo.png or .jpg), embedded in the brief so email clients show it without fetching."""
    own = asset("logo")
    if not own:
        return False
    if own.endswith(".png"):
        import shutil

        shutil.copy(own, "out/logo.png")
        return True
    plt = _plt()
    if not plt:
        return False
    plt.imsave("out/logo.png", plt.imread(own))
    return True


def draw_header():
    """The header background: the profile's own image (assets/header.png or .jpg), cropped to the header and darkened
    with a black overlay so white text stays readable; otherwise a gradient in the profile's colours."""
    plt = _plt()
    if not plt:
        return False
    from matplotlib.colors import LinearSegmentedColormap

    fig = plt.figure(figsize=(12.8, 3.2), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 12.8)
    ax.set_ylim(0, 3.2)
    ax.axis("off")
    own = asset("header")
    if own:
        im = plt.imread(own)
        h, w = im.shape[:2]
        if w / h > 4:  # crop the middle to the header's 4:1 shape
            cut = int((w - 4 * h) / 2)
            im = im[:, cut : w - cut]
        else:
            cut = int((h - w / 4) / 2)
            im = im[cut : h - cut]
        ax.imshow(im, extent=[0, 12.8, 0, 3.2], aspect="auto")
        ax.add_patch(
            plt.Rectangle((0, 0), 12.8, 3.2, color="#000000", alpha=0.68, lw=0)
        )  # dark overlay keeps the white text readable
    else:
        import math

        ax.imshow(
            [[i / 255 for i in range(256)]],
            extent=[0, 12.8, 0, 3.2],
            aspect="auto",
            cmap=LinearSegmentedColormap.from_list("b", [BRAND, BRAND2]),
        )
        for k in range(5):  # soft waves
            ys = [1.2 + 0.35 * k + 0.45 * math.sin(xv / 1.7 + k * 1.3) for xv in [i / 10 for i in range(129)]]
            ax.fill_between(
                [i / 10 for i in range(129)], ys, 3.2 if k % 2 else 0, color="white", alpha=0.035 + 0.01 * k, lw=0
            )
    fig.savefig("out/header.png")
    plt.close(fig)
    return True


os.makedirs("out", exist_ok=True)
made = {"map.png": draw_map(), "matrix.png": draw_matrix(), "header.png": draw_header(), "logo.png": draw_logo()}
cids = {name: make_msgid(domain="brief.local")[1:-1] for name, ok in made.items() if ok}
uri = lambda name: (
    ("data:image/png;base64," + base64.b64encode(open(f"out/{name}", "rb").read()).decode()) if name in cids else ""
)
html_preview = page(uri, preview=True)  # first render numbers the citations
open("out/brief.md", "w").write(markdown())
open("out/preview.html", "w").write(html_preview)
json.dump(CLAIMS, open("out/claims.json", "w"), indent=1, ensure_ascii=False)
log = [json.loads(l) for l in open("checks_log.jsonl")] if os.path.exists("checks_log.jsonl") else []
tags_all = {}
for p_ in ["tags/carried.json"] + sorted(glob.glob("tags/part_*.json")):
    if os.path.exists(p_):
        tags_all.update(json.load(open(p_)))
agent_sentences = sum(
    len(checks.sentences(v))
    for v in [t.get("summary") for t in x["themes"]]
    + [a.get("detail") for a in x.get("actions") or []]
    + [(a.get("ticket") or {}).get("body") for a in x.get("actions") or []]
)
metrics = {
    "date": info["date"],
    "items": len(items),
    "itemsTagged": sum(1 for i in items if i in tags_all),
    "untaggedShare": S.get("untaggedShare"),
    "connections": {c["id"]: c["status"] for c in S.get("connections", [])},
    "quotesVerified": sum(len(t.get("evidence") or []) for t in kept_themes.values()),
    "quotesShown": sum(len(t["quotes"]) for t in x["themes"]),
    "agentSentences": agent_sentences,
    "sentencesCited": sum(1 for c in CLAIMS if c["where"] != "headline"),
    "itemsCited": len(CITED),
    "claims": len(CLAIMS),
    "claimsVerified": sum(1 for c in CLAIMS if VERDICTS.get(c["id"], {}).get("supported")),
    "claimsUnsupported": [c["id"] for c in CLAIMS if c["id"] in VERDICTS and not VERDICTS[c["id"]].get("supported")],
    "checkFailuresCaught": sum(len(r["errors"]) for r in log),
    "checkRunsFailed": len(log),
    "tagsCarried": len(json.load(open("tags/carried.json"))) if os.path.exists("tags/carried.json") else 0,
    "minutes": (
        round(
            (datetime.datetime.now().astimezone() - datetime.datetime.fromisoformat(info["startedAt"])).total_seconds()
            / 60,
            1,
        )
        if info.get("startedAt")
        else None
    ),
    "usage": (
        json.load(open("usage.json")) if os.path.exists("usage.json") else None
    ),  # tokens, if the harness reports them
}
json.dump(metrics, open("out/metrics.json", "w"), indent=2)
html_part = page(lambda name: f"cid:{cids[name]}" if name in cids else "")
open("out/email.html", "w").write(html_part)
open("out/email.txt", "w").write(text())
m = EmailMessage()
m["Subject"], m["To"] = x["subject"], cfg["recipient"]
m["Date"] = format_datetime(datetime.datetime.now().astimezone())
m.set_content(text())
m.add_alternative(html_part, subtype="html")
for name, cid in cids.items():
    m.get_payload()[1].add_related(
        open(f"out/{name}", "rb").read(), "image", "png", cid=f"<{cid}>", disposition="inline", filename=name
    )
open("out/email.eml", "wb").write(bytes(m))
print(
    f"wrote {info['folder']}/out/brief.md, preview.html and email.eml"
    + (" with the feedback map" if "map.png" in cids else "")
)
print(f"preview: {os.path.abspath('out/preview.html')}")
