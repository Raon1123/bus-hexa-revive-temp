"""기한형 공지 서비스(bushexa.services.notices) 단위 테스트.

표시 기간(시작 포함·종료일은 그날 끝까지), 시행일 전후 문구 전환, {date}/{dow} 치환,
화면·노선 필터, 정렬, 검증 실패 항목 무시, 파일 부재·파손 폴백, mtime 캐시 갱신.
"""
from __future__ import annotations

import json
import os
from datetime import datetime

import pytest

from bushexa.services import notices as N
from bushexa.time_utils import KST


def _kst(*args) -> datetime:
    return datetime(*args, tzinfo=KST)


def _entry(**over) -> dict:
    base = {
        "id": "n1",
        "kind": "route_change",
        "routes": ["743"],
        "surfaces": ["board"],
        "show_from": None,
        "show_until": "2026-10-31",
        "effective_from": "2026-10-03",
        "text": {"ko": "{date}({dow})부터 변경", "en": "Changes from {date} ({dow})"},
        "text_after": {"ko": "{date}부터 변경됨", "en": "Changed on {date}"},
    }
    base.update(over)
    return base


@pytest.fixture(autouse=True)
def _fresh_cache():
    N._clear_cache()
    yield
    N._clear_cache()


# ── 시각 파싱 ─────────────────────────────────────────────────────────────

def test_parse_when_date_and_datetime():
    assert N.parse_when("2026-10-03") == _kst(2026, 10, 3)
    assert N.parse_when("2026-10-03T07:30") == _kst(2026, 10, 3, 7, 30)
    assert N.parse_when("2026-10-31", end_of_day=True) == _kst(2026, 11, 1)
    assert N.parse_when("") is None and N.parse_when(None) is None


@pytest.mark.parametrize("bad", ["2026/10/03", "2026-13-01", "10월 3일", "2026-10-03 07:30"])
def test_parse_when_rejects_bad_format(bad):
    with pytest.raises(N.NoticeError):
        N.parse_when(bad)


# ── 기간·단계·문구 ─────────────────────────────────────────────────────────

def test_status_window_end_is_inclusive_day():
    n = N.to_notice(N.validate(_entry(show_from="2026-09-26")))
    assert n.status(_kst(2026, 9, 25, 23, 59)) == "scheduled"
    assert n.status(_kst(2026, 9, 26, 0, 0)) == "active"
    assert n.status(_kst(2026, 10, 31, 23, 59)) == "active"
    assert n.status(_kst(2026, 11, 1, 0, 0)) == "expired"


def test_disabled_never_shows():
    n = N.to_notice(N.validate(_entry(enabled=False)))
    assert n.status(_kst(2026, 10, 1)) == "disabled"


def test_text_switches_at_effective_from_and_substitutes_date():
    n = N.to_notice(N.validate(_entry()))
    # 2026-10-03 은 토요일
    assert n.render_text(_kst(2026, 10, 2, 23, 59), "ko") == "10월 3일(토)부터 변경"
    assert n.render_text(_kst(2026, 10, 2, 23, 59), "en") == "Changes from Oct 3 (Sat)"
    assert n.phase(_kst(2026, 10, 2, 23, 59)) == "upcoming"
    assert n.render_text(_kst(2026, 10, 3, 0, 0), "ko") == "10월 3일부터 변경됨"
    assert n.phase(_kst(2026, 10, 3, 0, 0)) == "effective"


def test_text_after_optional_and_lang_fallback_to_ko():
    n = N.to_notice(N.validate(_entry(text={"ko": "한국어만"}, text_after={})))
    assert n.render_text(_kst(2026, 10, 5), "en") == "한국어만"


def test_date_placeholder_uses_show_from_without_effective():
    n = N.to_notice(N.validate(_entry(effective_from=None, show_from="2026-12-24", show_until=None,
                                      text={"ko": "{date} 운행 안내"}, text_after={})))
    assert n.render_text(_kst(2026, 12, 24), "ko") == "12월 24일 운행 안내"


# ── 선택·정렬 ─────────────────────────────────────────────────────────────

def test_select_filters_surface_route_and_orders_by_severity():
    items = [
        N.to_notice(N.validate(_entry(id="a", kind="info", routes=[], surfaces=["all"]))),
        N.to_notice(N.validate(_entry(id="b", kind="suspension", routes=["513"], surfaces=["board", "busno"]))),
        N.to_notice(N.validate(_entry(id="c", kind="route_change", routes=["743"], surfaces=["busno"]))),
        N.to_notice(N.validate(_entry(id="d", kind="info", surfaces=["info"]))),
    ]
    now = _kst(2026, 10, 1)
    board = [r.id for r in N.select_notices(items, surface="board", now=now, lang="ko")]
    assert board == ["b", "a"]
    busno_743 = [r.id for r in N.select_notices(items, surface="busno", now=now, lang="ko", routes=["743"])]
    assert busno_743 == ["c", "a"]          # 513 전용 공지 제외, 전체 대상(a) 포함
    busno_all = [r.id for r in N.select_notices(items, surface="busno", now=now, lang="ko")]
    assert busno_all == ["b", "c", "a"]


