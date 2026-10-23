---
name: customer-pulse-setup
description: Sets up or changes a Customer Pulse in one short conversation - the user's connections (online service, internal warehouse or data store, file), time window, output format (chat, email or both) and schedule - writing the user scope (with the user's confirmation) and the profile, deploying a scheduled run on Google Cloud if wanted, then runs the first pulse. Use when the user says "Use the setup skill", or at the start of a conversation when no user profile exists (even a plain "hi"), or to change a profile, a connection, the recipient, email or the schedule.
---

# Customer Pulse setup skill

Setup decides **what the agent does** (connections, recipient, schedule: the user scope, `profiles/<key>/user_scope.json`) and **how the pulse is presented** (focus, look, output format: the profile, `profiles/<key>/PROFILE.md`). It is the only time the user scope changes, and every change needs the user's confirmation. The user scope can only narrow the use case scope (`engine/scope.json`); `collect.py` refuses anything outside it.

The user is not technical. Never ask them to run commands or edit files; install what's missing yourself (see **Work in the sandbox** below); ask only for what you can't know.

**Ask every question below, one per message, in order.** After each answer, ask the next question in your very next message; don't start building the profile until all six have been answered. Never skip a question because it has a default: ask it and offer the default, so the user can just say "yes". Only skip a question the user has already answered explicitly. Keep each message to a line or two, and don't repeat back everything after each answer. When all six are answered, summarise once and ask the user to confirm before you save anything.

