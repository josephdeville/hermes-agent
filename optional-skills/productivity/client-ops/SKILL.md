---
name: client-ops
description: Turn call notes into follow-ups, actions, and reminders.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [client-ops, follow-up, memory-hygiene, operator, retainer]
    category: productivity
    related_skills: [junior-operator, prospect-and-draft, notion, google-workspace]
---

# Client Ops and Follow-Up Operator

Sit next to the communication layer: summarize a call, draft the follow-up,
extract actions with owners and deadlines, and remember *standing* client
preferences. Temporary task progress is not memory.

Hermes drafts. A human approves before anything leaves the building. For
more than one client, use **profiles** (`hermes -p acme`) so client A never
appears in client B's context.

## When to Use

- "I just finished a client call" + notes or a transcript
- Daily reminder sweep of open actions
- User wants a fractional back-office operator without mixing client books

Do not use to auto-send the follow-up, to dump a whole CRM into MEMORY.md, or
to mix two clients in one profile.

## Prerequisites

Helpers the GitHub hub actually downloads (name the real file in
backticks, not `SKILL_DIR/scripts/ops.py`):

- `scripts/ops.py` — JSON store for calls, actions, and prefs
- `templates/call.json` — ingest shape

```bash
hermes skills install josephdeville/hermes-agent/optional-skills/productivity/client-ops --category productivity -y
# Reinstall after a missing-helper install: add --force
python3 ~/.hermes/skills/productivity/client-ops/scripts/ops.py init
```

`official/productivity/client-ops` only works when this fork is the
installed Hermes package. `ops.py init` does not need an LLM.

A chat or cron one-shot does: run `hermes model`, or put an API key in
`${HERMES_HOME:-~/.hermes}/.env` (`OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`,
or `OPENAI_API_KEY`). Then `hermes config set model <id>` if no default
model is set.

Optional: Notion/Google Workspace skills if the user wants actions copied
into their tracker. The operator JSON store is enough to start.

## How to Run

```bash
SCRIPT=SKILL_DIR/scripts/ops.py
python3 $SCRIPT ingest-call --file /tmp/call.json
python3 $SCRIPT due --within-hours 24
python3 $SCRIPT audit
```

`call.json` shape:

```json
{
  "client": "acme",
  "source_call": "2026-09-08 standup",
  "follow_up_draft": "…",
  "actions": [
    {"action": "Send revised timeline", "owner": "Alex", "deadline": "2026-09-10"}
  ],
  "durable_prefs": [
    {"key": "billing", "value": "Net-30, invoice on the 1st"}
  ],
  "send_approved": false
}
```

Default prompt:

> I just finished a client call. Turn these notes into a clean follow-up
> message, a list of actions, owners, deadlines, and reminders. Save the
> durable client preferences to memory, but do not save temporary task
> progress as a memory. Ask me before sending anything externally.

```bash
hermes cron create "every day 8:00" --skill client-ops --name "Ops reminder sweep" \
  "ops.py due --within-hours 24. List overdue and due-today actions. Do not send follow-ups."
```

## Quick Reference

```
python3 $SCRIPT ingest-call --file call.json
python3 $SCRIPT prefs acme
python3 $SCRIPT due --within-hours 48
python3 $SCRIPT complete act-0001
python3 $SCRIPT classify "Follow up Friday about the invoice"
python3 $SCRIPT audit
```

`classify` / `pref-set` refuse strings that look like task progress
(deadlines, todos, "follow up") unless `--force` is used during an audit.

Send gate: `send_approved` only marks the draft `approved`. This script
**never sends**. Use `clarify` and let the human copy/paste or hit send in
their mail client.

## Procedure

1. Identify the client. If this profile already holds another client's book,
   stop and tell the user to `hermes -p <client>`.
2. Extract: follow-up draft, action table (`action | owner | deadline`),
   durable prefs (voice, billing, standing decisions).
3. `ingest-call` with `send_approved: false`.
4. Show the draft + actions. Ask with `clarify` before any external send.
5. Durable slice **may** go to native memory (a few facts). The full book
   stays in `prefs.json`. Actions stay in `actions.json` — never MEMORY.md.
6. Daily: `due` and remind. `complete` when the human says it's done.
7. Weekly: `audit` and delete prefs that look like stale tasks.

## Pitfalls

- Memory pollution: "send the deck Friday" is an action, not a preference.
- Guessed owners/deadlines: keep them in the draft for confirmation.
- Client data leak: one profile per client; no cross-client memory.
- "Ask before sending" as a prompt-only rule — there is no send credential
  in this workflow. `clarify` is the human gate.

## Verification

- [ ] Follow-up is a draft with `send_gate: blocked` until the user approves.
- [ ] Actions have owner + deadline fields (even if the user must fill them).
- [ ] `classify "Follow up Friday"` → `transient`; a billing cadence → `durable`.
- [ ] `audit` flags anything that drifted into prefs by mistake.
- [ ] Native MEMORY.md was not used as the task tracker.
