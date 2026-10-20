"""Step 3: check the plan and the writing, then build the brief for the chat, a visual preview and an email.

Usage (from the repository root, after writing brief_plan.json and live_content.json):  python3 engine/steps/render.py <key>

Stops first if the plan or the writing fail a check (every quote a checked quote, every number traced, every action
with a draft ticket). Then builds from the checked files only; the layout is fixed, a profile changes colours, icon
and wording. Every theme and quote shows its source. Draws the feedback map (every item placed by similarity,
coloured by the agent's theme) with matplotlib. Writes:
  out/brief.md       the brief as markdown, for the chat of any harness
  out/map.png        the feedback map (colour shows the theme, shape shows the connection)
  out/header.png     header artwork in the profile's colours (or the profile's own assets/header.png)
  out/preview.html   the full visual brief, with copy buttons and every item collected
  out/evidence.html  every item, numbered as cited (attached to the email)
  out/claims.json    every cited sentence with the text of its items, for the independent verifier
  out/metrics.json   grounding, coverage and guardrail numbers for this run
  out/email.html, out/email.txt, out/email.eml   the email
The reader can copy each action's draft ticket and open any source. Everything else is done by talking to the agent.
Nothing is filed or posted for them.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # engine/
import base64, datetime, glob, hashlib, html, json
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
INK, MUTED, LINE, BG = TH.get("ink", "#111827"), TH.get("muted", "#6b7280"), TH.get("line", "#e5e7eb"), TH.get("background", "#f5f6f8")
TINT = TH.get("tint", "#e9efe9")
KIND = {"problem": TH.get("problem", "#c2410c"), "request": TH.get("request", "#2563eb"),
        "praise": TH.get("praise", "#15803d"), "question": TH.get("question", "#7c3aed")}
TREND = {"new": ("New", ACCENT), "growing": ("Growing", ACCENT), "rising": ("Rising this period", ACCENT), "easing": ("Easing", "#15803d")}
NAME = cfg.get("wording", {}).get("briefName", "Customer feedback brief")
PRODUCT = cfg.get("product", {})
F = "font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Arial,Helvetica,sans-serif;"  # no quotes: styles sit in single quoted attributes
e = lambda s: html.escape(str(s if s is not None else ""))
themes_by_id = {t["id"]: t for t in S["themes"]}
kept_themes = {t["id"]: t for t in json.load(open("themes.json"))["themes"] if t.get("decision") == "keep"}
CITED = []  # item ids in order of first citation, numbered [1], [2] ... across the brief


def claims():
    """Every sentence the agent wrote with citations, with the text of the items it cites, for the verifier."""
    out = []
    fields = [("headline", x.get("headline"))]
    fields += [(f"theme {t['id']}", t.get("summary")) for t in x.get("themes") or []]
    for a in x.get("actions") or []:
        fields += [(f"action {a['theme']}", a.get("detail")), (f"ticket {a['theme']}", (a.get("ticket") or {}).get("body"))]
    for where, text in fields:
        for sentence in checks.sentences(text):
            ids = checks.citations(sentence)
            if ids:
                plain = checks.CITE.sub("", sentence).strip()
                out.append({"id": hashlib.sha1(f"{where}|{plain}".encode()).hexdigest()[:10], "where": where, "claim": plain,
                            "cited": [{"id": i, "text": ((items.get(i, {}).get("title") or "") + " " + items.get(i, {}).get("text", "")).strip()} for i in ids]})
    return out


CLAIMS = claims()
VERDICTS = json.load(open("verdicts.json")) if os.path.exists("verdicts.json") else {}
verified = lambda where: bool(VERDICTS) and all(VERDICTS.get(c["id"], {}).get("supported") for c in CLAIMS if c["where"] == where)
SRC_COLOURS = ["#334155", "#0f766e", "#9333ea", "#b45309", "#be123c"]
SRC_MARKERS = ["o", "^", "s", "D", "P"]
SRC_SYMBOLS = ["&#9679;", "&#9650;", "&#9632;", "&#9670;", "&#10010;"]  # the same shapes, for the html
SRC_STYLE = {c["id"]: (SRC_COLOURS[n % 5], SRC_MARKERS[n % 5], SRC_SYMBOLS[n % 5]) for n, c in enumerate(S.get("connections", []))}


# ---------------------------------------------------------------- pieces
def stars(r, scale):
    if r is None or not scale:
        return ""
    n = round(r / scale * 5)
    return f"<span style='color:{ACCENT}'>{'&#9733;' * n}</span><span style='color:{LINE}'>{'&#9733;' * (5 - n)}</span>"


def pill(text, colour, solid=False):
    style = f"background:{colour};color:#fff;" if solid else f"color:{colour};border:1px solid {colour};"
    return (f"<span style='display:inline-block;{F}font-size:11px;font-weight:600;{style}border-radius:999px;"
            f"padding:2px 9px;margin:0 6px 4px 0;text-transform:uppercase;letter-spacing:.4px'>{e(text)}</span>")


def copy_button(text, preview, label="Copy"):
    if not preview:
        return ""
    return (f"<button onclick='copyText(this)' data-t='{e(text)}' "
            f"style='{F}font-size:13px;font-weight:600;color:#fff;background:{BRAND};border:0;border-radius:8px;padding:8px 12px;"
            f"margin:6px 6px 0 0;cursor:pointer'>{e(label)}</button>")


def source_label(sid):
    c = conns.get(sid, {})
    label = e(c.get("label") or sid)
    return f"<a href='{e(c['link'])}' style='color:{BRAND}'>{label}</a>" if c.get("link") else label


def card(inner, accent=None):
    edge = f"border-left:4px solid {accent};" if accent else ""
    return (f"<tr><td style='padding:8px 24px'><div style='background:#ffffff;border:1px solid {LINE};{edge}border-radius:12px;"
            f"padding:16px 18px;box-shadow:0 1px 2px rgba(16,24,40,.05)'>{inner}</div></td></tr>")


def section(title, sub=""):
    sub = f"<div style='{F}font-size:13px;color:{MUTED};margin-top:2px'>{sub}</div>" if sub else ""
    return (f"<tr><td style='padding:26px 24px 4px'><div style='{F}font-size:18px;font-weight:700;color:{INK}'>{e(title)}</div>{sub}</td></tr>")


def stat(label, value, sub=""):
    return (f"<td class='stat' width='25%' style='padding:14px 8px;text-align:center'>"
            f"<div style='{F}font-size:24px;font-weight:700;color:{INK}'>{e(value)}</div>"
            f"<div style='{F}font-size:11px;color:{MUTED};text-transform:uppercase;letter-spacing:.5px;margin-top:2px'>{e(label)}</div>"
            f"<div style='{F}font-size:11px;color:{MUTED};margin-top:2px'>{sub}</div></td>")


def delta(v, unit="", better="up"):
    if v is None:
        return "first edition"
    if v == 0:
        return "no change"
    good = (v > 0) == (better == "up")
    return f"<span style='color:{'#15803d' if good else '#c2410c'}'>{'+' if v > 0 else ''}{v:g}{unit} vs last run</span>"


def source_tag(sid):
    """A small coloured tag naming the connection, with the same shape it has on the map."""
    colour, _, symbol = SRC_STYLE.get(sid, ("#334155", "o", "&#9679;"))
    return (f"<span style='display:inline-block;{F}font-size:11px;font-weight:600;color:{colour};background:#ffffff;"
            f"border:1px solid {colour};border-radius:999px;padding:1px 8px;margin-right:6px'>{symbol} {source_label(sid)}</span>")


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
    meta = source_tag(it.get("source")) + " &middot; ".join(filter(None, [e(it.get("date")), stars(it.get("rating"), it.get("ratingScale"))]))
    link = f" &middot; <a href='{e(it['url'])}' style='color:{BRAND}'>open</a>" if it.get("url") else ""
    return (f"<div style='background:{BG};border-radius:10px;padding:10px 14px;margin:10px 0 0'>"
            f"<div style='{F}font-size:14px;line-height:1.55;color:{INK}'>&ldquo;{e(q['text'])}&rdquo;</div>"
            f"<div style='{F}font-size:12px;color:{MUTED};margin-top:4px'>{meta}{link}</div></div>")


def ticket(a, preview):
    tk = a.get("ticket") or {}
    if not tk:
        return ""
    return (f"<div style='background:{TINT};border-radius:10px;padding:10px 12px;margin-top:10px'>"
            f"<div style='{F}font-size:11px;color:{MUTED};text-transform:uppercase;letter-spacing:.5px'>Draft ticket, not filed</div>"
            f"<div style='{F}font-size:14px;font-weight:700;color:{INK};margin-top:3px'>{e(tk.get('title'))}</div>"
            f"<div style='{F}font-size:13px;line-height:1.55;color:{INK};margin-top:4px;white-space:pre-line'>{cite(tk.get('body'))}</div>"
            f"{copy_button(tk.get('title', '') + chr(10) + chr(10) + ticket_text(tk.get('body', '')), preview, 'Copy ticket')}</div>")


def ticket_text(body):
    """A copied ticket keeps its evidence: each citation becomes the item's source, date and link."""
    def ref(m):
        out = []
        for i in [i.strip() for i in m.group(1).split(",")]:
            it = items.get(i, {})
            out.append(f"{it.get('sourceLabel', i)} {it.get('date', '')}" + (f" {it['url']}" if it.get("url") else f" ({i})"))
        return "(" + "; ".join(out) + ")"
    return checks.CITE.sub(ref, body)