## Work in the sandbox
Keep everything inside the project folder and your harness's sandbox, so nothing on the user's machine changes and nothing clashes with what is already installed:
- **One virtual environment, in the project:** `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`, then run every script with `.venv/bin/python3` (on Windows `.venv\Scripts\python`). If `python3 -m venv` fails because `ensurepip` is missing, use uv instead: `uv venv .venv && uv pip install --python .venv/bin/python3 -r requirements.txt` (install uv first if needed, into the user's own tools, not system-wide). Never install packages system-wide, never use `sudo`, and don't change the user's global Python, shell profile or settings.
- **Files stay in the project:** profiles in `profiles/`, secrets in `.env`, runs in `runs/`, throwaway code in the run folder. Nothing goes in the user's home folder or anywhere else.
- **Keep the harness's sandbox on.** If it blocks something the pulse needs (usually network access to an approved connection), tell the user what and why, and let them allow it; never switch the sandbox off or find a way round it.
- Only Google Cloud sign-in (`gcloud`), for a warehouse connection or a scheduled run, lives outside the project; ask before using it. If application default credentials fail to refresh ("Reauthentication failed"), ask the user to run `gcloud auth login` themselves (on the machine you run on; `--no-launch-browser` gives a link and a code when it's remote), then pass the token to the run for that session only: `GOOGLE_OAUTH_ACCESS_TOKEN=$(gcloud auth print-access-token) .venv/bin/python3 engine/steps/collect.py <key>`. Never write the token to a file.

## The questions, one at a time
1. **About you:** the product or company, and who reads the pulse. Then, if not already clear, their city (for the timezone) and what matters most, as a short follow up.
2. **Connections.** Ask what they use for customer feedback, and show the common providers below as examples; they can name any other. Every answer fits one of three kinds (`scope.json` → `connectionTypes`): an **online service**, an **internal warehouse or data store**, or a **file**.
   > Helpdesks: Zendesk, Intercom, Freshdesk, Jira Service Management, HubSpot · Issue trackers: GitHub Issues · Surveys and reviews: Typeform, SurveyMonkey, Trustpilot, Canny · Your warehouse: BigQuery · Or any export file
3. **Time window:** how much feedback each pulse covers (default the last 7 days, a weekly pulse; up to 31).
4. **Output format:** both, in the chat and by email, is the default: offer it and ask for the email details (see Email below). Chat only or email only if they prefer.
5. **Schedule:** on request, or automatically (for example "every Monday at 8am").
6. **Look** (optional): the pulse's name and colours, and two optional images that make it look like theirs: a **logo** (square, PNG or JPG, at least 128×128) shown in the header, and a **header background** (wide, about 1280×320, PNG or JPG), tinted with their brand colour so the text stays readable. Without them the header is a plain gradient in their colours. Save what they give you as `profiles/<key>/assets/logo.png` and `profiles/<key>/assets/header.png` (or `.jpg`); offer to move files they point you to. They can add or change these any time.

The user names their tools; you work out the connection. Never offer write access or posting: every connection is read only. If a service can't be read within these rules (no key, a read only bearer key or an OAuth client), explain why and offer a file export.

## Then
1. Create `profiles/<key>/` (a short lowercase key, for example `capital-bank`) with two files, written from the user's answers:
   - **`PROFILE.md`**, everything the user can change freely: a few settings at the top, then free text in their own words. Only these settings exist; anything else is refused:
     ```
     ---
     product: Capital Bank of Australia
     title: Weekly Customer Pulse
     reader: Priya Raman, General Manager, Customer Experience
     time window: 7 days
     output: both
     colours: brand #0b2545, brand2 #13315c, accent #c9a227
     ---
     **Who it's for.** ... **What matters.** ... **Tone.** ... **Standing instructions.** ...
     ```
     `output` is exactly `chat`, `email` or `both`, from question 4 (`both` unless they chose otherwise; it is also the default when the setting is missing). Write each value on its own, with no notes after it. Write the free text in the user's words: who reads it, what matters, what is urgent, what to keep apart, how to route tickets, the tone. Never invent facts about the company.
   - **`user_scope.json`**, what the pulse may reach, which only setup writes (see the next step). It is a separate file on purpose: a profile can change how the pulse looks, never what it can reach.
2. **If any connection is private** (a warehouse, a keyed service, a private file), ask one more question: *"The pulse will quote that feedback word for word, which is usual when it stays inside the company. Is that OK?"* Yes is the default (`"privateQuotes": true`); if they say no, set it to false, and themes are described and cited but not quoted.
   Write `user_scope.json`: `{"timezone": "Australia/Sydney", "recipients": ["reader@company.com"], "sources": [...], "privateQuotes": true, "schedule": null}`, with each connection below in `sources`. Test each one by running `python3 engine/steps/collect.py <key>` and showing the user a few items from `items.json`; keep it only when they confirm.
3. Set up email and the schedule if chosen (below), read back the connections, recipient and schedule, and ask the user to confirm. Their confirmation is the approval: from then on every run checks the user scope against the use case scope and refuses anything outside it, and only setup changes it. No git step is needed. (A team that keeps profiles in a shared repository can commit the profile and review it there; the agent never pushes.)
4. Run the first pulse with [SKILL.md](../SKILL.md) and present it in the chosen format. **If `output` is `email` or `both`, the pulse must also be emailed:** run `python3 engine/steps/send.py <key>` and tell them it was sent, or show exactly why it was blocked and what fixes it. Never finish setup without either sending or explaining why not.

## Connections
You handle the connector: the user only says what they use. Each connection has a short `id` and a plain `label`, maps the provider's own field names onto the item shape (`date` and `text` required; `id`, `title`, `rating`, `url` optional), and sets `maxItems` to cover the window (each run reads the most recent 500 items across all connections). Test each one and show the user a sample before keeping it.

- **Online service** (`engine/readers/service.py`): any JSON API, read with plain GET requests to the hosts you record. There is no connector code: you write the connection from the provider's API, which you know or can read in its docs. Choose a read endpoint that lists recent feedback, newest first; use `{page}` for paging and `{since}` for the window start where the API supports them; map its fields in `columns` (dotted paths work, for example `user.name`); set `itemsPath` if the items are nested; set `skipIf` to a field that marks non-feedback entries (for example `pull_request` on GitHub).
  - **With a key:** ask for a **read only** key and say in one line where to create it; if the provider only offers keys that can write, say so and suggest a file export. Store it in `.env` in the project root (the same folder as `README.md`; create the file if it doesn't exist, and tell the user its full path) and name it in `auth`: `bearer` (`{"type": "bearer", "env": "INTERCOM_TOKEN"}`), or `client_credentials` for OAuth clients whose tokens expire: store the client id and secret in `.env` and add `"tokenUrl"`, `"idEnv"`, `"secretEnv"` and `"scope": "read"`; the reader fetches a fresh read only token on every run. Add `"optional": true` when the API also works without one. Connections with a key are private (shape themes, never quoted) unless the data is public and the user agrees to `"private": false`.
  - Starting points: **Zendesk** `https://<sub>.zendesk.com/api/v2/tickets.json?sort_by=created_at&sort_order=desc&per_page=100&page={page}` (an OAuth client of kind Confidential, with `client_credentials` and `tokenUrl: https://<sub>.zendesk.com/oauth/tokens`, scope `read`; `itemsPath: tickets`). **Intercom** `https://api.intercom.io/conversations` (bearer; `itemsPath: conversations`). **GitHub Issues** `https://api.github.com/repos/<owner>/<repo>/issues?state=all&sort=created&direction=desc&since={since}&per_page=100&page={page}` (bearer, optional; `skipIf: pull_request`). Check the provider's current docs; these change.
  - Example: `{"type": "service", "label": "Zendesk tickets", "url": "https://acme.zendesk.com/api/v2/tickets.json?sort_by=created_at&sort_order=desc&page={page}", "hosts": ["acme.zendesk.com"], "auth": {"type": "client_credentials", "tokenUrl": "https://acme.zendesk.com/oauth/tokens", "idEnv": "ZENDESK_CLIENT_ID", "secretEnv": "ZENDESK_CLIENT_SECRET", "scope": "read"}, "itemsPath": "tickets", "columns": {"id": "id", "date": "created_at", "title": "subject", "text": "description"}, "maxPages": 10}`
- **Ratings:** if a connection has a rating or score, map it to `rating` and set `ratingScale` to its top value (5 for stars, 10 for 0 to 10 scores); the pulse's ratings need both, and code refuses a rating without a scale.
- **Internal warehouse or data store:** ask for the project, dataset and table or view, and what each column holds. If feedback is spread over tables, suggest the data owner makes one view. Access must be read only on that dataset (BigQuery Data Viewer, plus Job User on the project); the reader signs in with Google application default credentials or the identity a cloud job runs as. `{"type": "warehouse", "engine": "bigquery", "project": "...", "dataset": "...", "table": "...", "columns": {"date": "created_at", "text": "body"}}`. Always private.
- **File:** save the export in `profiles/<key>/data/` (offer to move it), read its header row, map the columns, and ask whether it's private. `{"type": "file", "file": "data/tickets.csv", "columns": {...}, "private": true}`.

## Email
The pulse is sent as the email itself, from a Gmail account the user owns, to the recipient in the user scope. Ask for the **Gmail address to send from** and the **address to send to** (they can be the same), then walk the user through the app password as numbered steps, because most people have never made one:
1. Use a personal Gmail account to send from. Work and school accounts often block app passwords.
2. Open https://myaccount.google.com/security and turn on **2-Step Verification** if it is off (app passwords need it).
3. Open https://myaccount.google.com/apppasswords, type a name such as `Customer Pulse`, and click **Create**.
4. Google shows a 16-letter password once. That is the app password; it is not their normal password, and spaces don't matter.

Offer two ways to hand it over: paste the 16 letters in the chat, or (better, so it never sits in the chat) open the `.env` file you create and paste it after `SMTP_PASSWORD=` themselves. Write the settings to `.env` in the project root (create the file if needed, and tell the user its full path); it is never committed. `SMTP_USER` is the full sending address:
```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=app-password
```
Save the recipient in `user_scope.json` → `recipients`. Send one test with `python3 engine/steps/send.py <key>` after the first pulse, and only that way: never send email any other way. Changing the recipient later is a user scope change.

## Schedule
Record it in `user_scope.json` → `schedule`, for example `{"days": ["Mon"], "time": "08:00"}`. A scheduled run has nobody in the chat, so it always sends by email (the job runs `send.py` after the agent finishes), carries only `SKILL.md` (never this setup skill, so it has no instructions for changing its own reach), and can only write to `runs/`. Trigger it once by hand and check the result with the user before leaving it on. This path is designed but not yet proven end to end: tell the user so.

**On Google Cloud** (the worked example; you deploy it, confirming each access change with the user):
1. Ask for the project and region (default the region of any BigQuery dataset). Enable Cloud Run, Cloud Scheduler, Secret Manager, Artifact Registry and Vertex AI.
2. Create one service account for this profile, `pulse-<key>@<project>.iam.gserviceaccount.com`, with only: Vertex AI User (to run the model), Secret Manager Secret Accessor on this profile's secrets, and for a warehouse connection BigQuery Data Viewer on that dataset plus BigQuery Job User. Nothing else; never a broader role.
3. Put each value from `.env` that the profile uses (email password, service keys) in Secret Manager, one secret each.
4. Build the image from the repository `Dockerfile` (it installs Gemini CLI, which signs in to Vertex AI as the service account, and removes `setup/`), push it to Artifact Registry, and create a Cloud Run job that runs as the service account, with the secrets as environment variables and `PROFILE=<key>`. Commit the profile first or add it to the image; it must not contain secrets.
5. Create a Cloud Storage bucket for this profile's runs (never public), give the service account Storage Object Admin on that bucket only, and mount it on the Cloud Run job at `/app/runs`. Every run stays there as an audit trail.
6. Create a Cloud Scheduler job in the user's timezone that runs the Cloud Run job on the schedule.
7. Run the job once by hand, read its logs with the user (every step and the send gate should pass), and only then enable the scheduler. To pause, disable the scheduler job and set `schedule` back to `null`.

**Elsewhere:** any scheduler that can start a headless harness on a machine with the project (cron, another cloud's job runner) works, following the same rules: the run skill only, a read only project except `runs/`, a least privilege identity, secrets outside the project.

## Changing things later
- Focus, tone, look, output format: edit `PROFILE.md` (its settings at the top, or the free text). Save preferences only there, never in your harness's own memory or user files, which are shared across clients.
- A connection, the recipient or the schedule: a user scope change; follow the sections above, and confirm with the user.
- A new kind of connection, write access, looser limits, posting replies: a change to the use case itself, not setup.
