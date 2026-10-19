---
name: feedback-brief
description: Runs a customer feedback brief for a profile in profiles/<key>/ - what customers said, what changed and what to do about it - in four checked steps. Use when asked to run a feedback brief, review customer feedback, or "run the demo" (the demo profile). To create or change a profile, its connections, time window, output format or schedule, use setup/SKILL.md.
---

# Feedback Brief skill

**Layers.** The use case (this skill, `engine/`, `engine/scope.json`) decides what happens. The user scope (`profiles/<key>/user_scope.json`, locked) holds the user's connections, recipient and schedule. The profile (`PROFILE.md`, and `profile.json` from it) holds focus, look, time window and output format. Read `PROFILE.md` first. Never edit `engine/`, `scope.json` or `user_scope.json` during a run.

**Rules.** Collect only through `collect.py`: no web search or other sources, and if a connection is blocked, report it and never try another way round. Quote word for word; never quote private items (warehouse data, items marked private) unless the user scope sets `privateQuotes`. Take every number from `summary.json`. Never file or post anything: tickets are drafts for a person. Say when evidence is thin or the period was quiet. When a script stops, fix what it names and run it again.

## Before the first run
Check the tools once per machine, and install anything missing yourself:
- **Python 3.9 or newer:** `python3 --version`.
- **The packages in `requirements.txt`** (scikit-learn and matplotlib, for clustering and the map): `python3 -c "import sklearn, matplotlib"`. If that fails, run `python3 -m pip install -r requirements.txt`. If pip refuses because the system Python is managed, make a virtual environment in the project root, `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`, and use `.venv/bin/python3` instead of `python3` in every command below.
- Everything else is the Python standard library. A warehouse connection also needs Google credentials, which setup arranges.

## Steps
Run every command from the repository root. Write your files in the run folder that step 1 prints. For the demo, first run `python3 demo/make_data.py` to refresh its data.

**1. Collect.** `python3 engine/steps/collect.py <key>`. It reads the user's connections (the most recent 500 items in the window), groups similar items, and writes `reading/part_NN.txt`: every item, cluster by cluster, one line each (`id | date | rating | text`).

**2. Read, theme and tag.**
- Read **every** part in `reading/`, in order. Items arrive grouped with similar items, so form themes cluster by cluster; a theme can span clusters, and a cluster can hold more than one theme.
- Write `themes.json`: 4 to 8 specific themes ("Cards declined by the new fraud rules since Thursday", not "Card issues"). Reuse last run's `id` for the same theme (`run.json` → `previous`). `impact` 0 to 3 (3 stops people using or paying); `actionability` 0 to 2 (2 a team could start this week). At least two word-for-word quotes per theme.
- Then tag **every** item: for each `reading/part_NN.txt`, write `tags/part_NN.json` mapping each item id to its theme ids (`[]` if none fits). Do one part at a time.
- Run `python3 engine/steps/summarise.py <key>`. Code checks every item is tagged, counts each theme exactly, computes trends from the items' dates and the previous run, and scores the themes. Keep a theme at 4 or more. If too many items fit no theme, it stops: add or widen a theme and retag.
```json
{"themes": [{"id": "cards-declined", "title": "Cards declined by the new fraud rules since Thursday", "kind": "problem",
  "summary": "Two or three sentences in your words: what, since when, anything that narrows it.",
  "evidence": [{"item": "tickets-012", "quote": "copied word for word, at least four words"}],
  "scores": {"impact": 3, "actionability": 2}, "decision": "keep", "reason": "one sentence"}]}
```
`kind` is problem, request, praise or question. Quotes must come from items tagged with the theme.

**3. Plan and write.** Write `brief_plan.json` and `live_content.json`, then run `python3 engine/steps/render.py <key>`.
- Up to three actions, on themes scoring 6 or more, most important first, owned by roles. Praise is never an action. If nothing material changed, set `quietWeek: true` and say so.
- Each action has a **draft ticket** for the owning team: a clear title, and a body with what's happening, the evidence (counts from `summary.json`, a short quote), and what to check first. Never file it.
- Copy `dateLabel` and `windowLabel` from `run.json`; start `subject` with the brief's name; quotes come from the theme's `evidence`; numbers only from `summary.json`. No links in prose (render adds sources, links and buttons).
```json
{"headline": "Most important thing first, then what's next.", "quietWeek": false,
 "actions": [{"theme": "cards-declined", "action": "Review the new fraud rule thresholds", "owner": "Head of card fraud operations", "why": "Customers can't pay."}],
 "themes": ["cards-declined", "login-lockouts"]}
```
```json
{"meta": {"dateLabel": "...", "windowLabel": "..."}, "subject": "Weekly Feedback Brief: ...", "preheader": "One sentence.", "headline": "...",
 "actions": [{"theme": "cards-declined", "title": "Reduce false fraud declines", "detail": "One or two sentences.", "owner": "...",
   "ticket": {"title": "False declines on everyday card purchases since Thursday", "body": "What is happening, the evidence, what to check first."}}],
 "themes": [{"id": "cards-declined", "title": "...", "summary": "...", "quotes": [{"item": "tickets-012", "text": "..."}]}],
 "footer": "Anything the reader should know about the evidence: a blocked connection, a capped or partly covered window."}
```

**4. Present.** Follow `profile.json` → `delivery`. **chat:** show `out/brief.md` in the chat and offer `out/preview.html`. **email:** run `python3 engine/steps/send.py <key>` and give a short summary. **both:** both. A scheduled run stops after step 3; the job runs the send gate itself. Finish in five lines or fewer: connections read or blocked, the actions, gaps in the evidence.