def test_priority_breaks_ties_within_kind():
    items = [
        N.to_notice(N.validate(_entry(id="low", kind="info", priority=0))),
        N.to_notice(N.validate(_entry(id="high", kind="info", priority=5))),
    ]
    assert [r.id for r in N.select_notices(items, surface="board", now=_kst(2026, 10, 1), lang="ko")] == ["high", "low"]


# ── 검증 ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("over, msg", [
    ({"id": "bad id"}, "ID"),
    ({"kind": "urgent"}, "종류"),
    ({"surfaces": ["home"]}, "표시 화면"),
    ({"text": {"en": "only en"}}, "ko"),
    ({"link": "https://evil.example"}, "링크"),
    ({"routes": ["7 13"]}, "노선 번호"),
    ({"show_from": "2026-11-01", "show_until": "2026-10-31"}, "표시 종료"),
    ({"routes": "713, 743"}, None),          # 문자열은 쉼표·공백으로 나눈다
])
def test_validate_rejects_bad_input(over, msg):
    if msg is None:
        assert N.validate(_entry(**over))["routes"] == ["713", "743"]
        return
    with pytest.raises(N.NoticeError, match=msg):
        N.validate(_entry(**over))


def test_validate_normalizes_all_surface_and_defaults():
    clean = N.validate({"id": "x", "text": {"ko": "안내"}, "surfaces": ["board", "all"]})
    assert clean["surfaces"] == ["all"]
    assert clean["kind"] == "info" and clean["enabled"] is True and clean["routes"] == []


def test_parse_entries_skips_invalid_and_duplicates():
    data = [_entry(id="ok"), {"id": "broken"}, _entry(id="ok"), "not a dict"]
    assert [e["id"] for e in N.parse_entries(data)] == ["ok"]


# ── 저장소 ───────────────────────────────────────────────────────────────

def test_store_live_over_seed_and_missing_files(tmp_path):
    live, seed = tmp_path / "live.json", tmp_path / "seed.json"
    store = N.NoticeStore(live, seed_path=seed)
    assert store.load() == []
    seed.write_text(json.dumps([_entry(id="seed")]), encoding="utf-8")
    assert [n.id for n in store.load()] == ["seed"]
    store.upsert(_entry(id="mine"))          # 첫 저장 시 seed 항목이 live 로 이관
    assert [n.id for n in store.load()] == ["seed", "mine"]
    assert live.exists()


def test_store_corrupt_file_yields_empty_not_error(tmp_path):
    live = tmp_path / "notices.json"
    live.write_text("{ not json", encoding="utf-8")
    assert N.NoticeStore(live, seed_path=None).load() == []


def test_corrupt_live_falls_back_to_seed_and_blocks_writes(tmp_path):
    """깨진 live → 표시는 seed, 쓰기는 거부(깨진 파일을 덮어써 유실시키지 않음)."""
    live, seed = tmp_path / "live.json", tmp_path / "seed.json"
    seed.write_text(json.dumps([_entry(id="seed")]), encoding="utf-8")
    live.write_text("[{bad json", encoding="utf-8")
    store = N.NoticeStore(live, seed_path=seed)
    assert [n.id for n in store.load()] == ["seed"]
    assert store.health()["corrupt"] is True and store.health()["source"] == "seed"
    for write in (lambda: store.upsert(_entry(id="new")), lambda: store.remove("seed"),
                  lambda: store.set_enabled("seed", False)):
        with pytest.raises(N.NoticeError, match="깨져"):
            write()
    assert live.read_text(encoding="utf-8") == "[{bad json"


def test_rejected_entry_blocks_writes_instead_of_dropping_it(tmp_path):
    live = tmp_path / "live.json"
    live.write_text(json.dumps([_entry(id="keep"), _entry(id="typo", show_until="2026-10-3")]),
                    encoding="utf-8")
    store = N.NoticeStore(live, seed_path=None)
    assert [n.id for n in store.load()] == ["keep"]
    assert any("typo" in r for r in store.health()["rejected"])
    with pytest.raises(N.NoticeError, match="잘못된 항목"):
        store.upsert(_entry(id="new"))
    assert "typo" in live.read_text(encoding="utf-8")


def test_upsert_with_original_id_renames_instead_of_duplicating(tmp_path):
    store = N.NoticeStore(tmp_path / "n.json", seed_path=None)
    store.upsert(_entry(id="old"))
    store.upsert(_entry(id="other"))
    store.upsert(_entry(id="renamed"), original_id="old")
    assert [e["id"] for e in store.load_entries()] == ["renamed", "other"]
    with pytest.raises(N.NoticeError, match="이미 있습니다"):
        store.upsert(_entry(id="other"), original_id="renamed")


