#!/usr/bin/env python3
"""Recommend the first junior-operator skill from starting assets.

Table-driven on purpose: adding a persona is a row, not a new branch.
Python stdlib only. Prints JSON.
"""

from __future__ import annotations

import argparse
import json
import sys

# persona alias -> (skill, why)
PLAYS: dict[str, tuple[str, str]] = {
    "b2b": (
        "prospect-and-draft",
        "Fastest direct ROI: a weekly qualified pipeline for your own offer.",
    ),
    "agency": (
        "prospect-and-draft",
        "Same as B2B; sell the outcome later as a DFY prospecting retainer.",
    ),
    "creator": (
        "content-research",
        "Compounds into growth; pair with trend-scout once briefs are useful.",
    ),
    "founder": (
        "content-research",
        "Founders posting on X/YouTube get leverage from outperformance teardowns.",
    ),
    "operator": (
        "client-ops",
        "Underrated, high willingness to pay, low competition as a retainer.",
    ),
    "va": (
        "client-ops",
        "Turn messy calls into follow-ups and tracked actions without dropping balls.",
    ),
    "freelancer": (
        "client-ops",
        "Retention is the money metric; this is the workflow clients already pay for.",
    ),
    "trader": (
        "market-alert",
        "Read-only research briefs. Never autopilot trades.",
    ),
    "quant": (
        "market-alert",
        "Read-only research briefs. Never autopilot trades.",
    ),
    "agency-owner": (
        "prospect-and-draft",
        "Prove one client on lead-gen, then replicate with hermes -p <client>.",
    ),
    "asset": (
        "trend-scout",
        "Needs distribution first; a niche digest is the smallest asset to ship.",
    ),
}

PACK = [
    "junior-operator",
    "prospect-and-draft",
    "content-research",
    "trend-scout",
    "market-alert",
    "client-ops",
]


def recommend(persona: str) -> dict:
    key = (persona or "").strip().lower().replace(" ", "-").replace("_", "-")
    aliases = {
        "b2b-agency": "b2b",
        "content": "creator",
        "youtube": "creator",
        "virtual-assistant": "va",
        "ops": "operator",
        "trading": "trader",
        "passive": "asset",
        "product": "asset",
    }
    key = aliases.get(key, key)
    if key not in PLAYS:
        return {
            "ok": False,
            "error": f"unknown persona {persona!r}",
            "known": sorted(set(PLAYS) | set(aliases)),
        }
    skill, why = PLAYS[key]
    return {
        "ok": True,
        "persona": key,
        "first_skill": skill,
        "why": why,
        "install": f"hermes skills install official/productivity/{skill}",
        "rule": "Build ONE workflow until it pays for itself. Do not install the other four yet.",
        "pack": PACK,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Recommend the first junior-operator play.")
    parser.add_argument("--persona", required=True, help="b2b, creator, operator, trader, agency-owner, asset, …")
    args = parser.parse_args(argv)
    result = recommend(args.persona)
    print(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    sys.exit(main())
