---
name: prospect-and-draft
description: Research ICP prospects and draft outreach; never send.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [prospecting, outreach, leads, crm, operator]
    category: productivity
    related_skills: [junior-operator, client-ops, notion]
---

# Prospect and Draft

Produce a qualified, ICP-matched prospect table with personalized angle
drafts. Hermes researches and drafts. A human reviews and sends. This skill
never sends email, DMs, or CRM sequences.

## When to Use

- User wants a weekly pipeline of companies that match an offer
- User asks to "find N companies and write outreach"
- A Monday cron job should top up a sheet without re-contacting last week's domains

Do not use to scrape or buy contact lists, auto-send cold email, or skip the
"why they might need this offer" step.

## Prerequisites

Helpers the GitHub hub actually downloads:

- `scripts/pipeline.py` — ICP, prospect table, contacted-domain store
- `templates/icp.json` — offer / segments / disqualifiers
- `templates/prospects.json` — upsert row shape

```bash
hermes skills install josephdeville/hermes-agent/optional-skills/productivity/prospect-and-draft --category productivity -y
python3 ~/.hermes/skills/productivity/prospect-and-draft/scripts/pipeline.py init
```

`official/productivity/prospect-and-draft` only works when this fork is the
installed Hermes package. Chat/cron runs need `hermes model` or an API key
in `${HERMES_HOME:-~/.hermes}/.env`; `pipeline.py init` does not.

Put the offer, segments, and disqualifiers in the store (`set-icp`), not in
MEMORY.md. Previously-contacted domains also live in the store so stateless
cron runs can dedupe.

## How to Run

```bash
SCRIPT=SKILL_DIR/scripts/pipeline.py
python3 $SCRIPT init
python3 $SCRIPT set-icp --file /path/to/icp.json
python3 $SCRIPT contacted-list
# after research:
python3 $SCRIPT upsert --file /tmp/prospects.json
python3 $SCRIPT export --format md
```

Default research prompt (swap industry/offer):

> Find 25 B2B companies in crypto, SaaS, or creator tools that look like they
> could benefit from a short-form content system. For each one, capture the
> company name, website, what they sell, why they might need content, and one
> personalized outreach angle. Do not send anything, put the research into a
> table, and draft three message variants for review.

Cron (gateway must be running):

```bash
hermes cron create "every monday 9:00" --skill prospect-and-draft --name "Weekly prospecting" \
  "Load ICP from the operator store. Search with web_search/browser_navigate. Upsert via pipeline.py. Export a markdown table. Do not send anything."
```

## Quick Reference

```
python3 $SCRIPT init
python3 $SCRIPT set-icp --file icp.json
python3 $SCRIPT upsert --file prospects.json   # stdin JSON array also fine
python3 $SCRIPT list --status draft
python3 $SCRIPT export --format md|csv|json
python3 $SCRIPT mark-contacted example.com
```

Row schema: `company | website | segment | what_they_sell | why_they_need_offer | personalized_angle | message_variants[3] | source_url | fit_score`

Dedupe key: registrable domain (`www` stripped). Rows whose domain is already
in `contacted.json` are skipped.

## Procedure

1. `pipeline.py show-icp`. If `offer` is empty, ask the user and `set-icp`.
2. `contacted-list` so you do not re-pitch last week's domains.
3. Discover companies with `web_search` and `web_extract` / `browser_navigate`.
   Fan out with `delegate_task` when scanning many names. Cap at the ICP
   `daily_cap` (default 25).
4. Every row **must** explain *why this offer fits*. Drop rows that cannot.
5. Draft three message variants per company. Do not invent personal emails
   from scraped staff lists.
6. `upsert` the JSON array. Report added / skipped_contacted / skipped_invalid.
7. Deliver `export --format md` to the user (or write a file they named).
8. After the human actually sends, `mark-contacted example.com`.

## Pitfalls

- Generic leads: the skill is the "why they need the offer" field. Empty = invalid.
- Duplicate outreach: contacted list is in the JSON store, never MEMORY.md.
- Compliance: no purchased lists, no auto-send, honor opt-outs the human records.
- Hermes approval does **not** block `send_message`. The gate is: this profile
  has no send credential, and you stop at drafts.

## Verification

- [ ] Store exists under `$HERMES_HOME/operator/prospect-and-draft/`.
- [ ] Re-upserting the same domain updates the row instead of duplicating it.
- [ ] A contacted domain is skipped on the next run.
- [ ] Output is a table, not a chatty paragraph.
- [ ] Nothing was sent.
