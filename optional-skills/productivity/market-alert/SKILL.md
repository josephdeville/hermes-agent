---
name: market-alert
description: Read-only Polymarket anomaly briefs; never trade.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [polymarket, alerts, research, prediction-markets, operator]
    category: productivity
    related_skills: [junior-operator, polymarket]
---

# Prediction-Market Research Alerts

Turn Polymarket noise into a verification brief: market link, price, possible
reason, related news, what to check before *any* human action.

**This skill never places trades.** There is no wallet, no order, no CLOB
auth. If a user asks the agent to trade, refuse and keep the profile
read-only. Autopilot trading is how people get wrecked.

## When to Use

- User wants unusual-movement alerts (price Δ or volume spike)
- Research brief for crypto / elections / AI / sports / macro markets
- Pair with the bundled `polymarket` skill for ad-hoc lookups

Do not use to bet, advise a bet, or imply a prediction. Correlation is not
cause.

## Prerequisites

```bash
hermes skills install official/productivity/market-alert
python3 SKILL_DIR/scripts/alerts.py init
```

Gamma API is public and unauthenticated. **Do not add a trading key to this
profile.** Per-poll snapshots must persist or a stateless cron run cannot
compute a 24h delta.

## How to Run

```bash
SCRIPT=SKILL_DIR/scripts/alerts.py
python3 $SCRIPT watchlist-set --file watchlist.json
python3 $SCRIPT fetch-detect
# or, after gathering JSON yourself:
python3 $SCRIPT detect --file /tmp/markets.json --threshold 0.08
```

First `detect` / `fetch-detect` **only stores a baseline** and emits no
alerts. The next run compares.

Default prompt:

> Monitor these Polymarket categories for unusual movement: crypto, elections,
> AI, sports, and macro. Do not place trades. When a market moves more than 8%
> in 24 hours or volume spikes unusually, send me a brief with the market link,
> current price, possible reason for the move, related news, and what I should
> verify before taking any action.

Threshold is **absolute probability points** (0.08 = 8 points, e.g. 50% →
58%). The video's warning: 8%/24h will spam; try 0.25 or a daily digest.

```bash
hermes cron create "every 30m" --skill market-alert --name "Polymarket anomalies" \
  "alerts.py fetch-detect. For each alert, web_search related news. Deliver verification briefs. Do not place trades."
```

## Quick Reference

```
python3 $SCRIPT watchlist-set --file watchlist.json
python3 $SCRIPT fetch-detect --threshold 0.25 --volume-spike 3
python3 $SCRIPT detect --file markets.json
python3 $SCRIPT alerts-list
```

Alert schema: `market_link | category | current_price | delta_price | volume_spike | possible_reason | related_news[] | verify_before_action[]`

Cooldown: the same market is not re-alerted within 12 hours.

## Procedure

1. Confirm read-only: no wallet / CLOB secret in `.env`.
2. `init` + watchlist categories/threshold.
3. `fetch-detect` (or ingest Gamma-shaped JSON). If `baseline: true`, say so and stop.
4. For each alert, `web_search` the question + date. Fill `possible_reason`
   as a *hypothesis* and `related_news` as citations.
5. Always include `verify_before_action`. Never say "buy" / "sell" / "this will resolve Yes."
6. Deliver briefs. Human acts in their own account if they act at all.

## Pitfalls

- Alert fatigue: raise `--threshold` (0.25) or switch to a daily digest cron.
- First cron tick looks "broken" because it is the baseline snapshot — expected.
- Stale quotes: check `taken_at` on the snapshot.
- Scope creep into trading: keep this profile credential-less for orders.

## Verification

- [ ] No trading credentials in this profile.
- [ ] Second detect with a ≥threshold move produces an alert; a sub-threshold move does not.
- [ ] Re-detect inside cooldown does not duplicate the alert.
- [ ] Briefs say "verify" not "predict."
