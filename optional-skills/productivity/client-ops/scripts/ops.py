#!/usr/bin/env python3
"""Client-ops store: durable prefs vs transient tasks, no silent sends.

Enforces the video's memory split in code: preferences persist, task progress
does not. Follow-up drafts stay queued until send_approved=true — this script
never sends mail or messages.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SKILL = "client-ops"
TRANSIENT_HINTS = (
    "deadline",
    "due ",
    "this week",
    "today",
    "todo",
    "follow up",
    "follow-up",
    "in progress",
    "waiting on",
    "next step",
    "action item",
    "remind me",
)
DURABLE_HINTS = (
    "prefer",
    "always",
    "never",
    "timezone",
    "voice",
    "billing",
    "decision",
    "do not",
    "don't",
    "pronoun",
    "nickname",
    "standing",
)


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
    for candidate in (text, text.replace("Z", "+00:00"), f"{text}T00:00:00+00:00"):
        try:
            dt = datetime.fromisoformat(candidate)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def classify_fact(text: str) -> str:
    blob = (text or "").lower()
    durable = any(h in blob for h in DURABLE_HINTS)
    transient = any(h in blob for h in TRANSIENT_HINTS)
    if transient and not durable:
        return "transient"
    if durable:
        return "durable"
    return "unknown"


def init_store(store: str | None = None) -> dict:
    root = store_dir(store)
    if not (root / "prefs.json").exists():
        _save(root / "prefs.json", {"clients": {}, "updated_at": _now_iso()})
    if not (root / "actions.json").exists():
        _save(root / "actions.json", {"items": [], "updated_at": _now_iso()})
    if not (root / "drafts.json").exists():
        _save(root / "drafts.json", {"items": [], "updated_at": _now_iso()})
    return {"ok": True, "store": str(root)}


def set_pref(client: str, key: str, value: str, store: str | None = None, force: bool = False) -> dict:
    kind = classify_fact(f"{key} {value}")
    if kind == "transient" and not force:
        return {
            "ok": False,
            "error": "refused: looks like transient task progress, not a durable preference",
            "classification": kind,
            "hint": "Put deadlines and next-steps in actions, not prefs. Pass force=true only for a memory audit override.",
        }
    root = store_dir(store)
    init_store(store)
    data = _load(root / "prefs.json", {"clients": {}})
    clients = data.setdefault("clients", {})
    book = clients.setdefault(client, {})
    book[key] = {"value": value, "classification": kind, "updated_at": _now_iso()}
    data["updated_at"] = _now_iso()
    _save(root / "prefs.json", data)
    return {"ok": True, "client": client, "key": key, "classification": kind}


def ingest_call(payload: dict, store: str | None = None) -> dict:
    if not isinstance(payload, dict):
        return {"ok": False, "error": "call payload must be an object"}
    client = str(payload.get("client") or "").strip()
    if not client:
        return {"ok": False, "error": "client is required"}
    root = store_dir(store)
    init_store(store)

    prefs_result = []
    rejected_prefs = []
    for item in payload.get("durable_prefs") or []:
        if isinstance(item, str):
            key, _, value = item.partition(":")
            key, value = key.strip() or item, value.strip() or item
        elif isinstance(item, dict):
            key = str(item.get("key") or "").strip()
            value = str(item.get("value") or "").strip()
        else:
            continue
        if not key or not value:
            continue
        saved = set_pref(client, key, value, store)
        (prefs_result if saved.get("ok") else rejected_prefs).append(saved)

    actions_bundle = _load(root / "actions.json", {"items": []})
    added_actions = []
    for raw in payload.get("actions") or []:
        if not isinstance(raw, dict):
            continue
        action = str(raw.get("action") or "").strip()
        if not action:
            continue
        row = {
            "id": f"act-{len(actions_bundle['items']) + len(added_actions) + 1:04d}",
            "client": client,
            "action": action,
            "owner": str(raw.get("owner") or "").strip(),
            "deadline": str(raw.get("deadline") or "").strip(),
            "source_call": str(payload.get("source_call") or payload.get("call_id") or "").strip(),
            "status": str(raw.get("status") or "open").strip() or "open",
            "created_at": _now_iso(),
        }
        added_actions.append(row)
    actions_bundle["items"].extend(added_actions)
    actions_bundle["updated_at"] = _now_iso()
    _save(root / "actions.json", actions_bundle)

    draft = str(payload.get("follow_up_draft") or payload.get("follow_up_message_draft") or "").strip()
    send_approved = bool(payload.get("send_approved"))
    draft_row = None
    if draft:
        drafts = _load(root / "drafts.json", {"items": []})
        draft_row = {
            "id": f"draft-{len(drafts['items']) + 1:04d}",
            "client": client,
            "body": draft,
            "status": "approved" if send_approved else "queued",
            "send_approved": send_approved,
            "created_at": _now_iso(),
        }
        if send_approved:
            # Still do not send. Mark as ready-for-human-copy only.
            draft_row["note"] = "Approved for the human to send. This script never sends."
        drafts["items"].append(draft_row)
        drafts["updated_at"] = _now_iso()
        _save(root / "drafts.json", drafts)

    return {
        "ok": True,
        "client": client,
        "prefs_saved": prefs_result,
        "prefs_rejected": rejected_prefs,
        "actions_added": added_actions,
        "follow_up": draft_row,
        "send_gate": "blocked" if draft and not send_approved else ("human_sends" if draft else "none"),
    }


def due_actions(store: str | None = None, within_hours: float = 24.0, now: datetime | None = None) -> dict:
    root = store_dir(store)
    init_store(store)
    clock = now or _now()
    horizon = clock + timedelta(hours=within_hours)
    items = []
    for row in _load(root / "actions.json", {"items": []}).get("items", []):
        if row.get("status") not in (None, "", "open"):
            continue
        deadline = parse_dt(row.get("deadline"))
        if deadline is None:
            continue
        if deadline <= horizon:
            items.append({**row, "overdue": deadline < clock})
    items.sort(key=lambda r: r.get("deadline") or "")
    return {"ok": True, "count": len(items), "within_hours": within_hours, "items": items}


def complete_action(action_id: str, store: str | None = None) -> dict:
    root = store_dir(store)
    bundle = _load(root / "actions.json", {"items": []})
    found = False
    for row in bundle.get("items", []):
        if row.get("id") == action_id:
            row["status"] = "done"
            row["completed_at"] = _now_iso()
            found = True
            break
    if not found:
        return {"ok": False, "error": f"unknown action {action_id}"}
    bundle["updated_at"] = _now_iso()
    _save(root / "actions.json", bundle)
    return {"ok": True, "id": action_id}


def audit_prefs(store: str | None = None) -> dict:
    root = store_dir(store)
    init_store(store)
    flagged = []
    clients = _load(root / "prefs.json", {"clients": {}}).get("clients", {})
    for client, book in clients.items():
        for key, meta in (book or {}).items():
            value = meta.get("value") if isinstance(meta, dict) else str(meta)
            kind = classify_fact(f"{key} {value}")
            if kind != "durable":
                flagged.append({"client": client, "key": key, "value": value, "classification": kind})
    return {"ok": True, "flagged": flagged, "count": len(flagged)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Client-ops durable store + send gate.")
    parser.add_argument("--store")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    p_set = sub.add_parser("pref-set")
    p_set.add_argument("client")
    p_set.add_argument("key")
    p_set.add_argument("value")
    p_set.add_argument("--force", action="store_true")
    p_get = sub.add_parser("prefs")
    p_get.add_argument("client", nargs="?")
    p_in = sub.add_parser("ingest-call")
    p_in.add_argument("--file")
    p_due = sub.add_parser("due")
    p_due.add_argument("--within-hours", type=float, default=24.0)
    p_done = sub.add_parser("complete")
    p_done.add_argument("action_id")
    sub.add_parser("audit")
    p_cls = sub.add_parser("classify")
    p_cls.add_argument("text")
    args = parser.parse_args(argv)
    store = args.store

    if args.cmd == "init":
        print(json.dumps(init_store(store), indent=2))
        return 0
    if args.cmd == "pref-set":
        print(json.dumps(set_pref(args.client, args.key, args.value, store, force=args.force), indent=2))
        return 0
    if args.cmd == "prefs":
        init_store(store)
        data = _load(store_dir(store) / "prefs.json", {"clients": {}})
        if args.client:
            print(json.dumps({"ok": True, "client": args.client, "prefs": data.get("clients", {}).get(args.client, {})}, indent=2))
        else:
            print(json.dumps(data, indent=2))
        return 0
    if args.cmd == "ingest-call":
        print(json.dumps(ingest_call(_read_json(args.file) or {}, store), indent=2))
        return 0
    if args.cmd == "due":
        print(json.dumps(due_actions(store, within_hours=args.within_hours), indent=2))
        return 0
    if args.cmd == "complete":
        print(json.dumps(complete_action(args.action_id, store), indent=2))
        return 0
    if args.cmd == "audit":
        print(json.dumps(audit_prefs(store), indent=2))
        return 0
    if args.cmd == "classify":
        print(json.dumps({"text": args.text, "classification": classify_fact(args.text)}))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
