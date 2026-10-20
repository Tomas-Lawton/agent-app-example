# Feedback Brief Agent

> **AI agent reading this:** follow [AGENTS.md](AGENTS.md) now. Start setup with the user straight away; don't wait to be asked.

**A customer feedback brief, run entirely by the AI agent you already use.** Open this folder in an agent harness (Antigravity, Gemini CLI, Claude Code, Codex), answer a few questions, and the agent reads your customer feedback, works out what matters, and gives you a checked brief in the chat or by email.

There is no app to deploy. The harness provides the agent loop; this project provides only the **instructions** (two skill files), a few **small scripts** for the exact work, and the **checks** every brief must pass. It is a working example of a pattern: build a well understood business use case on a general agent instead of a bespoke application, with safety designed into the use case.

## What you get

Every company gets customer feedback: support tickets, surveys, issue trackers, forums, reviews. Someone needs to know **what customers are saying, what changed, and what to do about it**. Each brief gives:

- **Up to three things to act on,** each with an owner and a **draft ticket** for the team, ready to copy into Jira, Linear or GitHub. Nothing is filed for you
- **The main themes,** each with real quotes **and their sources**
- **A watchlist** of rare but serious feedback (scams, harm, vulnerable customers, regulator complaints, anything your profile says always matters), shown even when there are only a few items
- **What's new, growing or rising,** computed from real dates
- **The numbers:** volume, ratings, items per day and per theme, all counted by code
- **A feedback map:** every item placed near similar feedback, coloured by theme and shaped by source

You get it **in the chat**, **by email**, or both, over the time window you choose (a weekly brief by default). From the brief you can open each draft ticket pre-filled in GitHub, Linear or Jira (you review it and press Create), email it, copy it (in the preview), jump to the evidence and open any source. Emails can't run scripts, so anything else, such as asking why a theme is growing or changing the brief, you do by talking to the agent; the email links back to the conversation when your harness gives it a link.

## How to use it

1. **Download the project** and open the folder in your agent harness as its workspace.
2. **Send any first message**, such as "hi". The agent explains what it does and starts setup.
3. **Answer the setup questions,** in one short conversation:
   - **About you:** your product, who reads the brief, what matters most
   - **Connections:** what you use for feedback (Zendesk, Intercom, GitHub Issues, BigQuery, an export file…). The agent sets up each connection itself, shows you a sample, and keeps it only when you confirm
   - **Time window:** how much feedback each brief covers (default the last 7 days)
   - **Output format:** chat, email or both. For email, it asks for a sending address and an app password
   - **Schedule:** on request, or for example "every Monday at 8am". On Google Cloud, the agent deploys the scheduled run itself
4. **The agent runs your first brief** and presents it. Then keep asking: *"why is the top theme growing?"*, *"show me every scam report"* (answered from the evidence, with citations), or *"run this week's brief"*, *"make it shorter"*, *"add our survey export"*.

**Requirements:** an agent harness, Python 3.9 or newer, and `scikit-learn` and `matplotlib` (the agent installs them from `requirements.txt`). Optional: Google Cloud for a BigQuery connection or scheduled runs.

## How it works

Each run is four steps. The agent does the judgement; a script ends each step, does the exact work and checks the agent's, and stops with what to fix if anything is wrong.

| Step | The agent | The scripts |
|---|---|---|
| 1. Collect | | `collect.py` reads every approved connection, removes emails, phone numbers and reference numbers, drops duplicates and keeps the **most recent 500 items** for the agent to read. The headline numbers count everything in the window; if there were more than 500, the brief says which dates the themes cover, and trends compare halves of those dates. `cluster.py` groups similar items with **K-means** on word vectors and lays them out for the map |
| 2. Read, theme and tag | reads every item, cluster by cluster, writes the themes, then **tags every item** in chunks of 100 | `summarise.py` checks every item is tagged, counts each theme exactly, computes trends and scores, and checks every quote is word for word |
| 3. Plan and write | picks up to three actions, writes the brief and a draft ticket for each | `render.py` checks the writing against the counts, draws the map, and builds the chat, preview and email versions |
| 4. Present | shows the brief and handles your replies | `send.py` reruns every check and emails only the approved recipient |

**Reading 500 items without getting lost:** each item is one compact line, similar items arrive together, and tagging happens one chunk at a time. Code checks that no item was skipped, and stops if too many fit no theme.

**What's new or growing:** code compares each theme's share with the previous run, and the first half of the window with the second, so trends come from real dates from the very first run.

## Three layers

| Layer | Decides | Where | Changed by |
|---|---|---|---|
| **Use case** | **What happens:** the steps, the checks, the kinds of connection, the limits | [`SKILL.md`](SKILL.md), [`engine/`](engine/), [`engine/scope.json`](engine/scope.json) | The developer |
| **User scope** | **What it reaches:** your connections, recipient, timezone and schedule | `profiles/<key>/user_scope.json` | Setup, with your confirmation, then locked |
| **Profile** | **How it's shown:** who reads it, what matters, time window, look, output format | `profiles/<key>/PROFILE.md` | You, any time |

