---
name: trend-scout
description: Catch fresh, actionable topics in the first hour.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [trends, digest, monitoring, hacker-news, operator]
    category: productivity
    related_skills: [junior-operator, content-research, blogwatcher]
---

# Real-Time Trend Scout

Catch a topic while it is still fresh so the user can react, film, thread, or
pitch. The agent increases surface area; it does not replace taste.

Each cron run is stateless. The **already-covered log** lives in the operator
store so Monday's digest cannot re-alert Sunday's link.

## When to Use

- User wants a morning digest of fresh, relevant, actionable items
- Monitoring X, YouTube, Hacker News, and industry news for a keyword set
- Alert fatigue is a risk and items must be filtered, not dumped

Do not use for evergreen roundups, SEO keyword lists, or auto-posting.

## Prerequisites

Helpers the GitHub hub actually downloads:

- `scripts/digest.py` — keyword filter, covered-log, HN fetch
- `templates/keywords.json` — topic terms

```bash
hermes skills install josephdeville/hermes-agent/optional-skills/productivity/trend-scout --category productivity -y
python3 ~/.hermes/skills/productivity/trend-scout/scripts/digest.py init
python3 ~/.hermes/skills/productivity/trend-scout/scripts/digest.py keywords-set --file ~/.hermes/skills/productivity/trend-scout/templates/keywords.json
```

`official/productivity/trend-scout` only works when this fork is the
installed Hermes package. Chat/cron runs need `hermes model` or an API key
in `${HERMES_HOME:-~/.hermes}/.env`; `digest.py init` does not.

Hacker News can be fetched with no key (`fetch-hn`). X/YouTube/news still go
through `web_search` / `browser_navigate` / RSS, then `digest --file`.

## How to Run

```bash
SCRIPT=SKILL_DIR/scripts/digest.py
python3 $SCRIPT fetch-hn --hours 24
# plus items you gathered:
python3 $SCRIPT digest --file /tmp/items.json --max-age-hours 24
python3 $SCRIPT mark-covered hn:123456 https://example.com/story
```

Item JSON: `id`, `source`, `title`, `url`, `published_at`, optional
`why_it_matters`, `recommended_format`, `draft_hook`.

Default prompt:

> Every morning at 8:00 a.m. check X, YouTube, Hacker News, and AI news
> sources for topics related to AI agents, Claude Code, OpenClaw, Hermes, and
> AI automation. Only send opportunities that are fresh and relevant and
> actionable. For each one, include the source, why it matters, and the
> recommended response format and a draft hook.

```bash
hermes cron create "every day 8:00" --skill trend-scout --name "Morning trend digest" \
  "Load keywords, fetch HN, search other sources, digest.py, deliver only fresh+relevant+actionable items with source, why, format, draft hook. Then mark-covered."
```

## Quick Reference

```
python3 $SCRIPT keywords-set --file keywords.json
python3 $SCRIPT fetch-hn --hours 24
python3 $SCRIPT digest --file items.json --max-age-hours 24
python3 $SCRIPT mark-covered ID_OR_URL
```

Filters, in order: valid title+url → not in covered log → age ≤ max-age-hours
→ keyword match. Sensitivity lives in keywords + max-age, not in "more items."

## Procedure

1. Load keywords. If they are still the defaults, confirm the niche.
2. Gather: `fetch-hn` plus `web_search` for X/YouTube/news. Prefer source
   links over screenshots.
3. For each keepable item, add why it matters, a format (thread / short /
   video / reply), and a draft hook.
4. `digest`. If the list is huge, raise specificity (keywords, not max-age).
5. Deliver the digest to the user's channel. Do not publish.
6. `mark-covered` every id/url you showed so the next run is idempotent.

## Pitfalls

- Notification spam: only fresh AND relevant AND actionable.
- Echo chamber: require more than one source class before calling something a trend.
- Missing the spike: shorten cadence for a launch window; keep covered-log hygiene.
- Stale `published_at`: if the timestamp is missing, say so; do not pretend it is first-hour.

## Verification

- [ ] Items older than max-age-hours are dropped.
- [ ] Re-digesting the same URL after `mark-covered` returns zero new items.
- [ ] Each row has source + why + format + hook.
- [ ] The agent did not post the reaction.
