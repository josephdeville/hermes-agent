#!/usr/bin/env python3
"""Trend-scout digest: freshness + relevance + already-covered dedupe.

Optional HN fetch uses the public Algolia API (no key). X/YouTube/news items
are ingested as JSON after the agent gathers them. Covered IDs persist across
stateless cron runs.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SKILL = "trend-scout"
HN_SEARCH = "https://hn.algolia.com/api/v1/search_by_date"
UA = "HermesAgent-trend-scout/1.0 (+https://github.com/NousResearch/hermes-agent)"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().strftime("%Y-%m-%dT%H:%M:%SZ")


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


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    for candidate in (text, text.replace("Z", "+00:00")):
        try:
            dt = datetime.fromisoformat(candidate)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            continue
    try:
        return datetime.fromtimestamp(float(text), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def item_id(item: dict) -> str:
    for key in ("id", "url", "title"):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return ""


def init_store(store: str | None = None) -> dict:
    root = store_dir(store)
    if not (root / "keywords.json").exists():
        _save(
            root / "keywords.json",
            {
                "keywords": ["AI agents", "Hermes", "Claude Code", "OpenClaw", "AI automation"],
                "updated_at": _now_iso(),
            },
        )
    if not (root / "covered.json").exists():
        _save(root / "covered.json", {"ids": [], "updated_at": _now_iso()})
    return {"ok": True, "store": str(root)}


def set_keywords(keywords: list[str], store: str | None = None) -> dict:
    cleaned = [str(k).strip() for k in keywords if str(k).strip()]
    payload = {"keywords": cleaned, "updated_at": _now_iso()}
    _save(store_dir(store) / "keywords.json", payload)
    return {"ok": True, "count": len(cleaned)}


def mark_covered(ids: list[str], store: str | None = None) -> dict:
    root = store_dir(store)
    init_store(store)
    data = _load(root / "covered.json", {"ids": []})
    have = list(data.get("ids", []))
    seen = set(have)
    added = []
    for raw in ids:
        key = str(raw or "").strip()
        if key and key not in seen:
            have.append(key)
            seen.add(key)
            added.append(key)
    data["ids"] = have
    data["updated_at"] = _now_iso()
    _save(root / "covered.json", data)
    return {"ok": True, "added": added, "total": len(have)}


def relevant(item: dict, keywords: list[str]) -> bool:
    if not keywords:
        return True
    blob = " ".join(
        str(item.get(k) or "") for k in ("title", "summary", "why_it_matters", "source")
    ).lower()
    return any(k.lower() in blob for k in keywords)


def digest(
    items: list[dict],
    store: str | None = None,
    max_age_hours: float = 24.0,
    now: datetime | None = None,
) -> dict:
    if not isinstance(items, list):
        return {"ok": False, "error": "expected a JSON array of items"}
    root = store_dir(store)
    init_store(store)
    keywords = _load(root / "keywords.json", {"keywords": []}).get("keywords", [])
    covered = set(_load(root / "covered.json", {"ids": []}).get("ids", []))
    clock = now or _now()
    kept = []
    dropped = {"stale": 0, "covered": 0, "irrelevant": 0, "invalid": 0}
    for raw in items:
        if not isinstance(raw, dict):
            dropped["invalid"] += 1
            continue
        key = item_id(raw)
        title = str(raw.get("title") or "").strip()
        url = str(raw.get("url") or "").strip()
        if not key or not title or not url:
            dropped["invalid"] += 1
            continue
        if key in covered or url in covered:
            dropped["covered"] += 1
            continue
        published = parse_dt(raw.get("published_at") or raw.get("created_at"))
        if published is not None:
            age_h = (clock - published).total_seconds() / 3600.0
            if age_h > max_age_hours:
                dropped["stale"] += 1
                continue
        else:
            age_h = None
        if not relevant(raw, keywords):
            dropped["irrelevant"] += 1
            continue
        kept.append(
            {
                "id": key,
                "source": str(raw.get("source") or "").strip(),
                "title": title,
                "url": url,
                "published_at": published.strftime("%Y-%m-%dT%H:%M:%SZ") if published else None,
                "age_hours": None if age_h is None else round(age_h, 2),
                "why_it_matters": str(raw.get("why_it_matters") or "").strip(),
                "recommended_format": str(raw.get("recommended_format") or raw.get("format") or "").strip(),
                "draft_hook": str(raw.get("draft_hook") or raw.get("hook") or "").strip(),
            }
        )
    kept.sort(key=lambda r: r.get("age_hours") if r.get("age_hours") is not None else 0)
    result = {
        "ok": True,
        "count": len(kept),
        "items": kept,
        "dropped": dropped,
        "max_age_hours": max_age_hours,
        "keywords": keywords,
    }
    _save(root / "last_digest.json", {**result, "updated_at": _now_iso()})
    return result


def fetch_hn(query: str, hours: float = 24.0, timeout: float = 20.0) -> list[dict]:
    created_after = int(_now().timestamp() - hours * 3600)
    params = urllib.parse.urlencode(
        {
            "query": query,
            "tags": "story",
            "numericFilters": f"created_at_i>{created_after}",
            "hitsPerPage": 30,
        }
    )
    req = urllib.request.Request(f"{HN_SEARCH}?{params}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    items = []
    for hit in payload.get("hits") or []:
        object_id = str(hit.get("objectID") or "")
        url = hit.get("url") or (f"https://news.ycombinator.com/item?id={object_id}" if object_id else "")
        created = hit.get("created_at")
        items.append(
            {
                "id": f"hn:{object_id}" if object_id else url,
                "source": "hacker-news",
                "title": hit.get("title") or "",
                "url": url,
                "published_at": created,
                "why_it_matters": "",
            }
        )
    return items


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Trend-scout freshness filter + covered log.")
    parser.add_argument("--store")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    sub.add_parser("keywords-list")
    p_kw = sub.add_parser("keywords-set")
    p_kw.add_argument("--file")
    sub.add_parser("covered-list")
    p_cov = sub.add_parser("mark-covered")
    p_cov.add_argument("ids", nargs="+")
    p_in = sub.add_parser("digest")
    p_in.add_argument("--file")
    p_in.add_argument("--max-age-hours", type=float, default=24.0)
    p_hn = sub.add_parser("fetch-hn")
    p_hn.add_argument("--query", default="")
    p_hn.add_argument("--hours", type=float, default=24.0)
    args = parser.parse_args(argv)
    store = args.store

    if args.cmd == "init":
        print(json.dumps(init_store(store), indent=2))
        return 0
    if args.cmd == "keywords-list":
        init_store(store)
        print(json.dumps(_load(store_dir(store) / "keywords.json", {}), indent=2))
        return 0
    if args.cmd == "keywords-set":
        payload = _read_json(args.file)
        keywords = payload if isinstance(payload, list) else (payload or {}).get("keywords", [])
        print(json.dumps(set_keywords(keywords, store), indent=2))
        return 0
    if args.cmd == "covered-list":
        init_store(store)
        print(json.dumps(_load(store_dir(store) / "covered.json", {}), indent=2))
        return 0
    if args.cmd == "mark-covered":
        print(json.dumps(mark_covered(args.ids, store), indent=2))
        return 0
    if args.cmd == "digest":
        payload = _read_json(args.file)
        items = payload if isinstance(payload, list) else (payload or {}).get("items", [])
        print(json.dumps(digest(items, store, max_age_hours=args.max_age_hours), indent=2))
        return 0
    if args.cmd == "fetch-hn":
        init_store(store)
        query = args.query or " OR ".join(
            _load(store_dir(store) / "keywords.json", {"keywords": []}).get("keywords", [])[:5]
        )
        try:
            items = fetch_hn(query, hours=args.hours)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            print(json.dumps({"ok": False, "error": str(exc)}))
            return 1
        print(json.dumps(digest(items, store, max_age_hours=args.hours), indent=2))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
