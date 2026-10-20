# Profiles

One folder per client, created by the setup conversation (`setup/SKILL.md`). Only setup writes a client's scope, with
their confirmation. The public repository ships with no clients.

```
profiles/<key>/
  PROFILE.md        how the brief is shown: a few settings at the top, then free text in the client's own words
  user_scope.json   what the brief may reach: connections, recipient, timezone, schedule; written only by setup
  data/             any feedback files the client exports (optional)
  assets/           optional images: logo.png (square) and header.png (wide, about 1280x320; .jpg works too)
```
