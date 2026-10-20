# Feedback Brief Agent

> **AI agent reading this:** follow [AGENTS.md](AGENTS.md) now. Start setup with the user straight away; don't wait to be asked.

**A customer feedback brief, run entirely by the AI agent you already use.** Open this folder in an agent harness (Antigravity, Gemini CLI, Claude Code, Codex), answer a few questions, and the agent reads your customer feedback, works out what matters, and gives you a checked brief in the chat or by email.

There is no app to deploy. The harness provides the agent loop; this project provides only the **instructions** (two skill files), a few **small scripts** for the exact work, and the **checks** every brief must pass. It is a working example of a pattern: build a well understood business use case on a general agent instead of a bespoke application, with safety designed into the use case.

## What you get

Every company gets customer feedback: support tickets, surveys, issue trackers, forums, reviews. Someone needs to know **what customers are saying, what changed, and what to do about it**. Each brief gives:

- **Up to three things to act on,** each with an owner and a **draft ticket** for the team, ready to copy into Jira, Linear or GitHub. Nothing is filed for you
- **The main themes,** each with real quotes **and their sources**
- **What's new, growing or rising,** computed from real dates
- **The numbers:** volume, ratings, items per day and per theme, all counted by code
- **A feedback map:** every item placed near similar feedback, coloured by theme and shaped by source

You get it **in the chat**, **by email**, or both, over the time window you choose (a weekly brief by default). From the brief you can email an action's owner, copy its ticket, jump to the evidence and open any source. Anything else, such as filing a ticket, asking why a theme is growing or changing the brief, you do by talking to the agent.

## How to use it

1. **Download the project** and open the folder in your agent harness as its workspace.
2. **Send any first message**, such as "hi". The agent explains what it does and starts setup. Say **demo** to see a brief for Capital Bank of Australia, a fictional bank, first.
3. **Answer the setup questions,** in one short conversation:
   - **About you:** your product, who reads the brief, what matters most
   - **Connections:** what you use for feedback (Zendesk, Intercom, GitHub Issues, BigQuery, an export file…). The agent sets up each connection itself, shows you a sample, and keeps it only when you confirm
   - **Time window:** how much feedback each brief covers (default the last 7 days)
   - **Output format:** chat, email or both. For email, it asks for a sending address and an app password
   - **Schedule:** on request, or for example "every Monday at 8am". On Google Cloud, the agent deploys the scheduled run itself
4. **The agent runs your first brief** and presents it. After that, just ask: *"run this week's brief"*, *"make it shorter"*, *"add our survey export"*.

**Requirements:** an agent harness, Python 3.9 or newer, and `scikit-learn` and `matplotlib` (the agent installs them from `requirements.txt`). Optional: Google Cloud for a BigQuery connection or scheduled runs.

## How it works

Each run is four steps. The agent does the judgement; a script ends each step, does the exact work and checks the agent's, and stops with what to fix if anything is wrong.

| Step | The agent | The scripts |
|---|---|---|
| 1. Collect | | `collect.py` reads every approved connection, removes emails, phone numbers and reference numbers, drops duplicates and keeps the **most recent 500 items**. `cluster.py` groups similar items with **K-means** on word vectors and lays them out for the map |
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

Every run also writes `out/metrics.json`: items tagged, quotes verified, sentences cited, claims verified, and how many problems the checks caught and the agent fixed.

**Limit:** code proves a citation exists and belongs; whether it truly supports the claim is judged by the verifier and, finally, by the reader, one click away.

## The demo

The `demo` profile is **Capital Bank of Australia**, a fictional bank, with about 500 generated pieces of feedback from two different sources that tell one story (cards declined after a fraud rule change, lockouts after an app update, delayed transfers, unexpected fees, a handful of scam reports that must not be missed, and praise for the app):
- **Support tickets** and **in-app survey comments**, as files, so the demo runs anywhere: run [`demo/make_data.py`](demo/make_data.py) to date them in the current week.
- For a **live test with real connections**, the same data loads into a real **Zendesk** account ([`demo/load_zendesk.py`](demo/load_zendesk.py)) and a real **BigQuery** table ([`demo/load_warehouse.py`](demo/load_warehouse.py)), and setup connects to them like any company's systems.

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
profiles/demo/       the Capital Bank of Australia demo profile
demo/                its data generator, and loaders that put the same data into Zendesk and BigQuery
```

Each run writes to `runs/<key>/<date>/` (not committed): the collected items, the clusters and reading parts, the agent's themes and tags, `summary.json`, and the brief and map in `out/`.

## Status

A new project, being tested. Built: setup, the four steps, the three kinds of connection, clustering and the map, chat, preview and email output, and the Google Cloud deployment instructions. Not yet proven end to end: the Zendesk import and the scheduled run on Google Cloud.

## From harness to code, and back

Each step has a fixed contract: the file it writes, the check it must pass, the tools it may use. So any step can be compiled into code when it must be predictable (clustering is one already: grouping is code, naming the groups is judgement), or unbuilt back into the skill when the model can handle it. The checks stay the same either way.
