---
name: feedback-brief
description: Runs a customer feedback brief for a profile in profiles/<key>/ - what customers said, what changed and what to do about it - in four checked steps. Use when asked to run a feedback brief or review customer feedback. To create or change a profile, its connections, time window, output format or schedule, use setup/SKILL.md.
---

# Feedback Brief skill

**Layers.** The use case (this skill, `engine/`, `engine/scope.json`) decides what happens, the same for every client. The user scope (`profiles/<key>/user_scope.json`, written only by setup and locked) holds this client's connections, recipient and schedule. The profile (`profiles/<key>/PROFILE.md`) holds a few settings at the top (name, colours, time window, output) and then free text in the client's words: who reads it, what matters, tone, standing instructions. Read `PROFILE.md` first and follow it within those limits. Never edit `engine/`, `scope.json` or `user_scope.json` during a run: the send gate compares them with the approved version and refuses to send if they differ.

**Rules.** Collect only through `collect.py`: no web search or other sources, and if a connection is blocked, report it and never try another way round. Quote word for word; never quote private items (warehouse data, items marked private) unless the user scope sets `privateQuotes`. Take every number from `summary.json`. Never file or post anything: tickets are drafts for a person. **Send email only by running `send.py`**: never write your own email code, use another mail tool, attach files or convert the brief to a PDF. The email body is the brief itself. If `send.py` blocks, tell the user its reason and what would fix it, and stop. Say when evidence is thin or the period was quiet. When a script stops, fix what it names and run it again.

## Before the first run
Check the tools once per machine, and install anything missing yourself:
- **Python 3.9 or newer:** `python3 --version`.
- **The packages in `requirements.txt`** (scikit-learn and matplotlib, for clustering and the map): `python3 -c "import sklearn, matplotlib"`. If that fails, run `python3 -m pip install -r requirements.txt`. If pip refuses because the system Python is managed, make a virtual environment in the project root, `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`, and use `.venv/bin/python3` instead of `python3` in every command below.
- Everything else is the Python standard library. A warehouse connection also needs Google credentials, which setup arranges.

## Steps
Run every command from the repository root. When you need anything the scripts don't do, such as a count for a follow-up question or reading an odd file, write a small throwaway program in the run folder, run it, and delete it; never add it to `engine/`. Write your files in the run folder that step 1 prints.

**1. Collect.** `python3 engine/steps/collect.py <key>`. It reads the user's connections (the most recent 500 items in the window for you to read; if there were more, `summary.json` → `coverage` says which dates the 500 cover, the headline numbers still count everything, and the brief says so), groups similar items, and writes `reading/part_NN.txt`: every item, cluster by cluster, one line each (`id | date | rating | text`).

**2. Read, theme and tag.**
- Read **every** part in `reading/`, in order. Items arrive grouped with similar items, so form themes cluster by cluster; a theme can span clusters, and a cluster can hold more than one theme.
- Write `themes.json`: 4 to 8 specific themes ("Cards declined by the new fraud rules since Thursday", not "Card issues"). Reuse last run's `id` for the same theme (`run.json` → `previous`). `impact` 0 to 3 (3 stops people using or paying); `actionability` 0 to 2 (2 a team could start this week). At least two word-for-word quotes per theme, and three or more where the theme allows, so the brief can show three.
- Then tag **every** item: for each `reading/part_NN.txt`, write `tags/part_NN.json` mapping each item id to its theme ids (`[]` if none fits). Do one part at a time. Items marked `tagged last run` already carry those tags (`tags/carried.json`); you only need to tag them again if their theme was renamed or dropped.
- **Keep it efficient.** If you can start sub-agents, give each reading part to one on a smaller, faster model with little or no extended thinking, with `themes.json` and that part only; tagging is routine. Keep finding themes, planning and writing on your main model.
- Run `python3 engine/steps/summarise.py <key>`. Code checks every item is tagged, counts each theme exactly, computes trends from the items' dates and the previous run, and scores the themes. Keep a theme at 4 or more. If too many items fit no theme, it stops: add or widen a theme and retag.
- **Watchlist: rare but serious.** Some feedback matters even when there is very little of it: anything `PROFILE.md` says always matters, and anything suggesting fraud or scams, harm or safety risks, a vulnerable customer, exposed personal data, or a complaint to a regulator, ombudsman or lawyer. Judge this by reading, never by keywords. Give such items their own theme, tag them, and if it scores below 4, set `"decision": "watch"` instead of dropping it (impact 2 or 3, at least one quote, up to 3 watched themes). Watched themes are always shown, on the brief's watchlist.
```json
{"themes": [{"id": "cards-declined", "title": "Cards declined by the new fraud rules since Thursday", "kind": "problem",
  "summary": "Two or three sentences in your words: what, since when, anything that narrows it.",
  "evidence": [{"item": "tickets-012", "quote": "copied word for word, at least four words"}],
  "scores": {"impact": 3, "actionability": 2}, "decision": "keep", "reason": "one sentence"}]}
```
`kind` is problem, request, praise or question. `decision` is keep, watch or drop. Quotes must come from items tagged with the theme.