# ---------------------------------------------------------------- the brief
def volume_chart():
    days = S["daily"]
    top = max([d["count"] for d in days] + [1])
    cols = []
    for d in days:
        h = max(2, round(110 * d["count"] / top))
        r = f"{d['avgRating']}" if d["avgRating"] is not None else "&nbsp;"
        cols.append(f"<td valign='bottom' align='center' style='padding:0 3px'>"
                    f"<div style='{F}font-size:11px;color:{MUTED}'>{d['count']}</div>"
                    f"<div style='height:{h}px;background:{BRAND};background-image:linear-gradient(180deg,{BRAND2},{BRAND});border-radius:6px 6px 0 0'></div>"
                    f"<div style='{F}font-size:11px;color:{MUTED};margin-top:4px'>{d['date'][8:].lstrip('0')}</div>"
                    f"<div style='{F}font-size:11px;color:{ACCENT}'>{r}</div></td>")
    return (f"<div style='{F}font-size:13px;font-weight:600;color:{INK};margin-bottom:8px'>Feedback per day "
            f"<span style='font-weight:400;color:{MUTED}'>(<span style='color:{ACCENT}'>average rating</span> below)</span></div>"
            f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0' style='table-layout:fixed'><tr>{''.join(cols)}</tr></table>")


def themes_chart():
    ts = S["themes"]
    top = max([t["count"] for t in ts] + [1])
    rows = "".join(
        f"<tr><td width='40%' style='{F}font-size:12px;color:{INK};padding:4px 8px 4px 0'>{e(t['title'])}</td>"
        f"<td style='padding:4px 0'><div style='width:{max(3, round(100 * t['count'] / top))}%;height:14px;border-radius:7px;"
        f"background:{KIND.get(t['kind'], BRAND)}'></div></td>"
        f"<td width='36' align='right' style='{F}font-size:12px;color:{MUTED}'>{t['count']}</td></tr>" for t in ts)
    legend = " ".join(f"<span style='color:{c}'>&#9632; {k}</span>" for k, c in KIND.items())
    return (f"<div style='{F}font-size:13px;font-weight:600;color:{INK};margin:20px 0 8px'>Items per theme</div>"
            f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0'>{rows}</table>"
            f"<div style='{F}font-size:12px;color:{MUTED};margin-top:6px'>{legend}</div>")


def body(preview, img):
    t, ch = S["totals"], S.get("change") or {}
    icon = PRODUCT.get("iconUrl")
    icon_td = (f"<td width='64' valign='middle'><img src='{e(icon)}' width='52' height='52' alt='' "
               f"style='display:block;border-radius:12px;border:2px solid rgba(255,255,255,.6)'/></td>") if icon else ""
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
        + stat("Avg rating", t["avgRating"] if t["avgRating"] is not None else "n/a", delta(ch.get("avgRating")) if ch else "")
        + stat("1 or 2 stars", f"{t['lowShare']}%" if t["lowShare"] is not None else "n/a", delta(ch.get("lowShare"), " pts", better="down") if ch else "")
        + stat("Connections", f"{S['sources']['ok']} of {sum(S['sources'].values())}", f"{S['sources']['blocked']} blocked" if S["sources"]["blocked"] else "all read")
        + "</tr></table></td></tr>",
    ]
    chips = []
    for c in S.get("connections", []):
        ok = c["status"] == "ok"
        tail = f"{c.get('kept', 0)} items" if ok else c["status"]
        lock = " &middot; private" if c.get("private") else ""
        chips.append(f"<span style='display:inline-block;margin:8px 4px 0 0'>{source_tag(c['id'])}"
                     f"<span style='{F}font-size:12px;color:{INK if ok else '#c2410c'}'>{e(c['type'])} &middot; {e(tail)}{lock}</span></span>")
    rows.append(f"<tr><td style='padding:6px 24px 0'><span style='{F}font-size:12px;color:{MUTED}'>Read from:</span> {''.join(chips)}</td></tr>")
    if S.get("capped"):
        rows.append(f"<tr><td style='padding:8px 24px 0'><div style='{F}font-size:12px;color:{MUTED}'>Read the {t['items']} most recent items in the window.</div></td></tr>")

    if img("map.png"):
        rows.append(section("Feedback map", "Each dot is one piece of feedback, placed near similar feedback and coloured by theme"))
        rows.append(card(f"<img src='{img('map.png')}' width='544' alt='Every item placed by similarity, coloured by theme' style='width:100%;height:auto;display:block'/>"
                         f"<div style='{F}font-size:12px;color:{MUTED};margin-top:6px'>Grouped with K-means on word vectors. Grey dots fit no theme.</div>"))
    rows.append(section("At a glance"))
    rows.append(card(volume_chart() + themes_chart()))

    rows.append(section("What customers are saying", "Every quote is word for word, with its source"))
    for th in x["themes"]:
        s = themes_by_id[th["id"]]
        trend = pill(*TREND[s["trend"]]) if s["trend"] in TREND else ""
        rating = f" &middot; average rating {s['avgRating']}" if s["avgRating"] is not None else ""
        size = f"{s['count']} items &middot; {s['share']}% of all feedback &middot; {s['firstHalf']} then {s['secondHalf']} across the period"
        prev = f" &middot; {s['previousShare']}% last run" if s.get("previousShare") is not None else ""
        srcs = "".join(f"{source_tag(k)}<span style='margin-right:8px'>{v}</span>" for k, v in (s.get("sources") or {}).items())
        rows.append(card(
            f"<a name='{e(th['id'])}' id='{e(th['id'])}'></a><div>{pill(s['kind'], KIND.get(s['kind'], BRAND), solid=True)}{trend}</div>"
            f"<div style='{F}font-size:17px;font-weight:700;color:{INK};margin-top:4px'>{e(th['title'])}</div>"
            f"<div style='{F}font-size:12px;color:{MUTED};margin-top:3px'>{size}{prev}{rating}</div>"
            f"<div style='{F}font-size:14px;line-height:1.55;color:{INK};margin-top:8px'>{cite(th['summary'])}</div>"
            + label("interpretation", f"theme {th['id']}", len(set(checks.citations(th['summary']))))
            + f"<div style='margin-top:10px'>{label('checked')}</div>"
            + "".join(quote(q) for q in th["quotes"])
            + f"<div style='{F}font-size:12px;color:{MUTED};margin-top:10px'>From {srcs}</div>",
            accent=KIND.get(s["kind"], BRAND)))

    if x.get("actions"):
        rows.append(section("Things to act on", "Ranked by impact, reach and growth, each with a draft ticket for the owning team"))
        for n, a in enumerate(x["actions"], 1):
            rows.append(card(
                f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0'><tr>"
                f"<td width='40' valign='top'><div style='{F}width:30px;height:30px;border-radius:15px;background:{ACCENT};color:#fff;"
                f"font-weight:700;font-size:15px;line-height:30px;text-align:center'>{n}</div></td>"
                f"<td valign='top'><div style='{F}font-size:16px;font-weight:700;color:{INK}'>{e(a['title'])}</div>"
                f"<div style='{F}font-size:14px;line-height:1.55;color:{INK};margin-top:4px'>{cite(a['detail'])}</div>"
                + label("interpretation", f"action {a['theme']}", len(set(checks.citations(a['detail']))))
                + f"<div style='{F}font-size:12px;color:{MUTED};margin-top:6px'>Owner: {e(a['owner'])}</div>"
                + ticket(a, preview)
                + f"</td></tr></table>"))


    rows.append(section("Ask your agent"))
    rows.append(card(f"<div style='{F}font-size:14px;line-height:1.7;color:{INK}'>"
                     "Reply in your agent to go further, for example:<br/>"
                     "&ldquo;File ticket 1 in Jira&rdquo; &middot; &ldquo;Why is the top theme growing?&rdquo; &middot; "
                     "&ldquo;Show me everything about it&rdquo; &middot; &ldquo;Make the brief shorter&rdquo; &middot; "
                     "&ldquo;Add a connection&rdquo;</div>"))

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
        f"removed before anything is written.</div></td></tr>")
    rows.append(evidence(preview))
    return "".join(rows)


