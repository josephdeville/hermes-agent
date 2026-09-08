#!/usr/bin/env python3
"""Content-research briefing store: outperformance + novelty, no copying.

The agent gathers video stats via `web_search` / `browser_navigate`. This
script scores them, checks novelty against published topics, and writes a
durable brief. Cron is stateless — channel lists and topic history live here.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

SKILL = "content-research"
STOP = {
    "a", "an", "the", "and", "or", "to", "of", "in", "on", "for", "with",
    "how", "why", "what", "this", "that", "from", "your", "my", "i",
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser()


def store_dir(store: str | None = None) -> Path:
    path = Path(store).expanduser() if store else _hermes_home() / "operator" / SKILL
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _save(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def _read_json(path: str | None):
    raw = Path(path).read_text(encoding="utf-8") if path and path != "-" else sys.stdin.read()
    raw = raw.strip()
    return json.loads(raw) if raw else None


def tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if t not in STOP and len(t) > 2}


def novelty_score(title: str, published: list[str]) -> float:
    """1.0 = fully new; 0.0 = exact token overlap with a published topic."""
    src = tokens(title)
    if not src:
        return 1.0
    worst = 1.0
    for topic in published:
        other = tokens(topic)
        if not other:
            continue
        overlap = len(src & other) / len(src)
        worst = min(worst, 1.0 - overlap)
    return round(worst, 4)


def init_store(store: str | None = None) -> dict:
    root = store_dir(store)
    if not (root / "channels.json").exists():
        _save(root / "channels.json", {"channels": [], "updated_at": _now()})
    if not (root / "published.json").exists():
        _save(root / "published.json", {"topics": [], "updated_at": _now()})
    if not (root / "videos.json").exists():
        _save(root / "videos.json", {"videos": [], "updated_at": _now()})
    return {"ok": True, "store": str(root)}


def set_channels(channels: list, store: str | None = None) -> dict:
    root = store_dir(store)
    cleaned = []
    for item in channels:
        if isinstance(item, str):
            cleaned.append({"name": item, "url": ""})
        elif isinstance(item, dict) and item.get("name"):
            cleaned.append({"name": str(item["name"]), "url": str(item.get("url") or "")})
    payload = {"channels": cleaned, "updated_at": _now()}
    _save(root / "channels.json", payload)
    return {"ok": True, "count": len(cleaned)}


def ingest_videos(videos: list[dict], store: str | None = None) -> dict:
    if not isinstance(videos, list):
        return {"ok": False, "error": "expected a JSON array of videos"}
    root = store_dir(store)
    init_store(store)
    existing = _load(root / "videos.json", {"videos": []}).get("videos", [])
    by_id = {}
    for vid in existing:
        key = str(vid.get("video_id") or vid.get("url") or "").strip()
        if key:
            by_id[key] = vid
    accepted = 0
    skipped = 0
    for raw in videos:
        if not isinstance(raw, dict):
            skipped += 1
            continue
        title = str(raw.get("title") or "").strip()
        channel = str(raw.get("channel") or "").strip()
        try:
            views = float(raw.get("views") or 0)
        except (TypeError, ValueError):
            skipped += 1
            continue
        if not title or not channel or views < 0:
            skipped += 1
            continue
        key = str(raw.get("video_id") or raw.get("url") or f"{channel}:{title}").strip()
        row = {
            "video_id": key,
            "title": title,
            "channel": channel,
            "views": views,
            "upload_date": str(raw.get("upload_date") or "").strip(),
            "url": str(raw.get("url") or "").strip(),
            "hook_pattern": str(raw.get("hook_pattern") or "").strip(),
            "why_it_worked": str(raw.get("why_it_worked") or "").strip(),
            "adaptation_idea": str(raw.get("adaptation_idea") or "").strip(),
            "channel_avg_views": raw.get("channel_avg_views"),
            "updated_at": _now(),
        }
        by_id[key] = row
        accepted += 1
    bundle = {"videos": list(by_id.values()), "updated_at": _now()}
    _save(root / "videos.json", bundle)
    return {"ok": True, "accepted": accepted, "skipped": skipped, "total": len(bundle["videos"])}


def published_add(topics: list[str], store: str | None = None) -> dict:
    root = store_dir(store)
    init_store(store)
    data = _load(root / "published.json", {"topics": []})
    have = [str(t) for t in data.get("topics", [])]
    lower = {t.lower() for t in have}
    added = []
    for topic in topics:
        text = str(topic or "").strip()
        if text and text.lower() not in lower:
            have.append(text)
            lower.add(text.lower())
            added.append(text)
    data["topics"] = have
    data["updated_at"] = _now()
    _save(root / "published.json", data)
    return {"ok": True, "added": added, "total": len(have)}


def _channel_averages(videos: list[dict]) -> dict[str, float]:
    buckets: dict[str, list[float]] = defaultdict(list)
    pinned = {}
    for vid in videos:
        channel = vid.get("channel") or ""
        buckets[channel].append(float(vid.get("views") or 0))
        if vid.get("channel_avg_views"):
            try:
                pinned[channel] = float(vid["channel_avg_views"])
            except (TypeError, ValueError):
                pass
    averages = {}
    for channel, values in buckets.items():
        if channel in pinned:
            averages[channel] = pinned[channel]
        else:
            averages[channel] = sum(values) / len(values) if values else 0.0
    return averages


def brief(store: str | None = None, top: int = 3, min_ratio: float = 1.5) -> dict:
    root = store_dir(store)
    init_store(store)
    videos = _load(root / "videos.json", {"videos": []}).get("videos", [])
    published = _load(root / "published.json", {"topics": []}).get("topics", [])
    averages = _channel_averages(videos)
    scored = []
    for vid in videos:
        avg = averages.get(vid.get("channel") or "") or 0.0
        views = float(vid.get("views") or 0)
        ratio = (views / avg) if avg > 0 else 0.0
        novel = novelty_score(vid.get("title") or "", published)
        if ratio < min_ratio:
            continue
        scored.append(
            {
                **vid,
                "channel_avg_views": round(avg, 2),
                "outperformance_ratio": round(ratio, 3),
                "novelty": novel,
                "rank_score": round(ratio * (0.4 + 0.6 * novel), 3),
            }
        )
    scored.sort(key=lambda r: r["rank_score"], reverse=True)
    winners = scored
    ideas = []
    seen_tokens: list[set[str]] = []
    for row in winners:
        idea = row.get("adaptation_idea") or row.get("title")
        idea_tokens = tokens(str(idea))
        if any(len(idea_tokens & prev) / max(len(idea_tokens), 1) > 0.7 for prev in seen_tokens):
            continue
        if novelty_score(str(idea), published) < 0.35:
            continue
        ideas.append(
            {
                "title": row["title"],
                "channel": row["channel"],
                "outperformance_ratio": row["outperformance_ratio"],
                "adaptation_idea": row.get("adaptation_idea") or "",
                "hook_pattern": row.get("hook_pattern") or "",
                "why_it_worked": row.get("why_it_worked") or "",
                "url": row.get("url") or "",
            }
        )
        seen_tokens.append(idea_tokens)
        if len(ideas) >= top:
            break
    result = {
        "ok": True,
        "winners": winners,
        "top_3_this_week": ideas,
        "published_topic_count": len(published),
        "min_ratio": min_ratio,
    }
    _save(root / "last_brief.json", {**result, "updated_at": _now()})
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="YouTube research briefing store.")
    parser.add_argument("--store")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    sub.add_parser("channels-list")
    p_ch = sub.add_parser("channels-set")
    p_ch.add_argument("--file")
    p_in = sub.add_parser("ingest")
    p_in.add_argument("--file")
    sub.add_parser("published-list")
    p_pub = sub.add_parser("published-add")
    p_pub.add_argument("topics", nargs="+")
    p_brief = sub.add_parser("brief")
    p_brief.add_argument("--top", type=int, default=3)
    p_brief.add_argument("--min-ratio", type=float, default=1.5)
    args = parser.parse_args(argv)
    store = args.store

    if args.cmd == "init":
        print(json.dumps(init_store(store), indent=2))
        return 0
    if args.cmd == "channels-list":
        init_store(store)
        print(json.dumps(_load(store_dir(store) / "channels.json", {}), indent=2))
        return 0
    if args.cmd == "channels-set":
        payload = _read_json(args.file)
        channels = payload if isinstance(payload, list) else (payload or {}).get("channels", [])
        print(json.dumps(set_channels(channels, store), indent=2))
        return 0
    if args.cmd == "ingest":
        payload = _read_json(args.file)
        videos = payload if isinstance(payload, list) else (payload or {}).get("videos", [])
        print(json.dumps(ingest_videos(videos, store), indent=2))
        return 0
    if args.cmd == "published-list":
        init_store(store)
        print(json.dumps(_load(store_dir(store) / "published.json", {}), indent=2))
        return 0
    if args.cmd == "published-add":
        print(json.dumps(published_add(args.topics, store), indent=2))
        return 0
    if args.cmd == "brief":
        print(json.dumps(brief(store, top=args.top, min_ratio=args.min_ratio), indent=2))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