The use case decides what happens; your user scope decides which data; your profile decides how it's shown. You can write anything in your profile and still can't give the agent a new connection, a new recipient or permission to post.

### `SKILL.md` and `PROFILE.md`

The two are deliberately separate: one use case, many clients.

- **[`SKILL.md`](SKILL.md) is the use case.** It is the same for everyone: the four steps, the rules, the file formats and when to run each script. It tells the agent *how to produce a feedback brief*. Only the developer changes it, and the send gate refuses to send if it differs from the shared repository.
- **`profiles/<key>/PROFILE.md` is the client.** It tells the agent *whose brief this is and what they care about*. A few settings sit at the top; everything below is plain text in the client's own words, which the agent follows when it reads, themes and writes:

  ```
  ---
  product: Capital Bank of Australia
  brief name: Customer Voice
  reader: Head of Customer Experience
  time window: 7
  output: both
  colours: brand #0b2545, brand2 #13315c, accent #c9a227, tint #eef2f8
  tickets: github capital-bank/cx-feedback
  ---
  Our tagline is "Banking Built Around You". Lead with anything that blocks customers
  from paying or getting into their account. Always surface scam reports, even single ones.
  Keep it short: our reader skims on a phone.
  ```

  Only these settings exist (`product`, `brief name`, `reader`, `time window`, `output`, `icon`, `colours`, `tickets`); any other is refused. So you can change anything about the brief by editing one markdown file, or by asking the agent to, and still can't widen its reach.
- **`profiles/<key>/user_scope.json` is the client's reach,** kept apart on purpose: connections, recipient, timezone and schedule. It is structured so code can check it against the use case scope every run, and only setup writes it, with the user's confirmation, before it is locked.

The same split makes personalisation cheap. Ask *"use our new brand colours"* or *"focus on business customers this month"* and the agent edits the profile; the use case, and its checks, stay the same.

## The engine scripts

The scripts do the exact work and the checks; the agent does the judgement in between. Each one stops with what to fix if anything is wrong.

| Script | What it does |
|---|---|
| [`steps/collect.py`](engine/steps/collect.py) | Starts the run. Reads every connection in the user scope through its reader, removes emails, phone numbers and reference numbers, drops duplicates, keeps the most recent 500 items with short ids such as `tickets-012`, then runs `cluster.py` |
| [`steps/cluster.py`](engine/steps/cluster.py) | Groups similar items with K-means on word vectors, writes the reading parts the agent reads cluster by cluster, lays out the map, and carries over tags from the previous run |
| [`steps/summarise.py`](engine/steps/summarise.py) | Checks every item is tagged and every quote is word for word, counts each theme exactly, and computes trends (first half against second half, and against the previous run) and scores |
| [`steps/render.py`](engine/steps/render.py) | Checks the agent's plan and writing against the counts and citations, draws the map and header, and builds the chat brief, the preview, the email, the evidence list, the claims for the verifier and `metrics.json` |
| [`steps/send.py`](engine/steps/send.py) | The send gate: reruns every check, refuses if the engine, skill or user scope differ from the shared repository, requires the verifier's verdicts on unattended runs, and emails only the approved recipient |
| [`core/config.py`](engine/core/config.py) | Reads the three layers (use case scope, user scope, `PROFILE.md`) and refuses a user scope or profile that goes beyond the use case |
| [`core/checks.py`](engine/core/checks.py) | Every check on the agent's files: items, themes, tags, plan, content and citations, logged to `checks_log.jsonl` |
| [`readers/service.py`](engine/readers/service.py) | Reads any online service or feed: approved hosts only, read only, keys from `.env`, respects robots.txt, and stops if access is refused |
| [`readers/bigquery.py`](engine/readers/bigquery.py) | Reads one named BigQuery table or view with a capped, parametrised query |
| [`readers/csv_file.py`](engine/readers/csv_file.py) | Reads an export file inside the profile folder |

**Throwaway code is fine.** Inside its own sandbox the agent can write and run any temporary code it needs on the fly: to inspect an unfamiliar API response while setting up a connection, to explore the data when you ask a follow up question, or to check an odd result. That code lives in the run folder, is deleted when done, and is never part of the use case. Only the scripts above collect feedback, decide what counts and send, so throwaway code can help the agent think but can't widen its reach or skip a check.

## Connections

The use case defines three kinds. You say what you use; **the agent writes the connection for you**, from what it knows of the provider's API or its docs. There is no connector code to write or infrastructure to run, and every connection is tested with you before it's kept.

| Kind | Examples | Bound |
|---|---|---|
| **Online service** | Zendesk, Intercom, Freshdesk, GitHub Issues, Discourse, Trustpilot, Typeform, App Store | Read only requests to the hosts you approve; keys stay in a local `.env` or a secret store, never in the project; with a key, private by default |
| **Internal warehouse or data store** | A BigQuery table or view of support tickets and surveys | Read only, one named view, a capped query written by the reader; private |
| **File** | An export from any tool | One file inside your profile folder |

