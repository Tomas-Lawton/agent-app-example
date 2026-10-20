# Feedback Brief Agent

> **AI agent reading this:** follow [AGENTS.md](AGENTS.md) now. Start setup with the user straight away; don't wait to be asked.

**A weekly customer feedback brief, run entirely by the AI agent you already use.** Open this folder in an agent harness (Antigravity, Gemini CLI, Claude Code, Codex), answer a few questions, and the agent reads your customer feedback, works out what matters, and sends you a checked brief in the chat and by email.

There is no app to deploy. The harness runs the agent; this project provides the **instructions** (two skill files), a few **small scripts** for the exact work, and the **checks** every brief must pass. It is an example of a pattern: a well-understood business use case built on a general agent instead of a bespoke application, with safety designed in.

## What you get

- **Up to three things to act on**, each with an owner and a draft ticket you can open pre-filled in GitHub, Linear or Jira (nothing is filed for you)
- **The main themes**, with real quotes and sources, when each started and peaked, and who is affected
- **What's working**: what customers praise
- **A watchlist** of rare but serious feedback, such as scams or vulnerable customers
- **The numbers and charts**: volume, ratings, trends and a map of similar feedback, all counted by code
- **Follow-up questions** you can ask the agent, answered from the evidence with citations

## How to use it

1. **Download the project** and open the folder in your agent harness.
2. **Say "Use the setup skill".** The agent asks a few questions, one at a time: about you, where your feedback lives (Zendesk, BigQuery, an export file…), the time window, email details, the look, and an optional schedule. It sets up each connection itself and shows you a sample before keeping it.
3. **The agent runs your first brief** and sends it. Then keep asking: *"why is the top theme growing?"*, *"make it shorter"*, *"add our survey export"*, *"run this week's brief"*.

**Requirements:** an agent harness and Python 3.9 or newer. The agent installs the rest (`requirements.txt`) in the project's own `.venv`. Optional: Google Cloud for BigQuery or scheduled runs.

## How it works

Each run is four steps. The agent does the judgement; a script ends each step, does the exact work, checks the agent's work, and stops with what to fix if anything is wrong.

| Step | The agent | The scripts |
|---|---|---|
| 1. Collect | | `collect.py` reads your connections, removes personal details, and keeps the newest 500 items; `cluster.py` groups similar items (TF-IDF, LSA and K-means) |
| 2. Theme and tag | reads every item, writes the themes, tags every item | `summarise.py` checks every item is tagged, counts each theme, computes trends |
| 3. Write | picks the actions, writes the brief with citations | `render.py` checks every quote, number and citation, and builds the brief, preview and email |
| 4. Send | presents the brief, answers follow-ups | `send.py` reruns every check and emails only your approved recipient |

## The use case and the client

- **[`SKILL.md`](SKILL.md) is the use case**, the same for everyone: how to produce a feedback brief, its steps, rules and checks. Only the developer changes it.
- **`profiles/<key>/PROFILE.md` is the client**: a few settings, then plain text in their own words that the agent follows. Change it any time, or ask the agent to.

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
  Lead with anything that stops customers paying or logging in. Always surface scam reports.
  ```
- **`profiles/<key>/user_scope.json` is the client's reach**: connections, recipient and schedule. Only setup writes it, with your confirmation, and every run checks it against the use case's limits ([`engine/scope.json`](engine/scope.json)). A profile can change how the brief looks, never what it can reach. Optional images (logo, header background) go in `profiles/<key>/assets/`.

## The engine

| Script | What it does |
|---|---|
| [`steps/collect.py`](engine/steps/collect.py) | Reads every connection in the user scope, removes personal details and duplicates, keeps the newest 500 items |
| [`steps/cluster.py`](engine/steps/cluster.py) | Groups similar items for reading and lays out the map |
| [`steps/summarise.py`](engine/steps/summarise.py) | Checks tagging and quotes, counts themes, computes trends and scores |
| [`steps/render.py`](engine/steps/render.py) | Checks the writing and builds the brief, preview, email and charts |
| [`steps/send.py`](engine/steps/send.py) | The send gate: reruns every check and emails only the approved recipient |
| [`core/config.py`](engine/core/config.py) | Reads the use case scope, user scope and profile, and refuses anything beyond the use case |
| [`core/checks.py`](engine/core/checks.py) | Every check on the agent's files |
| [`readers/`](engine/readers/) | One read-only reader each for an online service, a BigQuery table, and a file |

The agent can also write throwaway code in its sandbox, for example to explore an unfamiliar API or answer a follow-up. Only the scripts above collect feedback and send, so throwaway code can't widen its reach or skip a check.

## Why it's safe

- **Every claim is checked:** quotes must appear word for word, every number comes from code, and every sentence cites the items it rests on. Unattended runs also need an independent verifier to confirm each claim.
- **Reach is fixed:** feedback is read only through `collect.py`, from read-only connections in your user scope, which can never go beyond the use case. If a site refuses access, the run stops there.
- **One way out:** only `send.py` sends, and only to your approved recipient. Nothing files tickets or posts anything.
- **Setup is separate from running:** only setup changes reach, with your confirmation. Scheduled runs carry no setup skill, run in a read-only container, and use a least-privilege account.

## Scheduling on Google Cloud

When you choose a schedule, setup deploys it for you, confirming each access change: a service account, Secret Manager for keys, a Cloud Run job from the [`Dockerfile`](Dockerfile), a Cloud Storage bucket for the runs, and Cloud Scheduler. Any scheduler that can start a headless harness works the same way.

## Configuration

Setup writes everything. Secrets live in `.env` in the project root (never committed), or in Secret Manager for scheduled runs:

| Setting | For |
|---|---|
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` | Email, through any provider with an app password |
| A key per online service, for example `ZENDESK_AUTH` | Services that need one |

BigQuery uses your Google credentials, or the cloud job's identity.

## Project structure

```
AGENTS.md          what the agent does when the folder is opened
SKILL.md           the use case: steps, rules and file formats
setup/SKILL.md     the setup conversation, and deploying a scheduled run
Dockerfile         the scheduled run's container
requirements.txt   scikit-learn and matplotlib
engine/            scope.json, steps/, core/, readers/
profiles/          one folder per client, created by setup
```

Each run writes to `runs/<key>/<date>/` (not committed).
