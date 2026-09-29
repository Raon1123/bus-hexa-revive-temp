"""정류소 이름 다국어 사전(ADR-014) — 병합·1:1 검증·alias·캐시·시드 불변식."""

from __future__ import annotations

import json
import os

import pytest

from bushexa.data.constants import STOP_IDS, clean_stop_name
from bushexa.services.stop_name_dict import (
    SEED_PATH,
    StopNameDict,
    StopNameError,
    StopNames,
    validate,
)


def _write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def seed(tmp_path):
    p = tmp_path / "seed.json"
    _write(p, {
        "version": 1,
        "aliases": {"범서중": "범서중학교앞"},
        "en": {"범서중학교앞": "Beomseojunghakgyo-ap", "천상": "Cheonsang"},
    })
    return p


@pytest.fixture
def store(tmp_path, seed):
    return StopNameDict(tmp_path / "data" / "stop_names.json", seed_path=seed)


class TestLoad:
    def test_seed_only_when_override_missing(self, store):
        names = store.load()
        assert names.lookup("천상", "en") == "Cheonsang"

    def test_override_wins_per_entry(self, store):
        _write(store.path, {"en": {"천상": "Cheon-sang", "명촌": "Myeongchon"}})
        names = store.load()
        assert names.lookup("천상", "en") == "Cheon-sang"
        assert names.lookup("명촌", "en") == "Myeongchon"
        assert names.lookup("범서중학교앞", "en") == "Beomseojunghakgyo-ap"  # 시드 항목 유지

    def test_empty_override_is_tombstone(self, store):
        _write(store.path, {"en": {"천상": ""}, "aliases": {"범서중": ""}})
        names = store.load()
        assert names.lookup("천상", "en") is None
        assert names.canonical("범서중") == "범서중"

    def test_corrupt_override_falls_back_to_seed(self, store):
        store.path.parent.mkdir(parents=True, exist_ok=True)
        store.path.write_text("{not json", encoding="utf-8")
        assert store.load().lookup("천상", "en") == "Cheonsang"

    def test_no_files_is_empty(self, tmp_path):
        names = StopNameDict(tmp_path / "x.json", seed_path=tmp_path / "none.json").load()
        assert names.lookup("천상", "en") is None

    def test_cache_invalidated_on_mtime_change(self, store):
        assert store.load().lookup("명촌", "en") is None
        _write(store.path, {"en": {"명촌": "Myeongchon"}})
        st = os.stat(store.path)
        os.utime(store.path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
        assert store.load().lookup("명촌", "en") == "Myeongchon"

    def test_cache_hit_returns_same_object(self, store):
        assert store.load() is store.load()


class TestLookup:
    def test_alias_resolves_to_canonical_translation(self, store):
        assert store.load().lookup("범서중", "en") == "Beomseojunghakgyo-ap"

    def test_ascii_name_passes_through(self):
        names = StopNames(aliases={"울산과학기술원": "UNIST"})
        assert names.lookup("UNIST", "en") == "UNIST"
        assert names.lookup("울산과학기술원", "en") == "UNIST"

    def test_unknown_lang_is_none(self, store):
        assert store.load().lookup("천상", "zh") is None


class TestValidate:
    def test_duplicate_value_case_insensitive_rejected(self):
        problems = validate({"en": {"천상": "Cheonsang", "구영리": "CHEONSANG"}})
        assert any("1:1" in p for p in problems)

    def test_alias_key_cannot_be_translation_key(self):
        problems = validate({"aliases": {"범서중": "범서중학교앞"}, "en": {"범서중": "Beomseo"}})
        assert any("alias" in p for p in problems)

    def test_alias_chain_rejected(self):
        problems = validate({"aliases": {"a": "b", "b": "c"}})
        assert problems

    def test_alias_cycle_rejected(self):
        assert validate({"aliases": {"a": "b", "b": "a"}})

    def test_too_long_and_control_chars_rejected(self):
        assert validate({"en": {"천상": "x" * 61}})
        assert validate({"en": {"천상": "Cheon\nsang"}})

    def test_empty_values_ignored(self):
        assert validate({"en": {"천상": "", "구영리": ""}}) == []


class TestSave:
    def test_save_roundtrip(self, store):
        store.save({"en": {"명촌": "Myeongchon"}})
        on_disk = json.loads(store.path.read_text(encoding="utf-8"))
        assert on_disk["version"] == 1
        assert on_disk["en"] == {"명촌": "Myeongchon"}
        assert store.load().lookup("명촌", "en") == "Myeongchon"

    def test_save_rejects_conflict_with_seed(self, store):
        with pytest.raises(StopNameError) as exc:
            store.save({"en": {"명촌": "CHEONSANG"}})
        assert exc.value.problems
        assert not store.path.exists()

    def test_save_can_resolve_conflict_by_tombstoning_seed(self, store):
        store.save({"en": {"명촌": "Cheonsang", "천상": ""}})
        names = store.load()
        assert names.lookup("명촌", "en") == "Cheonsang"
        assert names.lookup("천상", "en") is None


class TestShippedSeed:
    """저장소에 포함된 시드 자체가 불변식을 만족하고, 표기 결정(ADR-014)을 따르는지."""

    @pytest.fixture(scope="class")
    def names(self, tmp_path_factory):
        return StopNameDict(tmp_path_factory.mktemp("d") / "none.json", seed_path=SEED_PATH).load()

    def test_seed_satisfies_invariants(self):
        raw = json.loads(SEED_PATH.read_text(encoding="utf-8"))
        raw.pop("version")
        assert validate(raw) == []

    def test_every_stop_ids_name_is_translated(self, names):
        missing = sorted({clean_stop_name(v) for v in STOP_IDS.values()
                          if names.lookup(clean_stop_name(v), "en") is None})
        assert missing == []

    def test_unist_unified(self, names):
        for ko in ("울산과학기술원", "과기원", "UNIST"):
            assert names.lookup(ko, "en") == "UNIST"

    def test_beomseo_canonical_is_official_name(self, names):
        assert names.canonical("범서중") == "범서중학교앞"
        assert names.canonical("범서중학교") == "범서중학교앞"
        assert names.lookup("범서중", "en") == names.lookup("범서중학교앞", "en")