def evidence_row(i, n=None):
    it = items.get(i, {})
    num = f"<b>[{n}]</b> " if n else ""
    link = f" &middot; <a href='{e(it['url'])}' style='color:{BRAND}'>open</a>" if it.get("url") else ""
    text = (f"{it['title']}: " if it.get("title") else "") + it.get("text", "")
    return (f"<tr id='ev-{e(i)}'><td style='{F}font-size:12px;line-height:1.5;color:{INK};padding:6px 0;border-top:1px solid {LINE}'>"
            f"{num}{source_tag(it.get('source'))}<span style='color:{MUTED}'>{e(i)} &middot; {e(it.get('date'))} "
            f"{stars(it.get('rating'), it.get('ratingScale'))}{link}</span><br/>{e(text)}</td></tr>")


def evidence(preview):
    """The items the brief cites, numbered; the preview and evidence.html also list every item collected."""
    cited = "".join(evidence_row(i, n) for n, i in enumerate(CITED, 1))
    every = "".join(evidence_row(i) for i in items if i not in CITED) if preview else ""
    more = (f"<div style='{F}font-size:13px;font-weight:700;color:{INK};margin:18px 0 4px'>Every other item collected ({len(items) - len(CITED)})</div>"
            f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0'>{every}</table>") if preview else (
            f"<div style='{F}font-size:12px;color:{MUTED};margin-top:8px'>Every item collected is in the attached evidence.html.</div>")
    return (section("Evidence", "Every item the brief cites, then everything collected") + card(
            f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0'>{cited}</table>{more}"))


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
</script>"""


def page(img, preview=False):
    css = ("@media (max-width:620px){.wrap{width:100%!important}.stat{display:block!important;width:100%!important;"
           "border-bottom:1px solid " + LINE + "}}")
    strip = ""
    if preview:
        strip = (f"<div style='{F}width:92%;max-width:1100px;margin:0 auto 12px;font-size:12px;color:{MUTED}'>"
                 f"<b>Subject:</b> {e(x['subject'])}<br/><b>To:</b> {e(cfg['recipient'])} &middot; "
                 f"<b>Preview line:</b> {e(x['preheader'])}</div>")
    return (f"<!doctype html><html><head><meta charset='utf-8'/><meta name='viewport' content='width=device-width,initial-scale=1'/>"
            f"<title>{e(x['subject'])}</title><style>{css}</style>{COPY_JS if preview else ''}</head>"
            f"<body style='margin:0;padding:24px 0;background:{BG};background-image:linear-gradient(180deg,{TINT} 0px,{BG} 420px)'>{strip}"
            f"<div style='display:none;max-height:0;overflow:hidden'>{e(x['preheader'])}</div>"
            + (f"<table role='presentation' class='wrap' width='100%' align='center' cellpadding='0' cellspacing='0' "
               f"style='width:92%;max-width:1100px;margin:0 auto;background:{BG};border-radius:16px;overflow:hidden;"
               if preview else
               f"<table role='presentation' class='wrap' width='640' align='center' cellpadding='0' cellspacing='0' "
               f"style='width:640px;max-width:640px;margin:0 auto;background:{BG};border-radius:16px;overflow:hidden;")
            + f"box-shadow:0 10px 30px rgba(16,24,40,.08)'>{body(preview, img)}</table></body></html>")


def text():
    out = [NAME, f"{x['meta']['dateLabel']}, feedback from {x['meta']['windowLabel']}", "", x["headline"], ""]
    for n, a in enumerate(x.get("actions") or [], 1):
        out += [f"{n}. {a['title']}", f"   {a['detail']}", f"   Owner: {a['owner']}"]
    for th in x["themes"]:
        s = themes_by_id[th["id"]]
        out += ["", f"* {th['title']} ({s['count']} items, {s['share']}%)", f"  {th['summary']}"]
        out += [f"  \"{q['text']}\" ({items.get(q['item'], {}).get('sourceLabel', '')})" for q in th["quotes"]]
    for a in x.get("actions") or []:
        tk = a.get("ticket") or {}
        out += ["", f"Draft ticket: {tk.get('title', '')}", tk.get("body", "")]
    out += ["", x["footer"]]
    return "\n".join(out)


def markdown():
    """The same order as the email: summary, map, charts as numbers, themes, then actions with their tickets."""
    t, ch = S["totals"], S.get("change") or {}
    out = [f"# {NAME}", f"*{PRODUCT.get('name', '')} · {x['meta']['dateLabel']} · feedback from {x['meta']['windowLabel']}*", "", x["headline"], ""]
    nums = [f"**{t['items']}** items"]
    if t["avgRating"] is not None:
        nums.append(f"average rating **{t['avgRating']}**" + (f" ({ch['avgRating']:+g} vs last run)" if ch.get("avgRating") else ""))
    if t["lowShare"] is not None:
        nums.append(f"**{t['lowShare']}%** at the lowest ratings")
    reads = ", ".join(f"[{c['label']}]({c['link']})" if c.get("link") else c["label"] for c in S.get("connections", []))
    out += [" · ".join(nums), f"Read from: {reads}", ""]
    if os.path.exists("out/map.png"):
        out += ["![Feedback map](map.png)", ""]
    out += ["## What customers are saying", ""]
    for th in x["themes"]:
        s = themes_by_id[th["id"]]
        trend = f" · {TREND[s['trend']][0]}" if s["trend"] in TREND else ""
        srcs = ", ".join(f"{conns.get(k, {}).get('label', k)} {v}" for k, v in (s.get("sources") or {}).items())
        out += [f"### {th['title']}", f"*{s['kind']} · {s['count']} items · {s['share']}% of feedback{trend} · sources: {srcs}*", "", th["summary"], ""]
        for q in th["quotes"]:
            it = items.get(q["item"], {})
            src = f"[{it.get('sourceLabel', '')}]({it['url']})" if it.get("url") else it.get("sourceLabel", "")
            out += [f"> \u201c{q['text']}\u201d", f"> \u2014 {src}, {it.get('date', '')}", ""]
    if x.get("actions"):
        out += ["## Things to act on", ""]
        for n, a in enumerate(x["actions"], 1):
            tk = a.get("ticket") or {}
            out += [f"{n}. **{a['title']}** {a['detail']} *Owner: {a['owner']}*", f"   > **Draft ticket: {tk.get('title', '')}**  ", f"   > {tk.get('body', '')}", ""]
    if CITED:
        out += ["## Evidence", ""]
        for n, i in enumerate(CITED, 1):
            it = items.get(i, {})
            src = f"[{it.get('sourceLabel', '')}]({it['url']})" if it.get("url") else it.get("sourceLabel", "")
            out.append(f"{n}. `{i}` · {src} · {it.get('date', '')}: {it.get('text', '')[:200]}")
        out.append("")
    out += ["---", x["footer"], "", "*Summaries and actions are the agent's interpretation, with the items they cite; quotes and numbers are checked by code.*"]
    return "\n".join(out)


# ---------------------------------------------------------------- write
def _plt():
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        return plt
    except ImportError:
        print("matplotlib is missing, so the brief has no map or header art; install it with: python3 -m pip install -r requirements.txt")
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
    palette = [BRAND, ACCENT, "#c2410c", "#7c3aed", "#15803d", "#0891b2", "#be185d", "#4d7c0f"]
    colour = {tid: palette[n % len(palette)] for n, tid in enumerate(shown)}
    fig, ax = plt.subplots(figsize=(8, 4.8), dpi=160)
    fig.patch.set_facecolor("white"); ax.set_facecolor(TINT)
    for iid, (px, py) in pos.items():
        tid = next((t for t in (tags.get(iid) or []) if t in colour), None)
        _, marker, _ = SRC_STYLE.get(items.get(iid, {}).get("source"), ("", "o", ""))
        ax.scatter(px, py, s=26 if tid else 12, marker=marker, color=colour.get(tid, "#c3cad3"), alpha=.9 if tid else .5,
                   edgecolors="white", linewidths=.4, zorder=3 if tid else 2)
    for tid in shown:  # the theme's name at the centre of its points
        pts = [pos[i] for i in pos if tid in (tags.get(i) or [])]
        if pts:
            cx, cy = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
            ax.annotate(themes_by_id[tid]["title"][:34], (cx, cy), fontsize=7.5, fontweight="bold", color=colour[tid], ha="center",
                        va="center", zorder=4, bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=colour[tid], lw=.8, alpha=.92))
    handles = [plt.Line2D([], [], marker=SRC_STYLE[c["id"]][1], color="#55606e", linestyle="", markersize=6, label=c["label"])
               for c in S.get("connections", []) if c["id"] in SRC_STYLE]
    ax.legend(handles=handles, loc="lower right", frameon=True, fontsize=7.5, framealpha=.9, title="Shape = source", title_fontsize=7.5)
    ax.set_xticks([]); ax.set_yticks([])
    for side in ax.spines.values():
        side.set_visible(False)
    fig.tight_layout()
    fig.savefig("out/map.png", facecolor="white")
    plt.close(fig)
    return True


def draw_header():
    """Header artwork in the profile's colours, unless the profile supplies its own (profiles/<key>/assets/header.png)."""
    own = os.path.join(config.ROOT, "profiles", cfg["key"], "assets", "header.png")
    if os.path.exists(own):
        import shutil
        shutil.copy(own, "out/header.png")
        return True
    plt = _plt()
    if not plt:
        return False
    import math, random
    from matplotlib.colors import LinearSegmentedColormap
    rnd = random.Random(cfg["key"])
    fig = plt.figure(figsize=(12.8, 3.2), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 12.8); ax.set_ylim(0, 3.2); ax.axis("off")
    grad = [[i / 255 for i in range(256)]]
    ax.imshow(grad, extent=[0, 12.8, 0, 3.2], aspect="auto", cmap=LinearSegmentedColormap.from_list("b", [BRAND, BRAND2]))
    for k in range(5):  # soft waves
        ys = [1.2 + .35 * k + .45 * math.sin(xv / 1.7 + k * 1.3) for xv in [i / 10 for i in range(129)]]
        ax.fill_between([i / 10 for i in range(129)], ys, 3.2 if k % 2 else 0, color="white", alpha=.035 + .01 * k, lw=0)
    for _ in range(14):  # light circles
        ax.add_patch(plt.Circle((rnd.uniform(6, 12.8), rnd.uniform(0, 3.2)), rnd.uniform(.2, 1.1), color=ACCENT if rnd.random() < .25 else "white",
                                alpha=rnd.uniform(.05, .14), lw=0))
    fig.savefig("out/header.png")
    plt.close(fig)
    return True


os.makedirs("out", exist_ok=True)
made = {"map.png": draw_map(), "header.png": draw_header()}
cids = {name: make_msgid(domain="brief.local")[1:-1] for name, ok in made.items() if ok}
uri = lambda name: ("data:image/png;base64," + base64.b64encode(open(f"out/{name}", "rb").read()).decode()) if name in cids else ""
html_preview = page(uri, preview=True)  # first render numbers the citations
open("out/brief.md", "w").write(markdown())
open("out/preview.html", "w").write(html_preview)
open("out/evidence.html", "w").write(f"<!doctype html><html><head><meta charset='utf-8'/><title>Evidence</title></head><body style='margin:24px;background:{BG}'>"
                                     f"<table role='presentation' width='100%' style='max-width:1000px;margin:0 auto'>{evidence(True)}</table></body></html>")
json.dump(CLAIMS, open("out/claims.json", "w"), indent=1, ensure_ascii=False)
log = [json.loads(l) for l in open("checks_log.jsonl")] if os.path.exists("checks_log.jsonl") else []
tags_all = {}
for p_ in ["tags/carried.json"] + sorted(glob.glob("tags/part_*.json")):
    if os.path.exists(p_):
        tags_all.update(json.load(open(p_)))
agent_sentences = sum(len(checks.sentences(v)) for v in [t.get("summary") for t in x["themes"]] + [a.get("detail") for a in x.get("actions") or []]
                      + [(a.get("ticket") or {}).get("body") for a in x.get("actions") or []])
metrics = {
    "date": info["date"], "items": len(items), "itemsTagged": sum(1 for i in items if i in tags_all), "untaggedShare": S.get("untaggedShare"),
    "connections": {c["id"]: c["status"] for c in S.get("connections", [])},
    "quotesVerified": sum(len(t.get("evidence") or []) for t in kept_themes.values()), "quotesShown": sum(len(t["quotes"]) for t in x["themes"]),
    "agentSentences": agent_sentences, "sentencesCited": sum(1 for c in CLAIMS if c["where"] != "headline"), "itemsCited": len(CITED),
    "claims": len(CLAIMS), "claimsVerified": sum(1 for c in CLAIMS if VERDICTS.get(c["id"], {}).get("supported")),
    "claimsUnsupported": [c["id"] for c in CLAIMS if c["id"] in VERDICTS and not VERDICTS[c["id"]].get("supported")],
    "checkFailuresCaught": sum(len(r["errors"]) for r in log), "checkRunsFailed": len(log),
    "tagsCarried": len(json.load(open("tags/carried.json"))) if os.path.exists("tags/carried.json") else 0,
    "minutes": round((datetime.datetime.now().astimezone() - datetime.datetime.fromisoformat(info["startedAt"])).total_seconds() / 60, 1) if info.get("startedAt") else None,
    "usage": json.load(open("usage.json")) if os.path.exists("usage.json") else None,  # tokens, if the harness reports them
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
m.add_attachment(open("out/evidence.html", "rb").read(), "text", "html", filename="evidence.html")
for name, cid in cids.items():
    m.get_payload()[1].add_related(open(f"out/{name}", "rb").read(), "image", "png", cid=f"<{cid}>", disposition="inline", filename=name)
open("out/email.eml", "wb").write(bytes(m))
print(f"wrote {info['folder']}/out/brief.md, preview.html and email.eml" + (" with the feedback map" if "map.png" in cids else ""))
print(f"preview: {os.path.abspath('out/preview.html')}")
