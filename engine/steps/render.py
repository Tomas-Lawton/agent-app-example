import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # engine/
import datetime, hashlib, html, json, shutil
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
BRAND2 = TH.get("brand2", ACCENT)
INK, MUTED = TH.get("ink", "#111827"), TH.get("muted", "#6b7280")
LINE, BG = TH.get("line", "#e5e7eb"), TH.get("background", "#f5f6f8")
KIND = {
    "problem": TH.get("problem", "#c2410c"),
    "request": TH.get("request", "#2563eb"),
    "praise": TH.get("praise", "#15803d"),
    "question": TH.get("question", "#7c3aed"),
}
TREND = {"rising": ("Rising this period", ACCENT), "easing": ("Easing", "#15803d")}
NAME = cfg.get("wording", {}).get("title", "Customer Pulse")
PRODUCT = cfg.get("product", "")
F = "font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Arial,Helvetica,sans-serif;"  # no quotes: styles sit in single quoted attributes
e = lambda s: html.escape(str(s if s is not None else ""))
themes_by_id = {t["id"]: t for t in S["themes"]}
CITED = []  # item ids in order of first citation, numbered [1], [2] ... across the pulse
SRC_COLOURS = ["#334155", "#0f766e", "#9333ea", "#b45309", "#be123c"]
SRC_COLOUR = {c["id"]: SRC_COLOURS[n % 5] for n, c in enumerate(S.get("connections", []))}


def item_text(i):
    it = items.get(i, {})
    return ((it.get("title") or "") + " " + it.get("text", "")).strip()


def claim_fields():
    """Every piece of the agent's writing that carries citations, labelled by where it sits in the pulse."""
    fields = [("headline", x.get("headline"))]
    fields += [(f"theme {t['id']}", t.get("summary")) for t in x.get("themes") or []]
    fields += [(f"watch {w['id']}", w.get("why")) for w in x.get("watch") or []]
    for entry in (x.get("themes") or []) + (x.get("watch") or []):  # each quote must be a clear example of its theme
        for q in entry.get("quotes") or []:
            fields.append(
                (
                    f"quote {entry['id']}",
                    f'This feedback is a clear example of "{entry.get("title", "")}" [{q["item"]}].',
                )
            )
    for a in x.get("actions") or []:
        fields.append((f"action {a['theme']}", a.get("detail")))  # optional
        tk = a.get("ticket") or {}
        if tk.get("issue") and tk.get("items"):
            fields.append((f"ticket {a['theme']}", f"{tk['issue']} [{', '.join(tk['items'])}]"))
    return fields


def claims():
    """Every sentence the agent wrote with citations, with the text of the items it cites, for the verifier."""
    out = []
    for where, text in claim_fields():
        for sentence in checks.sentences(text):
            ids = checks.citations(sentence)
            if ids:
                plain = checks.CITE.sub("", sentence).strip()
                out.append(
                    {
                        "id": hashlib.sha1(f"{where}|{plain}".encode()).hexdigest()[:10],
                        "where": where,
                        "claim": plain,
                        "cited": [{"id": i, "text": item_text(i)} for i in ids],
                    }
                )
    return out


CLAIMS = claims()
VERDICTS = json.load(open("verdicts.json")) if os.path.exists("verdicts.json") else {}
verified = lambda where: bool(VERDICTS) and all(
    VERDICTS.get(c["id"], {}).get("supported") for c in CLAIMS if c["where"] == where
)


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


def source_label(sid):
    c = conns.get(sid, {})
    label = e(c.get("label") or sid)
    return f"<a href='{e(c['link'])}' style='color:{BRAND}'>{label}</a>" if c.get("link") else label


def source_tag(sid):
    """A small coloured tag naming the connection."""
    colour = SRC_COLOUR.get(sid, "#334155")
    return (
        f"<span style='display:inline-block;{F}font-size:11px;font-weight:600;color:{colour};background:#ffffff;"
        f"border:1px solid {colour};border-radius:999px;padding:1px 8px;margin-right:6px'>{source_label(sid)}</span>"
    )


