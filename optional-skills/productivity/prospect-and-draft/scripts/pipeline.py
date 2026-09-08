#!/usr/bin/env python3
"""Durable prospect pipeline for the prospect-and-draft skill.

Cron runs are stateless. Contacted domains and prior rows live here, not in
MEMORY.md. Python stdlib only. Prints JSON unless --format md/csv.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

SKILL = "prospect-and-draft"
REQUIRED = ("company", "why_they_need_offer", "personalized_angle")


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
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def normalize_domain(value: str) -> str:
    text = (value or "").strip().lower()
    if not text:
        return ""
    if "://" not in text:
        text = "https://" + text
    host = urlparse(text).hostname or ""
    if host.startswith("www."):
        host = host[4:]
    return host


def _read_json(path: str | None):
    raw = Path(path).read_text(encoding="utf-8") if path and path != "-" else sys.stdin.read()
    raw = raw.strip()
    if not raw:
        return None
    return json.loads(raw)


def init_store(store: str | None = None) -> dict:
    root = store_dir(store)
    contacted_path = root / "contacted.json"
    prospects_path = root / "prospects.json"
    icp_path = root / "icp.json"
    if not contacted_path.exists():
        _save(contacted_path, {"domains": [], "updated_at": _now()})
    if not prospects_path.exists():
        _save(prospects_path, {"rows": [], "updated_at": _now()})
    if not icp_path.exists():
        _save(
            icp_path,
            {
                "offer": "",
                "segments": [],
                "qualifiers": [],
                "disqualifiers": [],
                "voice": "direct, specific, no hype",
                "daily_cap": 25,
                "updated_at": _now(),
            },
        )
    return {"ok": True, "store": str(root)}


def set_icp(payload: dict, store: str | None = None) -> dict:
    root = store_dir(store)
    current = _load(root / "icp.json", {})
    if not isinstance(payload, dict):
        return {"ok": False, "error": "ICP payload must be an object"}
    for key in ("offer", "segments", "qualifiers", "disqualifiers", "voice", "daily_cap"):
        if key in payload:
            current[key] = payload[key]
    current["updated_at"] = _now()
    _save(root / "icp.json", current)
    return {"ok": True, "icp": current}


def contacted_add(domains: list[str], store: str | None = None) -> dict:
    root = store_dir(store)
    data = _load(root / "contacted.json", {"domains": []})
    existing = {normalize_domain(d) for d in data.get("domains", []) if normalize_domain(d)}
    added = []
    for raw in domains:
        domain = normalize_domain(raw)
        if domain and domain not in existing:
            existing.add(domain)
            added.append(domain)
    data["domains"] = sorted(existing)
    data["updated_at"] = _now()
    _save(root / "contacted.json", data)
    return {"ok": True, "added": added, "total": len(data["domains"])}


def upsert_prospects(rows: list[dict], store: str | None = None) -> dict:
    if not isinstance(rows, list):
        return {"ok": False, "error": "expected a JSON array of prospect objects"}
    root = store_dir(store)
    contacted = {
        normalize_domain(d)
        for d in _load(root / "contacted.json", {"domains": []}).get("domains", [])
    }
    bundle = _load(root / "prospects.json", {"rows": []})
    by_domain = {}
    for row in bundle.get("rows", []):
        domain = normalize_domain(row.get("domain") or row.get("website") or "")
        if domain:
            by_domain[domain] = row

    added = updated = skipped_contacted = skipped_invalid = 0
    for raw in rows:
        if not isinstance(raw, dict):
            skipped_invalid += 1
            continue
        domain = normalize_domain(raw.get("domain") or raw.get("website") or "")
        missing = [k for k in REQUIRED if not str(raw.get(k) or "").strip()]
        if not domain or missing:
            skipped_invalid += 1
            continue
        if domain in contacted:
            skipped_contacted += 1
            continue
        variants = raw.get("message_variants") or []
        if isinstance(variants, str):
            variants = [variants]
        row = {
            "company": str(raw.get("company") or "").strip(),
            "website": str(raw.get("website") or f"https://{domain}").strip(),
            "domain": domain,
            "segment": str(raw.get("segment") or "").strip(),
            "what_they_sell": str(raw.get("what_they_sell") or "").strip(),
            "why_they_need_offer": str(raw.get("why_they_need_offer") or "").strip(),
            "personalized_angle": str(raw.get("personalized_angle") or "").strip(),
            "message_variants": [str(v).strip() for v in variants if str(v).strip()][:3],
            "source_url": str(raw.get("source_url") or "").strip(),
            "fit_score": raw.get("fit_score"),
            "status": str(raw.get("status") or "draft").strip() or "draft",
            "updated_at": _now(),
        }
        if domain in by_domain:
            prev = by_domain[domain]
            if not row["message_variants"]:
                row["message_variants"] = prev.get("message_variants") or []
            row["created_at"] = prev.get("created_at") or _now()
            by_domain[domain] = row
            updated += 1
        else:
            row["created_at"] = _now()
            by_domain[domain] = row
            added += 1

    bundle["rows"] = sorted(by_domain.values(), key=lambda r: r.get("company", "").lower())
    bundle["updated_at"] = _now()
    _save(root / "prospects.json", bundle)
    return {
        "ok": True,
        "added": added,
        "updated": updated,
        "skipped_contacted": skipped_contacted,
        "skipped_invalid": skipped_invalid,
        "total": len(bundle["rows"]),
    }


def list_prospects(store: str | None = None, status: str | None = None) -> dict:
    rows = _load(store_dir(store) / "prospects.json", {"rows": []}).get("rows", [])
    if status:
        rows = [r for r in rows if r.get("status") == status]
    return {"ok": True, "count": len(rows), "rows": rows}


def export_rows(rows: list[dict], fmt: str) -> str:
    fields = [
        "company",
        "website",
        "segment",
        "what_they_sell",
        "why_they_need_offer",
        "personalized_angle",
        "message_variants",
        "source_url",
        "fit_score",
        "status",
    ]
    if fmt == "json":
        return json.dumps(rows, indent=2, ensure_ascii=False)
    flat = []
    for row in rows:
        item = dict(row)
        variants = item.get("message_variants") or []
        item["message_variants"] = " | ".join(variants)
        flat.append(item)
    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(flat)
        return buf.getvalue()
    # markdown
    header = "| " + " | ".join(fields) + " |"
    sep = "| " + " | ".join("---" for _ in fields) + " |"
    lines = [header, sep]
    for item in flat:
        lines.append("| " + " | ".join(str(item.get(f, "") or "").replace("|", "/") for f in fields) + " |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prospect pipeline store (dedupe + drafts, no send).")
    parser.add_argument("--store", help="Override store directory (default $HERMES_HOME/operator/prospect-and-draft)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init")
    sub.add_parser("show-icp")
    p_icp = sub.add_parser("set-icp")
    p_icp.add_argument("--file", help="JSON file (default stdin)")

    p_add = sub.add_parser("contacted-add")
    p_add.add_argument("domains", nargs="+")
    sub.add_parser("contacted-list")

    p_up = sub.add_parser("upsert")
    p_up.add_argument("--file", help="JSON array file (default stdin)")

    p_list = sub.add_parser("list")
    p_list.add_argument("--status")

    p_ex = sub.add_parser("export")
    p_ex.add_argument("--format", choices=("json", "md", "csv"), default="md")
    p_ex.add_argument("--status")

    p_mark = sub.add_parser("mark-contacted")
    p_mark.add_argument("domains", nargs="+")

    args = parser.parse_args(argv)
    store = args.store

    if args.cmd == "init":
        print(json.dumps(init_store(store), indent=2))
        return 0
    if args.cmd == "show-icp":
        init_store(store)
        print(json.dumps(_load(store_dir(store) / "icp.json", {}), indent=2))
        return 0
    if args.cmd == "set-icp":
        payload = _read_json(args.file)
        print(json.dumps(set_icp(payload or {}, store), indent=2))
        return 0
    if args.cmd == "contacted-add":
        print(json.dumps(contacted_add(args.domains, store), indent=2))
        return 0
    if args.cmd == "contacted-list":
        init_store(store)
        print(json.dumps(_load(store_dir(store) / "contacted.json", {}), indent=2))
        return 0
    if args.cmd == "upsert":
        payload = _read_json(args.file)
        rows = payload if isinstance(payload, list) else (payload.get("rows") if isinstance(payload, dict) else None)
        print(json.dumps(upsert_prospects(rows or [], store), indent=2))
        return 0
    if args.cmd == "list":
        print(json.dumps(list_prospects(store, args.status), indent=2))
        return 0
    if args.cmd == "export":
        result = list_prospects(store, args.status)
        print(export_rows(result["rows"], args.format))
        return 0
    if args.cmd == "mark-contacted":
        added = contacted_add(args.domains, store)
        # drop those domains from the live draft table
        bundle = _load(store_dir(store) / "prospects.json", {"rows": []})
        marked = {normalize_domain(d) for d in args.domains}
        kept = []
        for row in bundle.get("rows", []):
            if normalize_domain(row.get("domain") or "") in marked:
                row["status"] = "contacted"
            kept.append(row)
        bundle["rows"] = kept
        bundle["updated_at"] = _now()
        _save(store_dir(store) / "prospects.json", bundle)
        added["prospects_marked"] = sorted(marked)
        print(json.dumps(added, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
