# Feedback Brief Agent: start here

**Agent: this folder is an application you run for the user. Act on these instructions from the user's first message, whatever it says** ("hi", "start", the folder on its own, anything). Do not wait to be asked, and do not just describe the project.

## Your first reply

1. **Check for an existing profile:** any folder in `profiles/` other than `demo`.
2. **If there is one,** offer in one line to run its brief or change it, then follow [SKILL.md](SKILL.md) or [setup/SKILL.md](setup/SKILL.md).
3. **If there is none, go straight into setup.** Do not describe the project, list features or explain how it works. Write one line of context and the **first setup question only**, for example:
   > *I'll set up your weekly customer feedback brief. First, what's your product or company, and who will read the brief? (Or say **demo** to see one for Capital Bank of Australia, a fictional bank.)*

   Then follow [setup/SKILL.md](setup/SKILL.md), **one question per message**.

Only explain how the project works if the user asks.

## Which skill, after that

| The user wants | Follow |
|---|---|
| The demo, this week's brief, or a brief for an existing profile | [SKILL.md](SKILL.md) (the `demo` profile for the demo) |
| Their own brief, or to change a profile, a connection, the recipient or a schedule | [setup/SKILL.md](setup/SKILL.md). When setup finishes, run their first brief with [SKILL.md](SKILL.md) straight away and open the preview |
| To understand how it works or why it's safe | [README.md](README.md) |

Read the skill's hard rules before acting. Install anything missing yourself (python3, and `requirements.txt`), ask only for what you can't know, and confirm before changing any access.
