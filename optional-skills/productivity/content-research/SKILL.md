---
name: content-research
description: Find outperforming videos and adapt ideas, never copy.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [youtube, content, research, briefing, operator]
    category: productivity
    related_skills: [junior-operator, trend-scout, youtube-content]
---

# Content Research Intelligence Loop

Treat research as a loop, not a one-off: pull competitor videos, score
outperformance vs the channel average, teardown hooks, and rank three ideas
to film this week that are *not* already on your published-topic list.

Hermes drafts briefs. Taste — what actually gets produced — stays human.
Never copy a video; adapt the pattern.

## When to Use

- User wants "what's outperforming in my niche and why"
- Weekly filming ideas for a YouTube/X creator or founder
- Novelty check against topics already published

Do not use to rewrite someone else's video, download copyrighted media, or
replace `youtube-content` (that skill is transcripts → summaries).

## Prerequisites

Helpers the GitHub hub actually downloads:

- `scripts/briefing.py` — ingest, score, and rank filming ideas
- `templates/channels.json` — competitor channel list

```bash
hermes skills install josephdeville/hermes-agent/optional-skills/productivity/content-research --category productivity -y
python3 ~/.hermes/skills/productivity/content-research/scripts/briefing.py init
python3 ~/.hermes/skills/productivity/content-research/scripts/briefing.py channels-set --file ~/.hermes/skills/productivity/content-research/templates/channels.json
```

`official/productivity/content-research` only works when this fork is the
installed Hermes package. Chat/cron runs need `hermes model` or an API key
in `${HERMES_HOME:-~/.hermes}/.env`; `briefing.py init` does not.

You gather stats with `web_search` / `browser_navigate` (or a YouTube API the
user already has). This script only scores, dedupes, and stores.

## How to Run

```bash
SCRIPT=SKILL_DIR/scripts/briefing.py
python3 $SCRIPT ingest --file /tmp/videos.json
python3 $SCRIPT brief --top 3 --min-ratio 1.5
python3 $SCRIPT published-add "my last video topic"
```

Video JSON objects: `title`, `channel`, `views`, plus optional `video_id`,
`url`, `upload_date`, `hook_pattern`, `why_it_worked`, `adaptation_idea`,
`channel_avg_views`. If `channel_avg_views` is missing, the channel average
is computed from the ingested set.

Default prompt:

> Act as my YouTube research operator. Find 10 recent videos in the AI agent
> niche that are outperforming their channel average. For each one, capture
> the title, channel, views, upload date, hook pattern, why it likely worked,
> and how I could adapt that pattern without copying the video. Return the
> top three ideas I should film this week.

```bash
hermes cron create "every monday 8:00" --skill content-research --name "Weekly content brief" \
  "Load channels, research with web_search/browser_navigate, ingest JSON, run briefing.py brief, deliver the table. Do not copy videos."
```

## Quick Reference

```
python3 $SCRIPT channels-set --file channels.json
python3 $SCRIPT ingest --file videos.json
python3 $SCRIPT brief --top 3 --min-ratio 1.5
python3 $SCRIPT published-add "Topic I just filmed"
```

Winner schema: `title | channel | views | upload_date | outperformance_ratio | hook_pattern | why_it_worked | adaptation_idea` plus `top_3_this_week[]`.

## Procedure

1. Load the channel list. Confirm niche keywords with the user if empty.
2. For each channel, collect recent videos (views, date, title). Use
   `delegate_task` to fan out across channels.
3. `ingest` the JSON. Require N samples per channel before trusting an average.
4. Fill hook_pattern / why_it_worked / adaptation_idea on likely winners
   (ratio ≥ `--min-ratio`). Adaptation must name the *pattern*, not the plot.
5. `brief`. Drop ideas that collide with `published.json`.
6. Deliver the winner table + top three. Human picks.
7. When they publish, `published-add` so next week cannot repeat it.

## Pitfalls

- One viral outlier can fake "outperformance" — need a channel baseline and N samples.
- Same ideas every week — novelty uses published-topic tokens in the store.
- Copying — if the adaptation restates the original title, rewrite or drop it.
- YouTube ToS / rate limits — prefer APIs the user owns; otherwise slow browser use.

## Verification

- [ ] Brief includes ratio vs channel average, not raw view counts alone.
- [ ] Top three ideas are absent from published topics.
- [ ] Every winner cites channel + URL.
- [ ] Nothing was published or uploaded by the agent.