def test_seed_drift_and_import(tmp_path):
    live, seed = tmp_path / "live.json", tmp_path / "seed.json"
    seed.write_text(json.dumps([_entry(id="a"), _entry(id="b")]), encoding="utf-8")
    store = N.NoticeStore(live, seed_path=seed)
    store.upsert(_entry(id="mine"))                       # seed a,b 이관 + mine
    assert store.seed_drift() == []
    seed.write_text(json.dumps([_entry(id="a", priority=9), _entry(id="b"), _entry(id="c")]),
                    encoding="utf-8")
    drift = {d["entry"]["id"]: d["state"] for d in store.seed_drift()}
    assert drift == {"a": "differs", "c": "missing"}
    assert store.import_seed("a") and store.get("a")["priority"] == 9
    assert store.import_seed("zzz") is False


def test_cache_detects_same_size_rewrite_within_one_mtime_tick(tmp_path):
    """atomic 저장은 새 inode → mtime·크기가 같아도 감지."""
    live = tmp_path / "n.json"
    store = N.NoticeStore(live, seed_path=None)
    store.upsert(_entry(id="a", priority=1))
    st = live.stat()
    assert store.get("a")["priority"] == 1
    store.upsert(_entry(id="a", priority=2))
    os.utime(live, ns=(st.st_atime_ns, st.st_mtime_ns))    # 같은 mtime 틱 흉내
    assert live.stat().st_size == st.st_size
    assert store.get("a")["priority"] == 2


def test_write_uses_cross_worker_lock(tmp_path, monkeypatch):
    calls = []
    real = N.locked_update_json
    monkeypatch.setattr(N, "locked_update_json", lambda *a, **k: (calls.append(a[0]), real(*a, **k))[1])
    N.NoticeStore(tmp_path / "n.json", seed_path=None).upsert(_entry(id="a"))
    assert calls == [tmp_path / "n.json"]


@pytest.mark.parametrize("over, msg", [
    ({"show_until": "9999-12-31"}, "2000~2100"),
    ({"effective_from": "1999-01-01"}, "2000~2100"),
    ({"priority": 1e400}, "정수"),
    ({"priority": True}, "정수"),
    ({"priority": 1.5}, "정수"),
    ({"priority": 5000}, "-1000~1000"),
    ({"enabled": "false"}, "true/false"),
    ({"text_after": {"en": "EN only"}}, "같은 언어"),
    ({"effective_from": None, "show_from": None}, "시행일이나 표시 시작일"),
])
def test_validate_rejects_overflow_language_gap_and_unanchored_placeholders(over, msg):
    with pytest.raises(N.NoticeError, match=msg):
        N.validate(_entry(**over))


def test_one_overflowing_entry_does_not_hide_the_others(tmp_path):
    live = tmp_path / "n.json"
    live.write_text('[' + json.dumps(_entry(id="ok")) + ',{"id":"b","text":{"ko":"x"},"priority":1e400}]',
                    encoding="utf-8")
    assert [n.id for n in N.NoticeStore(live, seed_path=None).load()] == ["ok"]


def test_render_after_text_per_language_fallback():
    """시행 후 문구가 (검증을 우회해) 한 언어만 있어도 다른 언어 사용자는 자기 언어 본문을 본다."""
    n = N.Notice(id="x", kind="info", routes=(), surfaces=("all",), show_from=None, show_until=None,
                 effective_from=_kst(2026, 10, 3), text={"ko": "전", "en": "before"},
                 text_after={"en": "after"})
    now = _kst(2026, 10, 5)
    assert n.render_text(now, "en") == "after"
    assert n.render_text(now, "ko") == "전"


def test_store_upsert_toggle_remove(tmp_path):
    store = N.NoticeStore(tmp_path / "notices.json", seed_path=None)
    store.upsert(_entry(id="a"))
    store.upsert(_entry(id="a", kind="warning"))
    assert [e["kind"] for e in store.load_entries()] == ["warning"]
    assert store.set_enabled("a", False) and store.load()[0].enabled is False
    assert store.set_enabled("zzz", True) is False
    assert store.remove("a") and store.load() == []
    assert store.remove("a") is False


def test_store_cache_reloads_when_file_changes(tmp_path):
    """다른 워커가 저장한 변경을 (mtime_ns, size) 서명으로 감지한다."""
    live = tmp_path / "notices.json"
    live.write_text(json.dumps([_entry(id="one")]), encoding="utf-8")
    store = N.NoticeStore(live, seed_path=None)
    assert [n.id for n in store.load()] == ["one"]
    live.write_text(json.dumps([_entry(id="two"), _entry(id="three")]), encoding="utf-8")
    st = live.stat()
    os.utime(live, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
    assert [n.id for n in store.load()] == ["two", "three"]


def test_shipped_seed_is_valid():
    """이미지에 구워지는 seed 공지가 스키마를 통과한다(잘못되면 조용히 사라지므로)."""
    raw = json.loads(N.SEED_PATH.read_text(encoding="utf-8"))
    assert len(N.parse_entries(raw)) == len(raw) >= 1