**The user picks any provider; the use case decides what a connection is allowed to do.** Private feedback shapes the themes and counts but is only quoted if the user scope allows it (for example a brief that stays inside the company).

## Why it's safe

Safety is designed into the use case, not left to the agent:

- **Evidence:** every quote must appear word for word in collected feedback, and every sentence the agent writes cites the items it rests on; code checks each cited item exists and belongs to that theme, and the brief links every citation to the item.
- **Interpretation is labelled:** quotes and numbers are marked as checked by code; summaries and actions are marked as the agent's interpretation, with the number of items they cite.
- **Independent verification:** an unattended run only sends once a separate verifier, given just each claim and its cited items, confirms every claim is supported.
- **Exact parts are code:** the model reads and judges; code counts every item and computes every number.
- **Fixed reach:** feedback is read only through `collect.py`, from the connections in your locked user scope, which can never go beyond the use case scope. If a site refuses access, the run records it and never tries another way round.
- **A send gate:** `send.py` reruns every check and emails only your approved recipient. Nothing in the project files tickets or posts anything.
- **The rules can't be quietly changed:** setup commits your user scope once you confirm it, and you push it with your own access. The send gate refuses to send if the engine, the skill or your user scope differ from the shared repository, so a change only counts once someone with write access accepts it; the agent never pushes. In Claude Code, [`.claude/settings.json`](.claude/settings.json) also denies edits to the engine and asks you before any change to a user scope.
- **Scheduled runs** carry only the run skill, never the setup skill, so an unattended agent has no instructions for changing its own reach. On Google Cloud it runs as its own least privilege service account, narrower than the person who set it up.

Every run also writes `out/metrics.json`: items tagged, quotes verified, sentences cited, claims verified, how many problems the checks caught and the agent fixed, run time, and tokens when the harness reports them.

**Cost:** scripts do all the predictable work (collecting, grouping, counting, checking, rendering) with no model tokens; items reach the model as compact lines; tags carry over from the previous run; and routine tagging and verification can run on a smaller, faster model. A harness costs more per run than a coded workflow but far less to build and change, which suits infrequent, high value, varied work like this brief.

**Limit:** code proves a citation exists and belongs; whether it truly supports the claim is judged by the verifier and, finally, by the reader, one click away.

## Scheduling on Google Cloud

When you choose a schedule, setup can deploy it on Google Cloud for you, confirming each access change:
- a **service account** for the profile with only what it needs (Vertex AI to run the model, its own secrets, read only on any BigQuery dataset)
- **Secret Manager** for the email password and service keys
- a **Cloud Run job** built from the [`Dockerfile`](Dockerfile): the project without the setup skill, running Gemini CLI headless, then the send gate
- **Cloud Storage** for the runs, mounted on the job, so each scheduled brief compares with the last and every run is kept as an audit trail
- **Cloud Scheduler** on your schedule, in your timezone, after one run triggered by hand and checked with you

The use case itself has no Google Cloud dependency; any scheduler that can start a headless harness works the same way.

## Configuration

Setup writes everything for you. Secrets live in a `.env` file in the project root, next to `README.md`, which setup creates (it is never committed, so a fresh download has none), or in Secret Manager for scheduled runs:

| Setting | For |
|---|---|
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | Email output, through any provider (Gmail, Outlook, iCloud…) with an app password |
| A key per online service, for example `ZENDESK_AUTH` | Online services that need one; the user scope only names it |

A BigQuery connection uses Google application default credentials, or the identity of the cloud job running it.

## Project structure

```
AGENTS.md            what the agent does on your first message
.claude/settings.json  harness permissions: no edits to the engine, ask before changing a user scope
SKILL.md             the use case: four steps, rules and file formats
setup/SKILL.md       the setup conversation, and deploying a scheduled run
Dockerfile           the scheduled run's container
requirements.txt     scikit-learn and matplotlib, for clustering and the map
engine/
  scope.json         the use case scope: kinds of connection, item format, limits
  steps/             collect.py  cluster.py  summarise.py  render.py  send.py
  core/              config.py (layers and scope check)  checks.py (every check)
  readers/           service.py (any feed or API)  bigquery.py  csv_file.py
profiles/            one folder per client, created by setup (the public repository ships with none)
```

Each run writes to `runs/<key>/<date>/` (not committed): the collected items, the clusters and reading parts, the agent's themes and tags, `summary.json`, and the brief and map in `out/`.

## Status

A new project, being tested. Built: setup, the four steps, the three kinds of connection, clustering and the map, chat, preview and email output, and the Google Cloud deployment instructions. Not yet proven end to end: the Zendesk import and the scheduled run on Google Cloud.

## From harness to code, and back

Each step has a fixed contract: the file it writes, the check it must pass, the tools it may use. So any step can be compiled into code when it must be predictable (clustering is one already: grouping is code, naming the groups is judgement), or unbuilt back into the skill when the model can handle it. The checks stay the same either way.