def source_counts(s):
    return "".join(
        f"{source_tag(k)}<span style='margin-right:8px'>{v}</span>" for k, v in (s.get("sources") or {}).items()
    )


def box_style(accent=None):
    edge = f"border-left:4px solid {accent};" if accent else ""
    return (
        f"background:#ffffff;border:1px solid {LINE};{edge}border-radius:12px;"
        f"padding:16px 18px;box-shadow:0 1px 2px rgba(16,24,40,.05)"
    )


def box(inner, accent=None):
    return {"inner": inner, "accent": accent}  # drawn by full() or grid()


def full(b):
    return f"<tr><td style='padding:8px 24px'><div style='{box_style(b['accent'])}'>{b['inner']}</div></td></tr>"


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


def section(title, sub=""):
    sub = f"<div style='{F}font-size:13px;color:{MUTED};margin-top:4px'>{sub}</div>" if sub else ""
    return (
        f"<tr><td style='padding:30px 24px 6px'><div style='{F}font-size:22px;font-weight:800;color:{BRAND};letter-spacing:-.2px'>{e(title)}</div>"
        f"<div style='width:40px;height:3px;background:{ACCENT};border-radius:2px;margin-top:6px'></div>{sub}</td></tr>"
    )


def stat(label, value, sub=""):
    return (
        f"<td class='stat' width='25%' style='padding:14px 8px;text-align:center'>"
        f"<div style='{F}font-size:26px;font-weight:800;color:{BRAND}'>{e(value)}</div>"
        f"<div style='{F}font-size:11px;color:{MUTED};text-transform:uppercase;letter-spacing:.5px;margin-top:2px'>{e(label)}</div>"
        f"<div style='{F}font-size:11px;color:{MUTED};margin-top:2px'>{sub}</div></td>"
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


def label(where, n):
    """The small line under the agent's writing: its interpretation, how many items it cites, and whether verified."""
    tick = " &middot; <span style='color:#15803d'>&#10003; claims verified</span>" if verified(where) else ""
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


def action_ticket(a):
    """An action is its draft ticket: title, the issue, who owns it and the feedback it rests on."""
    tk = a.get("ticket") or {}
    refs = cite("[" + ", ".join(tk.get("items") or []) + "]") if tk.get("items") else ""
    return (
        f"<div style='{F}font-size:11px;color:{MUTED};text-transform:uppercase;letter-spacing:.5px'>"
        f"Draft ticket for {e(a.get('owner'))} &middot; not filed</div>"
        f"<div style='{F}font-size:16px;font-weight:700;color:{INK};margin-top:3px'>{e(tk.get('title') or a.get('title'))}</div>"
        f"<div style='{F}font-size:14px;line-height:1.55;color:{INK};margin-top:4px'>{e(tk.get('issue'))}</div>"
        f"<div style='{F}font-size:12px;color:{MUTED};margin-top:6px'>Feedback: {refs}</div>"
    )


# ---------------------------------------------------------------- charts
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


# ---------------------------------------------------------------- the pulse
PRIVATE_NOTE = (
    f"<div style='{F}font-size:12px;color:{MUTED};margin-top:10px;font-style:italic'>No quotes: this feedback is private, "
    "so it is described and cited but not quoted (setup can allow quoting for a pulse that stays inside the company).</div>"
)
CAP_NOTE = f"Based on the newest {cfg['scope']['collect']['maxItems']} items in the window."


def header_row(img):
    logo = img("logo.png")
    logo_td = (
        f"<td width='92' valign='middle'><img src='{e(logo)}' width='76' height='76' alt='' "
        f"style='display:block;border-radius:14px'/></td>"
        if logo
        else ""
    )
    art = img("header.png")
    background = f"url({art})" if art else f"linear-gradient(135deg,{BRAND} 0%,{BRAND2} 100%)"
    return (
        f"<tr><td bgcolor='{BRAND}' background='{art}' style='background:{BRAND};background-image:{background}"
        f";background-size:cover;background-position:center;padding:52px 28px'>"
        f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0'><tr>{logo_td}<td valign='middle'>"
        f"<div style='{F}font-size:13px;font-weight:800;color:#ffffff;text-transform:uppercase;letter-spacing:1.2px'>{e(PRODUCT)}</div>"
        f"<div style='{F}font-size:26px;font-weight:700;color:#ffffff;margin-top:2px'>{e(NAME)}</div>"
        f"<div style='{F}font-size:13px;color:#ffffff;opacity:.9;margin-top:4px'>{e(x['meta']['dateLabel'])} &middot; feedback from {e(x['meta']['windowLabel'])}</div>"
        f"</td></tr></table></td></tr>"
    )


def stats_row():
    t, src = S["totals"], S["sources"]
    return (
        f"<tr><td style='padding:14px 24px 0'><table role='presentation' width='100%' cellpadding='0' cellspacing='0' "
        f"style='background:#ffffff;border:1px solid {LINE};border-radius:12px'><tr>"
        + stat("Items", t["items"], "newest in the window" if S.get("capped") else "")
        + stat("Avg rating", t["avgRating"] if t["avgRating"] is not None else "n/a")
        + stat("1 or 2 stars", f"{t['lowShare']}%" if t["lowShare"] is not None else "n/a")
        + stat(
            "Connections",
            f"{src['ok']} of {sum(src.values())}",
            f"{src['blocked']} blocked" if src["blocked"] else "all read",
        )
        + "</tr></table></td></tr>"
    )


def read_from_row():
    chips = []
    for c in S.get("connections", []):
        ok = c["status"] == "ok"
        tail = f"{c.get('kept', 0)} items" if ok else c["status"]
        lock = " &middot; private" if c.get("private") else ""
        chips.append(
            f"<span style='display:block;margin:6px 0 0'>{source_tag(c['id'])}"
            f"<span style='{F}font-size:12px;color:{INK if ok else '#c2410c'}'>{e(c['type'])} &middot; {e(tail)}{lock}</span></span>"
        )
    row = f"<tr><td style='padding:6px 24px 0'><div style='{F}font-size:12px;color:{MUTED}'>Read from:</div>{''.join(chips)}</td></tr>"
    if S.get("capped"):
        row += f"<tr><td style='padding:8px 24px 0'><div style='{F}font-size:12px;color:{MUTED}'>{e(CAP_NOTE)}</div></td></tr>"
    return row


def theme_card(th):
    s = themes_by_id[th["id"]]
    trend = pill(*TREND[s["trend"]]) if s["trend"] in TREND else ""
    rating = f" &middot; average rating {s['avgRating']}" if s["avgRating"] is not None else ""
    size = f"{s['count']} items &middot; {s['share']}% of all feedback &middot; {s['firstHalf']} then {s['secondHalf']} across the period"
    return box(
        f"<a name='{e(th['id'])}' id='{e(th['id'])}'></a><div>{pill(s['kind'], KIND.get(s['kind'], BRAND), solid=True)}{trend}</div>"
        f"<div style='{F}font-size:17px;font-weight:700;color:{INK};margin-top:4px'>{e(th['title'])}</div>"
        f"<div style='{F}font-size:12px;color:{MUTED};margin-top:3px'>{size}{rating}</div>"
        f"<div style='{F}font-size:14px;line-height:1.55;color:{INK};margin-top:8px'>{cite(th['summary'])}</div>"
        + label(f"theme {th['id']}", len(set(checks.citations(th["summary"]))))
        + ("".join(quote(q) for q in th["quotes"]) or PRIVATE_NOTE)
        + f"<div style='{F}font-size:12px;color:{MUTED};margin-top:10px'>From {source_counts(s)}</div>",
        accent=KIND.get(s["kind"], BRAND),
    )


def theme_rows():
    issues = [th for th in x["themes"] if themes_by_id[th["id"]]["kind"] != "praise"]
    working = [th for th in x["themes"] if themes_by_id[th["id"]]["kind"] == "praise"]
    rows = []
    if issues:
        rows.append(section("What customers are saying", "Every quote is word for word, with its source"))
        rows += [full(theme_card(th)) for th in issues]
    if working:
        rows.append(section("What's working", "What customers praise: worth passing on to the teams behind it"))
        rows.append(grid([theme_card(th) for th in working]))
    return rows


def watch_box(w, s):
    count = s.get("count", 0)
    return box(
        f"<div style='{F}font-size:16px;font-weight:700;color:{INK}'>{e(w['title'])}</div>"
        f"<div style='{F}font-size:12px;color:{MUTED};margin-top:3px'>{count} item{'s' if count != 1 else ''} &middot; From {source_counts(s)}</div>"
        f"<div style='{F}font-size:14px;line-height:1.55;color:{INK};margin-top:8px'>{cite(w['why'])}</div>"
        + label(f"watch {w['id']}", len(set(checks.citations(w["why"]))))
        + "".join(quote(q) for q in w.get("quotes") or []),
        accent="#b91c1c",
    )


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
        rows.append(
            card(
                f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0'><tr>"
                f"<td width='40' valign='top'><div style='{F}width:30px;height:30px;border-radius:15px;background:{ACCENT};color:#fff;"
                f"font-weight:700;font-size:15px;line-height:30px;text-align:center'>{n}</div></td>"
                f"<td valign='top'>{action_ticket(a)}</td></tr></table>"
            )
        )
    return rows


def ask_rows():
    qs = "".join(f"<li style='margin:2px 0'>&ldquo;{e(q)}&rdquo;</li>" for q in x.get("questions") or [])
    return [
        section("Ask your agent"),
        card(
            f"<div style='{F}font-size:14px;line-height:1.6;color:{INK}'>Ask the agent in the conversation where this pulse "
            f"was made, or open the project in your agent harness. It answers from this pulse's evidence, with every claim "
            f"cited. For example:<ul style='margin:6px 0 0 18px;padding:0'>{qs}</ul>"
            f"<div style='{F}font-size:12px;color:{MUTED};margin-top:8px'>You can also ask it to change the pulse "
            f"(&ldquo;make it shorter&rdquo;) or add a connection.</div></div>"
        ),
    ]


def footer_row():
    srcs = []
    for c in S.get("connections", []):
        tail = f"{c.get('kept', 0)} items" if c["status"] == "ok" else f"{c['status']}: {c.get('reason', '')}"
        if c.get("note"):
            tail += f" ({c['note']})"
        srcs.append(f"{source_label(c['id'])}{' (private)' if c.get('private') else ''}: {e(tail)}")
    return (
        f"<tr><td style='padding:22px 24px 26px'><div style='{F}font-size:12px;line-height:1.65;color:{MUTED}'>"
        f"<b>Sources.</b> {'; '.join(srcs)}.<br/>{e(x['footer'])}<br/>"
        f"Written by an AI agent. Every quote was checked word for word against the collected feedback, every number was "
        f"computed by code, and private feedback is quoted only when setup allows it. Names, emails and reference numbers "
        f"are removed before anything is written.</div></td></tr>"
    )


def evidence_row(n, i):
    it = items.get(i, {})
    link = f" &middot; <a href='{e(it['url'])}' style='color:{BRAND}'>open</a>" if it.get("url") else ""
    text = (f"{it['title']}: " if it.get("title") else "") + it.get("text", "")
    if len(text) > 160:  # one short line per item keeps the email small; the full text stays with the run
        text = text[:157].rsplit(" ", 1)[0] + "…"
    return (
        f"<tr id='ev-{e(i)}'><td style='{F}font-size:12px;line-height:1.5;color:{INK};padding:6px 0;border-top:1px solid {LINE}'>"
        f"<b>[{n}]</b> {source_tag(it.get('source'))}<span style='color:{MUTED}'>{e(i)} &middot; {e(it.get('date'))} "
        f"{stars(it.get('rating'), it.get('ratingScale'))}{link}</span><br/>{e(text)}</td></tr>"
    )


def evidence():
    """The items the pulse cites, numbered. Everything collected stays with the run, for the agent to answer questions from."""
    rows = "".join(evidence_row(n, i) for n, i in enumerate(CITED, 1))
    more = (
        f"<div style='{F}font-size:12px;color:{MUTED};margin-top:8px'>All {len(items)} items collected are kept with this run; "
        f"ask your agent about any of them.</div>"
    )
    table = f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0'>{rows}</table>"
    return section("Evidence", "Every item the pulse cites") + card(table + more)


def body(img):
    rows = [
        header_row(img),
        f"<tr><td style='padding:22px 24px 4px'><div style='{F}font-size:18px;line-height:1.5;color:{INK}'>{cite(x['headline'])}</div></td></tr>",
        stats_row(),
        read_from_row(),
        section("At a glance"),
        card(volume_chart()),
        card(themes_chart()),
    ]
    rows += theme_rows() + watch_rows() + action_rows() + ask_rows()
    rows += [footer_row(), evidence()]  # the evidence comes last, once every citation is numbered
    return "".join(rows)


def mix(a, b, w):
    """Blend two hex colours: w=0 gives a, w=1 gives b."""
    a, b = [[int(c.lstrip("#")[k : k + 2], 16) for k in (0, 2, 4)] for c in (a, b)]
    return "#" + "".join(f"{round(x + (y - x) * w):02x}" for x, y in zip(a, b))


def page(img):
    """The pulse as one email-safe page: tables and inline styles, no scripts."""
    DEEP = mix(BRAND, "#000000", 0.35)  # the primary colour, a bit darker
    css = (
        "@media (max-width:620px){.wrap{width:100%!important}.stat{display:block!important;width:100%!important;"
        "border-bottom:1px solid "
        + LINE
        + "}.col{display:block!important;width:auto!important;margin-bottom:12px}.gap{display:none!important}}"
    )
    return (
        f"<!doctype html><html><head><meta charset='utf-8'/><meta name='viewport' content='width=device-width,initial-scale=1'/>"
        f"<title>{e(x['subject'])}</title><style>{css}</style></head>"
        f"<body style='margin:0;padding:24px 0;min-height:100vh;background:{DEEP};"
        f"background-image:linear-gradient(135deg,{DEEP} 0%,{mix(DEEP, BRAND, .5)} 70%,{mix(BRAND, ACCENT, .12)} 100%);background-attachment:fixed'>"
        f"<div style='display:none;max-height:0;overflow:hidden'>{e(x['preheader'])}</div>"
        f"<table role='presentation' class='wrap' width='760' align='center' cellpadding='0' cellspacing='0' "
        f"style='width:760px;max-width:100%;margin:0 auto;background:{BG};border-radius:16px;overflow:hidden;"
        f"box-shadow:0 24px 60px rgba(0,0,0,.35),0 4px 14px rgba(0,0,0,.18)'>{body(img)}</table></body></html>"
    )


def chat_summary():
    """The short version for the chat (and the email's plain text part), from the same computed numbers."""
    out = [
        f"# {NAME}",
        f"*{PRODUCT} · {x['meta']['dateLabel']} · feedback from {x['meta']['windowLabel']}*",
        "",
        x["headline"],
    ]
    if S.get("capped"):
        out += ["", f"*{CAP_NOTE}*"]
    if x.get("actions"):
        out += ["", "## Top actions"]
        for n, a in enumerate(x["actions"], 1):
            tk = a.get("ticket") or {}
            out.append(
                f"{n}. **{tk.get('title') or a.get('title', '')}** ({a.get('owner', '')}): {tk.get('issue', '')}"
            )
    out += ["", "## Themes"]
    out += [
        f"- {th['title']} ({themes_by_id[th['id']]['count']} items, {themes_by_id[th['id']]['share']}%)"
        for th in x["themes"]
    ]
    if x.get("watch"):
        counts = {w["id"]: w.get("count", 0) for w in S.get("watch", [])}
        out += ["", "## Watchlist"] + [f"- {w['title']} ({counts.get(w['id'], 0)} items)" for w in x["watch"]]
    out += ["", "## Ask your agent"] + [f"- {q}" for q in x.get("questions") or []]
    out += ["", "The full pulse, with quotes and evidence, is in preview.html."]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- images
def _plt():
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        return plt
    except ImportError:
        print(
            "matplotlib is missing, so the pulse has no header art; install it with: python3 -m pip install -r requirements.txt"
        )
        return None


def asset(name):
    """The profile's own image, if it has one: profiles/<key>/assets/<name>.png or .jpg."""
    for ext in ("png", "jpg", "jpeg"):
        p = os.path.join(config.ROOT, "profiles", cfg["key"], "assets", f"{name}.{ext}")
        if os.path.exists(p):
            return p
    return None


def draw_logo():
    """The profile's logo (assets/logo.png or .jpg), embedded in the pulse so email clients show it without fetching."""
    own = asset("logo")
    if not own:
        return False
    if own.endswith(".png"):
        shutil.copy(own, "out/logo.png")
        return True
    plt = _plt()
    if not plt:
        return False
    plt.imsave("out/logo.png", plt.imread(own))
    return True


def crop_to_header(im):
    """The middle of an image, cut to the header's 4:1 shape."""
    h, w = im.shape[:2]
    if w / h > 4:
        cut = int((w - 4 * h) / 2)
        return im[:, cut : w - cut]
    cut = int((h - w / 4) / 2)
    return im[cut : h - cut]


def draw_waves(plt, ax):
    """A gradient in the profile's colours with soft waves, when the profile has no header image."""
    import math
    from matplotlib.colors import LinearSegmentedColormap

    gradient = LinearSegmentedColormap.from_list("b", [BRAND, BRAND2])
    ax.imshow([[i / 255 for i in range(256)]], extent=[0, 12.8, 0, 3.2], aspect="auto", cmap=gradient)
    xs = [i / 10 for i in range(129)]
    for k in range(5):
        ys = [1.2 + 0.35 * k + 0.45 * math.sin(xv / 1.7 + k * 1.3) for xv in xs]
        ax.fill_between(xs, ys, 3.2 if k % 2 else 0, color="white", alpha=0.035 + 0.01 * k, lw=0)


def draw_header():
    """The header background: the profile's own image (assets/header.png or .jpg), cropped to the header and darkened
    with a black overlay so white text stays readable; otherwise a gradient in the profile's colours."""
    plt = _plt()
    if not plt:
        return False
    fig = plt.figure(figsize=(12.8, 3.2), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 12.8)
    ax.set_ylim(0, 3.2)
    ax.axis("off")
    own = asset("header")
    if own:
        ax.imshow(crop_to_header(plt.imread(own)), extent=[0, 12.8, 0, 3.2], aspect="auto")
        ax.add_patch(
            plt.Rectangle((0, 0), 12.8, 3.2, color="#000000", alpha=0.68, lw=0)
        )  # dark overlay keeps the white text readable
    else:
        draw_waves(plt, ax)
    fig.savefig("out/header.png")
    plt.close(fig)
    return True


# ---------------------------------------------------------------- write
def email_message(html_part, text_part, cids):
    m = EmailMessage()
    m["Subject"], m["To"] = x["subject"], cfg["recipient"]
    m["Date"] = format_datetime(datetime.datetime.now().astimezone())
    m.set_content(text_part)
    m.add_alternative(html_part, subtype="html")
    for name, cid in cids.items():
        m.get_payload()[1].add_related(
            open(f"out/{name}", "rb").read(), "image", "png", cid=f"<{cid}>", disposition="inline", filename=name
        )
    return m


os.makedirs("out", exist_ok=True)
made = {"header.png": draw_header(), "logo.png": draw_logo()}
cids = {name: make_msgid(domain="pulse.local")[1:-1] for name, ok in made.items() if ok}
html_part = page(lambda name: f"cid:{cids[name]}" if name in cids else "")
preview = html_part
for name, cid in cids.items():  # the same page; in a browser the images are the files next to it
    preview = preview.replace(f"cid:{cid}", name)
summary_text = chat_summary()
open("out/preview.html", "w").write(preview)
open("out/pulse.md", "w").write(summary_text)
json.dump(CLAIMS, open("out/claims.json", "w"), indent=1, ensure_ascii=False)
open("out/email.eml", "wb").write(bytes(email_message(html_part, summary_text, cids)))
print(f"wrote {info['folder']}/out/pulse.md, preview.html, claims.json and email.eml")
print(f"preview: {os.path.abspath('out/preview.html')}")