**3. Plan and write.** Write `brief_plan.json` and `live_content.json`, then run `python3 engine/steps/render.py <key>`.
- Up to three actions, on themes scoring 6 or more, most important first, owned by roles. Praise is never an action. If nothing material changed, set `quietWeek: true` and say so.
- Each action has a **draft ticket** for the owning team: a clear title, and a body with what's happening, the evidence (counts from `summary.json`, a short quote), and what to check first. Never file it.
- **Watchlist:** list every watched theme in the plan's `watch`, and for each write a title, one or two cited sentences on why it matters (`why`), and one or two of its quotes.
- **Quotes:** show three per theme (fewer only if the theme has fewer checked quotes). The theme summary cites the quoted items along with the others it rests on.
- **Cite as you write.** End every sentence in a theme summary, action detail and ticket body with the items it rests on, like `[tickets-012, survey-087]`, using items tagged with that theme. Code checks every sentence has citations and every cited item exists and belongs; the brief links each citation to the item.
- Copy `dateLabel` and `windowLabel` from `run.json`; start `subject` with the brief's name; quotes come from the theme's `evidence`; numbers only from `summary.json`. No links in prose (render adds sources, links and citations).
- **Verify** (required for scheduled runs, recommended before any email): `render.py` writes `out/claims.json`, every cited sentence with the text of its items. Give **only that file** to a fresh sub-agent, which can use a smaller model (or, without sub-agents, judge it yourself without looking back at your own notes) and have it write `verdicts.json`: `{"<claim id>": {"supported": true or false, "note": "why"}}`, supported only if the cited items clearly say what the claim says. Rewrite or re-cite any unsupported claim and render again. The brief then marks verified claims, and an unattended send refuses unless every claim is supported.
```json
{"headline": "Most important thing first, then what's next.", "quietWeek": false,
 "actions": [{"theme": "cards-declined", "action": "Review the new fraud rule thresholds", "owner": "Head of card fraud operations", "why": "Customers can't pay."}],
 "themes": ["cards-declined", "login-lockouts"], "watch": ["scam-calls"]}
```
```json
{"meta": {"dateLabel": "...", "windowLabel": "..."}, "subject": "Weekly Feedback Brief: ...", "preheader": "One sentence.", "headline": "...",
 "actions": [{"theme": "cards-declined", "title": "Reduce false fraud declines", "detail": "One or two sentences, each cited [tickets-012].", "owner": "...",
   "ticket": {"title": "False declines on everyday card purchases since Thursday", "body": "What is happening [tickets-012, survey-087]. What to check first [tickets-031]."}}],
 "themes": [{"id": "cards-declined", "title": "...", "summary": "Each sentence ends with its citations [tickets-012, tickets-019].", "quotes": [{"item": "tickets-012", "text": "..."}]}],
 "watch": [{"id": "scam-calls", "title": "...", "why": "Why it matters, cited [tickets-044].", "quotes": [{"item": "tickets-044", "text": "..."}]}],
 "footer": "Anything the reader should know about the evidence: a blocked connection, a partly covered window."}
```

**4. Present.** Follow the `output` setting in `PROFILE.md`. **chat:** show `out/brief.md` in the chat and offer `out/preview.html`. **email:** run `python3 engine/steps/send.py <key>` and give a short summary. If it prints BLOCKED or NOT SET UP, report that and stop; there is no other way to send. **both:** both. A scheduled run stops after step 3; the job runs the send gate itself. Finish in five lines or fewer: connections read or blocked, the actions, gaps in the evidence. If your harness reports token usage, write it to `usage.json` in the run folder (`{"inputTokens": 0, "outputTokens": 0}`) and render again, so `metrics.json` records the cost.

## After the brief: follow-up questions
The reader can keep asking: *"why is the declines theme growing?"*, *"show me every scam report"*, *"compare with last month"*. Answer from this run's evidence only: `items.json`, `themes.json`, the tags and `summary.json`, and earlier runs' `summary.json` in `runs/<key>/` for comparisons. Never collect from anywhere else. Follow the same rules as the brief: quote word for word, cite every claim with item ids, take numbers from code (run a short Python count over `items.json` and the tags, never estimate), and say when the evidence doesn't answer the question. A different period is a new run.

If they ask to change their reach in the chat, such as *"add our Intercom too"*, *"send it to Sam instead"* or *"run it every Monday"*, switch to [setup/SKILL.md](setup/SKILL.md) for that one change: set it up and test it, show a sample, and only when the user confirms, update `user_scope.json` and commit it (never push). Then rerun the brief so they see the change straight away. Tell them that email and scheduled sends wait until they push the commit, because the send gate refuses a user scope that differs from the shared repository. Anything outside `engine/scope.json`, such as posting to another tool or a write connection, is a change to the use case, not the user scope: say so and don't attempt it.
