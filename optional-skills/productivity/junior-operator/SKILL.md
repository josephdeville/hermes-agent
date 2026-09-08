---
name: junior-operator
description: Treat Hermes as a junior operator for paid work.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [operator, playbook, cron, skills, business-ops]
    category: productivity
    related_skills:
      - prospect-and-draft
      - content-research
      - trend-scout
      - market-alert
      - client-ops
---

# Junior Operator Playbook

Hermes is a junior operator: it researches, monitors, drafts, reminds, and
summarizes around a real offer. It is not a money printer, an AI CEO, or an
autopilot trading bot. This hub skill picks **one** workflow, then points at
the matching SOP skill.

Workflows come from Sharbel A.'s "5 Ways I Make Money With Hermes Agent"
(May 2026) plus Hermes platform constraints: cron is a **stateless fresh
agent** each run, native memory is tiny, and approval gates **shell commands**
— not "send this email."

## When to Use

- User wants Hermes to pay for itself / run a business workflow
- User asks for lead gen, content research, trend alerts, Polymarket briefs, or client ops
- User is about to add a cron job that must remember prior runs
- User wants a per-client isolated operator (`hermes -p`)

Do not use for: one-off chat questions, building a new core tool, or
unattended sending/trading.

## Prerequisites

Install this hub, then **only the one SOP you will run this month**:

```bash
hermes skills install official/productivity/junior-operator
hermes skills install official/productivity/prospect-and-draft   # or content-research / trend-scout / market-alert / client-ops
```

Gateway must be running for cron (`hermes gateway install`). Durable state
is written under `${HERMES_HOME:-~/.hermes}/operator/<skill>/` so profiles
stay isolated.

## How to Run

Ask which starting assets the user has, then pick the first skill:

```bash
python3 SKILL_DIR/scripts/choose_play.py --persona creator
```

Personas: `b2b`, `agency`, `creator`, `founder`, `operator`, `va`,
`freelancer`, `trader`, `quant`, `agency-owner`, `asset`.

Then follow that skill's SKILL.md. Do not install the other four until the
first workflow is saving time or creating opportunities.

## Quick Reference

| Play | Skill | Trigger | Human still owns |
|------|-------|---------|------------------|
| Lead gen | `prospect-and-draft` | Weekly cron | Sending outreach |
| Content research | `content-research` | Daily/weekly cron | What to film |
| Trend scout | `trend-scout` | Morning cron | What to publish |
| Market alerts | `market-alert` | Frequent poll | Any trade |
| Client ops | `client-ops` | After a call + daily sweep | External sends |

Shared skeleton: **trigger → skill SOP → tools → external store → human gate → delivery.**

## Procedure

1. **Pick one play** with `choose_play.py`. Stop if the user wants all five.
2. **Install that SOP skill** and read it fully (`skill_view` / `read_file`).
3. **Init the store** (`python3 …/scripts/*.py init`) so cron has somewhere to read/write.
4. **Prove it once manually** with `web_search` / `browser_navigate` / `terminal`. Measure output quality.
5. **Harden**: dedupe keys in the JSON store, delivery channel, `cronjob` with `--skill`.
6. **Gate**: never grant send/trade credentials. Drafts only. Use `clarify` before any external side effect.
7. **Native memory stays tiny**: ICP, voice, standing decisions. Contact lists, covered IDs, snapshots, and task progress go in the operator store (or the client's CRM/sheet).
8. **Multi-client**: `hermes -p <client>` — one profile per client, never mixed memory.

### 30-day starter (any persona)

- Days 1–7: one manual run of one workflow.
- Days 8–14: guardrail + store + cron + skill consistency.
- Days 15–21: one proof artifact (a booked meeting, a used brief, a caught follow-up).
- Days 22–30: sell the *outcome* or ship 2× from the briefs. Not the method.

## Pitfalls

1. **Treating native MEMORY.md as a CRM.** It is ~2,200 characters. Overflow silently corrupts later runs.
2. **Assuming cron remembers last week.** It does not. If a run must know contacted domains / last prices / covered URLs, the script must load and persist them.
3. **Prompt-only "do not send."** Hermes approvals gate dangerous *shell* commands. The send/trade gate is: no outbound credential + human copies the draft.
4. **Alert spam.** Thresholds are first-class knobs (8% vs 25%). Digest mode beats a firehose.
5. **Skipping distribution.** An operator without an offer, a channel, or customer conversations cannot monetize.

## Verification

- [ ] Exactly one SOP skill is installed and scheduled (or run manually).
- [ ] `${HERMES_HOME}/operator/<skill>/` exists and is the source of durable state.
- [ ] No send/trade API key is in this profile's `.env`.
- [ ] A re-run is idempotent: no duplicate rows, no double alerts.
- [ ] Native memory holds only a handful of standing facts.
