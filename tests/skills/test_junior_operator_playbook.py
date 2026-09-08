"""Invariants for the junior-operator optional skill pack.

Asserts how stores, gates, and scoring relate — not frozen catalogs.
No live network. Stdlib + pytest only.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
PACK = REPO / "optional-skills" / "productivity"
SKILLS = REPO / "skills"
OPTIONAL = REPO / "optional-skills"

PACK_SKILLS = [
    "junior-operator",
    "prospect-and-draft",
    "content-research",
    "trend-scout",
    "market-alert",
    "client-ops",
]

SCRIPTS = {
    "junior-operator": PACK / "junior-operator" / "scripts" / "choose_play.py",
    "prospect-and-draft": PACK / "prospect-and-draft" / "scripts" / "pipeline.py",
    "content-research": PACK / "content-research" / "scripts" / "briefing.py",
    "trend-scout": PACK / "trend-scout" / "scripts" / "digest.py",
    "market-alert": PACK / "market-alert" / "scripts" / "alerts.py",
    "client-ops": PACK / "client-ops" / "scripts" / "ops.py",
}


def _frontmatter(skill_md: Path) -> dict:
    text = skill_md.read_text(encoding="utf-8")
    match = text.startswith("---")
    assert match, f"{skill_md} missing frontmatter"
    end = text.find("\n---\n", 3)
    assert end != -1, f"{skill_md} unclosed frontmatter"
    return yaml.safe_load(text[4:end])


def _load_script(name: str):
    path = SCRIPTS[name]
    spec = importlib.util.spec_from_file_location(f"jo_{name.replace('-', '_')}", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def store(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    monkeypatch.setenv("HERMES_HOME", str(home))
    return home / "operator"


@pytest.mark.parametrize("name", PACK_SKILLS)
def test_frontmatter_contract(name):
    skill_md = PACK / name / "SKILL.md"
    fm = _frontmatter(skill_md)
    assert fm["name"] == name
    desc = fm["description"].strip()
    assert desc.endswith(".")
    assert len(desc) <= 60, f"{name}: description is {len(desc)} chars: {desc!r}"
    assert set(fm.get("platforms") or []) <= {"linux", "macos", "windows"}
    assert fm.get("metadata", {}).get("hermes", {}).get("category") == "productivity"


@pytest.mark.parametrize("name", PACK_SKILLS)
def test_script_exists_and_compiles(name):
    import py_compile

    path = SCRIPTS[name]
    assert path.exists(), f"missing {path}"
    py_compile.compile(str(path), doraise=True)
    body = (PACK / name / "SKILL.md").read_text(encoding="utf-8")
    rel = f"scripts/{path.name}"
    assert rel in body, f"{name}: SKILL.md does not mention {rel}"


def test_related_skills_resolve():
    known = {p.parent.name for p in SKILLS.rglob("SKILL.md")} | {
        p.parent.name for p in OPTIONAL.rglob("SKILL.md")
    }
    for name in PACK_SKILLS:
        related = (
            _frontmatter(PACK / name / "SKILL.md")
            .get("metadata", {})
            .get("hermes", {})
            .get("related_skills", [])
        )
        assert related, f"{name} should cross-link related_skills"
        for rel in related:
            assert rel in known, f"{name}: related skill {rel!r} does not exist"


def test_choose_play_table():
    mod = _load_script("junior-operator")
    hit = mod.recommend("creator")
    assert hit["ok"] is True
    assert hit["first_skill"] == "content-research"
    assert "install" in hit
    miss = mod.recommend("spaceship")
    assert miss["ok"] is False
    assert "known" in miss


def test_pipeline_dedupes_and_skips_contacted(store):
    mod = _load_script("prospect-and-draft")
    root = str(store / "prospect-and-draft")
    mod.init_store(root)
    first = mod.upsert_prospects(
        [
            {
                "company": "Acme",
                "website": "https://www.acme.test",
                "why_they_need_offer": "No outbound motion",
                "personalized_angle": "Their changelog is the whole funnel",
            }
        ],
        root,
    )
    again = mod.upsert_prospects(
        [
            {
                "company": "Acme Inc",
                "website": "acme.test",
                "why_they_need_offer": "Still no outbound",
                "personalized_angle": "Same domain, updated angle",
            }
        ],
        root,
    )
    assert first["added"] == 1
    assert again["added"] == 0
    assert again["updated"] == 1
    listed = mod.list_prospects(root)
    assert listed["count"] == 1
    assert listed["rows"][0]["domain"] == "acme.test"

    mod.contacted_add(["https://www.acme.test/about"], root)
    skipped = mod.upsert_prospects(
        [
            {
                "company": "Acme",
                "website": "https://acme.test",
                "why_they_need_offer": "x",
                "personalized_angle": "y",
            }
        ],
        root,
    )
    assert skipped["skipped_contacted"] == 1
    assert skipped["added"] == 0


def test_pipeline_rejects_rows_without_why(store):
    mod = _load_script("prospect-and-draft")
    root = str(store / "prospect-and-draft")
    result = mod.upsert_prospects(
        [{"company": "Nope", "website": "https://nope.test", "personalized_angle": "hi"}],
        root,
    )
    assert result["skipped_invalid"] == 1
    assert result["total"] == 0


def test_briefing_outperformance_and_novelty(store):
    mod = _load_script("content-research")
    root = str(store / "content-research")
    mod.init_store(root)
    mod.ingest_videos(
        [
            {
                "title": "Baseline clip one",
                "channel": "A",
                "views": 1000,
                "video_id": "a0",
                "channel_avg_views": 2000,
            },
            {
                "title": "Quiet shipping habits",
                "channel": "A",
                "views": 8000,
                "video_id": "a1",
                "channel_avg_views": 2000,
            },
            {
                "title": "Breakout hook experiment",
                "channel": "A",
                "views": 7000,
                "video_id": "a2",
                "channel_avg_views": 2000,
            },
        ],
        root,
    )
    mod.published_add(["Quiet shipping habits"], root)
    result = mod.brief(root, top=3, min_ratio=1.5)
    winner_titles = {row["title"] for row in result["winners"]}
    assert "Breakout hook experiment" in winner_titles
    assert "Quiet shipping habits" in winner_titles
    assert all(row["outperformance_ratio"] >= 1.5 for row in result["winners"])
    top_ideas = [i["title"] for i in result["top_3_this_week"]]
    assert "Quiet shipping habits" not in top_ideas
    assert "Breakout hook experiment" in top_ideas


def test_digest_freshness_and_covered(store):
    mod = _load_script("trend-scout")
    root = str(store / "trend-scout")
    mod.init_store(root)
    mod.set_keywords(["hermes"], root)
    now = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    fresh = {
        "id": "hn:1",
        "source": "hacker-news",
        "title": "Hermes operator workflows",
        "url": "https://example.test/fresh",
        "published_at": (now - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    stale = {
        **fresh,
        "id": "hn:2",
        "url": "https://example.test/stale",
        "published_at": (now - timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    other = {
        "id": "hn:3",
        "source": "x",
        "title": "Unrelated cooking blog",
        "url": "https://example.test/food",
        "published_at": (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    first = mod.digest([fresh, stale, other], root, max_age_hours=24, now=now)
    assert first["count"] == 1
    assert first["items"][0]["id"] == "hn:1"
    assert first["dropped"]["stale"] == 1
    assert first["dropped"]["irrelevant"] == 1

    mod.mark_covered(["hn:1"], root)
    second = mod.digest([fresh], root, max_age_hours=24, now=now)
    assert second["count"] == 0
    assert second["dropped"]["covered"] == 1


def test_market_alert_baseline_threshold_cooldown(store):
    mod = _load_script("market-alert")
    markets_v1 = [
        {
            "id": "m1",
            "question": "Will X happen?",
            "slug": "will-x",
            "outcomePrices": '["0.50", "0.50"]',
            "volume": 1000,
            "category": "ai",
        }
    ]
    first = mod.detect(markets_v1, previous=None, threshold=0.08)
    assert first["baseline"] is True
    assert first["alerts"] == []

    moved = [
        {
            **markets_v1[0],
            "outcomePrices": '["0.70", "0.30"]',
            "volume": 1000,
        }
    ]
    second = mod.detect(moved, previous=first["snapshot"], threshold=0.08)
    assert second["baseline"] is False
    assert len(second["alerts"]) == 1
    assert abs(second["alerts"][0]["delta_price"] - 0.20) < 1e-6

    quiet = [
        {
            **markets_v1[0],
            "outcomePrices": '["0.55", "0.45"]',
            "volume": 1000,
        }
    ]
    third = mod.detect(quiet, previous=first["snapshot"], threshold=0.08)
    assert third["alerts"] == []

    now = datetime(2026, 9, 8, 12, tzinfo=timezone.utc)
    cooled = mod.detect(
        moved,
        previous=first["snapshot"],
        threshold=0.08,
        cooldown={"m1": now.strftime("%Y-%m-%dT%H:%M:%SZ")},
        cooldown_hours=12,
        now=now + timedelta(hours=1),
    )
    assert cooled["alerts"] == []
    assert cooled["skipped_cooldown"] == 1


def test_client_ops_memory_split_and_send_gate(store):
    mod = _load_script("client-ops")
    root = str(store / "client-ops")
    assert mod.classify_fact("Follow up Friday about the invoice") == "transient"
    assert mod.classify_fact("invoice") == "unknown"
    assert mod.classify_fact("Prefers Net-30 billing, always invoice on the 1st") == "durable"

    refused = mod.set_pref("acme", "next", "Follow up Friday about the invoice", root)
    assert refused["ok"] is False

    saved = mod.set_pref("acme", "billing", "Prefers Net-30 billing", root)
    assert saved["ok"] is True

    result = mod.ingest_call(
        {
            "client": "acme",
            "follow_up_draft": "Thanks — I'll send the timeline Thursday.",
            "actions": [
                {"action": "Send revised timeline", "owner": "Alex", "deadline": "2026-09-10"}
            ],
            "durable_prefs": [{"key": "voice", "value": "Always short emails, never slang"}],
            "send_approved": False,
        },
        root,
    )
    assert result["ok"] is True
    assert result["send_gate"] == "blocked"
    assert result["follow_up"]["status"] == "queued"
    assert result["actions_added"][0]["owner"] == "Alex"

    due = mod.due_actions(
        root,
        within_hours=72,
        now=datetime(2026, 9, 8, tzinfo=timezone.utc),
    )
    assert due["count"] == 1

    audit = mod.audit_prefs(root)
    assert audit["ok"] is True
    assert all(item["classification"] != "durable" for item in audit["flagged"])


def test_normalize_domain_strips_www():
    mod = _load_script("prospect-and-draft")
    assert mod.normalize_domain("https://WWW.Acme.test/path") == "acme.test"
    assert mod.normalize_domain("acme.test") == "acme.test"
