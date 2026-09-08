#!/usr/bin/env python3
"""Read-only Polymarket anomaly detector. Never places trades.

Each cron run is a fresh agent, so 24h/1h deltas require a persisted snapshot.
Default posture: ingest JSON (tests, browser fallback) or fetch Gamma (public,
unauthenticated). Alerts include a verification checklist, not a prediction.
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

SKILL = "market-alert"
GAMMA = "https://gamma-api.polymarket.com"
POLYMARKET_EVENT = "https://polymarket.com/event"
UA = "HermesAgent-market-alert/1.0 (+https://github.com/NousResearch/hermes-agent)"
DEFAULT_THRESHOLD = 0.08  # 8 percentage points, matching the video's starting knob
DEFAULT_VOLUME_SPIKE = 3.0
DEFAULT_COOLDOWN_HOURS = 12.0


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


def parse_prices(raw) -> list[float]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return []
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        try:
            out.append(float(item))
        except (TypeError, ValueError):
            return []
    return out


def yes_price(market: dict) -> float | None:
    prices = parse_prices(market.get("outcomePrices"))
    if prices:
        return prices[0]
    for key in ("price", "yes_price", "current_price"):
        if market.get(key) is None:
            continue
        try:
            return float(market[key])
        except (TypeError, ValueError):
            return None
    return None


def market_volume(market: dict) -> float:
    for key in ("volume", "volume24hr", "volumeNum"):
        if market.get(key) is None:
            continue
        try:
            return float(market[key])
        except (TypeError, ValueError):
            continue
    return 0.0


def market_id(market: dict) -> str:
    for key in ("conditionId", "id", "slug", "question"):
        value = str(market.get(key) or "").strip()
        if value:
            return value
    return ""


def flatten_events(payload) -> list[dict]:
    events = payload
    if isinstance(payload, dict):
        events = payload.get("events") or payload.get("data") or [payload]
    if not isinstance(events, list):
        return []
    markets = []
    for event in events:
        if not isinstance(event, dict):
            continue
        nested = event.get("markets")
        if isinstance(nested, list) and nested:
            slug = event.get("slug") or ""
            category = event.get("category") or ""
            for market in nested:
                if not isinstance(market, dict):
                    continue
                row = dict(market)
                row.setdefault("event_slug", slug)
                row.setdefault("category", category or market.get("category") or "")
                markets.append(row)
        else:
            markets.append(event)
    return markets


def snapshot_from_markets(markets: list[dict], taken_at: str | None = None) -> dict:
    taken = taken_at or _now_iso()
    rows = {}
    for market in markets:
        mid = market_id(market)
        price = yes_price(market)
        if not mid or price is None:
            continue
        slug = str(market.get("event_slug") or market.get("slug") or "")
        rows[mid] = {
            "id": mid,
            "question": str(market.get("question") or market.get("title") or ""),
            "category": str(market.get("category") or ""),
            "price": price,
            "volume": market_volume(market),
            "url": str(market.get("url") or (f"{POLYMARKET_EVENT}/{slug}" if slug else "")),
            "taken_at": taken,
        }
    return {"taken_at": taken, "markets": rows}


def detect(
    current_markets: list[dict],
    previous: dict | None,
    *,
    threshold: float = DEFAULT_THRESHOLD,
    volume_spike: float = DEFAULT_VOLUME_SPIKE,
    cooldown: dict | None = None,
    cooldown_hours: float = DEFAULT_COOLDOWN_HOURS,
    now: datetime | None = None,
) -> dict:
    """Compare current markets to the last snapshot.

    First run (no previous snapshot) stores baseline and emits no alerts —
    a stateless cron job cannot invent a 24h delta from a single sample.
    """
    clock = now or _now()
    current = snapshot_from_markets(current_markets)
    prev_markets = (previous or {}).get("markets") or {}
    cooldown = cooldown or {}
    alerts = []
    skipped_cooldown = 0
    if not prev_markets:
        return {
            "ok": True,
            "baseline": True,
            "alerts": [],
            "compared": 0,
            "snapshot": current,
            "note": "First snapshot stored. Subsequent runs can compute deltas.",
        }

    for mid, row in current["markets"].items():
        prev = prev_markets.get(mid)
        if not prev:
            continue
        delta = row["price"] - float(prev.get("price") or 0)
        prev_vol = float(prev.get("volume") or 0)
        vol_ratio = (row["volume"] / prev_vol) if prev_vol > 0 else 0.0
        price_hit = abs(delta) >= threshold
        volume_hit = prev_vol > 0 and vol_ratio >= volume_spike
        if not (price_hit or volume_hit):
            continue
        last_alert = cooldown.get(mid)
        if last_alert:
            last_dt = None
            try:
                last_dt = datetime.fromisoformat(str(last_alert).replace("Z", "+00:00"))
            except ValueError:
                last_dt = None
            if last_dt is not None:
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=timezone.utc)
                age_h = (clock - last_dt.astimezone(timezone.utc)).total_seconds() / 3600.0
                if age_h < cooldown_hours:
                    skipped_cooldown += 1
                    continue
        alerts.append(
            {
                "market_link": row["url"],
                "market_id": mid,
                "category": row["category"],
                "question": row["question"],
                "current_price": round(row["price"], 4),
                "delta_price": round(delta, 4),
                "volume": row["volume"],
                "volume_spike": round(vol_ratio, 3) if volume_hit else None,
                "possible_reason": "",
                "related_news": [],
                "verify_before_action": [
                    "Confirm the quote timestamp is fresh.",
                    "Read the market resolution rules.",
                    "Cross-check a primary news source — correlation is not cause.",
                    "Do not place a trade from this agent. Research only.",
                ],
            }
        )

    alerts.sort(key=lambda a: abs(a["delta_price"]), reverse=True)
    return {
        "ok": True,
        "baseline": False,
        "alerts": alerts,
        "compared": len(set(current["markets"]) & set(prev_markets)),
        "skipped_cooldown": skipped_cooldown,
        "threshold": threshold,
        "volume_spike": volume_spike,
        "snapshot": current,
    }


def persist_detection(result: dict, store: str | None = None) -> dict:
    root = store_dir(store)
    _save(root / "snapshot.json", result["snapshot"])
    if result.get("alerts"):
        cooldown = _load(root / "cooldown.json", {})
        stamp = _now_iso()
        for alert in result["alerts"]:
            cooldown[alert["market_id"]] = stamp
        _save(root / "cooldown.json", cooldown)
        history = _load(root / "alerts.json", {"alerts": []})
        history.setdefault("alerts", [])
        history["alerts"].extend(result["alerts"])
        history["updated_at"] = stamp
        _save(root / "alerts.json", history)
    result = dict(result)
    result.pop("snapshot", None)
    result["stored_at"] = str(root)
    return result


def fetch_gamma(categories: list[str] | None = None, limit: int = 50, timeout: float = 20.0) -> list[dict]:
    tags = categories or [None]
    markets: list[dict] = []
    for tag in tags:
        params = {"active": "true", "closed": "false", "limit": str(limit), "order": "volume"}
        if tag:
            params["tag"] = tag
        url = f"{GAMMA}/events?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        markets.extend(flatten_events(payload))
    return markets


def init_store(store: str | None = None) -> dict:
    root = store_dir(store)
    if not (root / "watchlist.json").exists():
        _save(
            root / "watchlist.json",
            {
                "categories": ["crypto", "elections", "ai", "sports", "macro"],
                "threshold": DEFAULT_THRESHOLD,
                "volume_spike": DEFAULT_VOLUME_SPIKE,
                "updated_at": _now_iso(),
            },
        )
    if not (root / "snapshot.json").exists():
        _save(root / "snapshot.json", {"taken_at": None, "markets": {}})
    if not (root / "cooldown.json").exists():
        _save(root / "cooldown.json", {})
    return {"ok": True, "store": str(root)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only Polymarket anomaly briefs.")
    parser.add_argument("--store")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    sub.add_parser("watchlist")
    p_wl = sub.add_parser("watchlist-set")
    p_wl.add_argument("--file")
    p_in = sub.add_parser("detect")
    p_in.add_argument("--file", help="JSON markets/events (default stdin)")
    p_in.add_argument("--threshold", type=float)
    p_in.add_argument("--volume-spike", type=float)
    p_fetch = sub.add_parser("fetch-detect")
    p_fetch.add_argument("--threshold", type=float)
    p_fetch.add_argument("--volume-spike", type=float)
    sub.add_parser("alerts-list")
    args = parser.parse_args(argv)
    store = args.store
    init_store(store)
    root = store_dir(store)
    watch = _load(root / "watchlist.json", {})

    if args.cmd == "init":
        print(json.dumps(init_store(store), indent=2))
        return 0
    if args.cmd == "watchlist":
        print(json.dumps(watch, indent=2))
        return 0
    if args.cmd == "watchlist-set":
        payload = _read_json(args.file)
        if not isinstance(payload, dict):
            print(json.dumps({"ok": False, "error": "watchlist JSON must be an object"}))
            return 2
        for key in ("categories", "threshold", "volume_spike"):
            if key in payload:
                watch[key] = payload[key]
        watch["updated_at"] = _now_iso()
        _save(root / "watchlist.json", watch)
        print(json.dumps({"ok": True, "watchlist": watch}, indent=2))
        return 0
    if args.cmd in ("detect", "fetch-detect"):
        if args.cmd == "fetch-detect":
            try:
                markets = fetch_gamma(watch.get("categories") or None)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
                print(json.dumps({"ok": False, "error": str(exc)}))
                return 1
        else:
            payload = _read_json(args.file)
            markets = flatten_events(payload) if payload is not None else []
        threshold = args.threshold if args.threshold is not None else float(watch.get("threshold") or DEFAULT_THRESHOLD)
        spike = args.volume_spike if args.volume_spike is not None else float(watch.get("volume_spike") or DEFAULT_VOLUME_SPIKE)
        previous = _load(root / "snapshot.json", {"markets": {}})
        cooldown = _load(root / "cooldown.json", {})
        result = detect(
            markets,
            previous,
            threshold=threshold,
            volume_spike=spike,
            cooldown=cooldown,
        )
        print(json.dumps(persist_detection(result, store), indent=2))
        return 0
    if args.cmd == "alerts-list":
        print(json.dumps(_load(root / "alerts.json", {"alerts": []}), indent=2))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
