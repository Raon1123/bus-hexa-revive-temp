"""정류소 이름 다국어 사전(ADR-014) — 한국어 정식명 ↔ 대상 언어명의 1:1 사전 + 한국어 약칭 alias.

정류소 이름은 고유명사라 운영자가 관리자 화면에서 직접 고친다. 코드에는 시드
(`bushexa/data/stop_names.seed.json`)만 두고, 편집분은 `<data_dir>/stop_names.json`에 저장한다.

파일 구조::

    {"version": 1,
     "aliases": {"범서중": "범서중학교앞", ...},     # 한국어 약칭 → 한국어 정식명
     "en": {"범서중학교앞": "Beomseojunghakgyo-ap", ...}}

병합 규칙(항목 단위): **override > seed**. override의 빈 문자열은 "번역 없음/alias 없음"을
명시하는 묘비(tombstone)라 시드 값을 가린다. 시드에 새로 추가된 항목은 기존 override와 함께
자동 반영된다(`via_overrides.json`과 같은 모델).

불변식(`validate`):
- 언어별 값 유일(대소문자·앞뒤 공백 무시) — 영어 이름만 보고 한국어 정류소를 되짚을 수 있어야 한다.
- alias 키는 번역 사전 키가 될 수 없다(약칭은 정식명을 거쳐서만 번역).
- alias는 1단계만: 대상이 또 다른 alias면 거부(순환 포함).
- 값 길이 ≤ ``MAX_LEN``, 제어문자 금지.

번역 적용은 렌더 계층(`bushexa.web.i18n.localize_stop`)에서만 한다. STOP_IDS·recorder·DB의
한국어 원문은 이 모듈과 무관하게 그대로다.
"""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path

from bushexa.fileio import atomic_write_json, read_json

log = logging.getLogger(__name__)

MAX_LEN = 60
FILE_VERSION = 1
SEED_PATH = Path(__file__).resolve().parent.parent / "data" / "stop_names.seed.json"


def default_stop_names_path(data_dir) -> Path:
    """override 파일의 기본 경로(`<data_dir>/stop_names.json`)."""
    return Path(data_dir) / "stop_names.json"


class StopNameError(ValueError):
    """저장 거부 — ``problems``에 사람이 읽을 위반 목록."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class StopNames:
    """병합이 끝난 유효 사전. 묘비(빈 값)는 제거된 상태."""

    aliases: dict[str, str] = field(default_factory=dict)
    langs: dict[str, dict[str, str]] = field(default_factory=dict)

    def canonical(self, name: str) -> str:
        """약칭이면 정식명, 아니면 그대로."""
        return self.aliases.get(name, name)

    def lookup(self, name: str, lang: str) -> str | None:
        """alias 해소 후 *lang* 사전 조회. 라틴 문자로만 된 이름(``UNIST``)은 그대로 반환."""
        canon = self.canonical(name)
        if canon.isascii():
            return canon
        return self.langs.get(lang, {}).get(canon)


EMPTY = StopNames()


def _normalize(raw: object) -> dict:
    """파일 내용 → ``{"aliases": {...}, "<lang>": {...}}``(문자열 값만, 공백 정리). 파손 항목은 버린다."""
    out: dict[str, dict[str, str]] = {}
    if not isinstance(raw, dict):
        return out
    for section, entries in raw.items():
        if section == "version" or not isinstance(entries, dict):
            continue
        out[str(section)] = {
            str(k).strip(): v.strip() for k, v in entries.items()
            if isinstance(v, str) and str(k).strip()
        }
    return out


def _merge(seed: dict, override: dict) -> dict:
    merged: dict[str, dict[str, str]] = {}
    for section in set(seed) | set(override):
        merged[section] = {**seed.get(section, {}), **override.get(section, {})}
    return merged


def _to_stop_names(data: dict) -> StopNames:
    aliases = {k: v for k, v in data.get("aliases", {}).items() if v}
    langs = {
        section: {k: v for k, v in entries.items() if v}
        for section, entries in data.items() if section != "aliases"
    }
    return StopNames(aliases=aliases, langs=langs)


def validate(data: dict) -> list[str]:
    """병합 결과(``_normalize`` 형태)의 불변식 위반 목록. 비어 있으면 통과."""
    problems: list[str] = []
    aliases = {k: v for k, v in data.get("aliases", {}).items() if v}
    for short, canon in aliases.items():
        if canon in aliases:
            problems.append(f"alias '{short}' → '{canon}': 대상이 다시 alias입니다(1단계만 허용)")
    for section, entries in data.items():
        if section == "aliases":
            continue
        seen: dict[str, str] = {}
        for ko, value in entries.items():
            if not value:
                continue
            if ko in aliases:
                problems.append(f"[{section}] '{ko}'는 alias(약칭)라 번역 키가 될 수 없습니다")
            if len(value) > MAX_LEN:
                problems.append(f"[{section}] '{ko}': {MAX_LEN}자 초과")
            if any(ord(c) < 32 for c in value):
                problems.append(f"[{section}] '{ko}': 제어문자 포함")
            folded = value.casefold()
            if folded in seen:
                problems.append(f"[{section}] '{value}'가 '{seen[folded]}'와 '{ko}'에 중복됩니다(1:1 위반)")
            else:
                seen[folded] = ko
    return problems


class StopNameDict:
    """시드 + override 파일의 로드/검증/저장. 로드 결과는 두 파일의 mtime으로 캐시."""

    def __init__(self, path, seed_path=SEED_PATH):
        self.path = Path(path)
        self.seed_path = Path(seed_path) if seed_path else None
        self._lock = threading.Lock()
        self._cache_key: tuple | None = None
        self._cache: StopNames = EMPTY

    def _read(self, path: Path | None) -> dict:
        if path is None:
            return {}
        return _normalize(read_json(path, {}, expect=dict, warn_label="stop_names", logger=log))

    def load_raw(self) -> tuple[dict, dict]:
        """(seed, override) 원본 — 관리자 편집 화면용(묘비 포함)."""
        return self._read(self.seed_path), self._read(self.path)

    def load(self) -> StopNames:
        """유효 사전. 파일 부재·파손은 빈 사전으로 취급(ADR-013)하며, 불변식 위반이 있으면 로그만 남긴다."""
        key = (_mtime(self.seed_path), _mtime(self.path))
        with self._lock:
            if key == self._cache_key:
                return self._cache
        seed, override = self.load_raw()
        merged = _merge(seed, override)
        problems = validate(merged)
        if problems:
            log.warning("stop_names 불변식 위반(표시는 계속): %s", "; ".join(problems))
        names = _to_stop_names(merged)
        with self._lock:
            self._cache_key, self._cache = key, names
        return names

    def save(self, override: dict) -> None:
        """override 전체를 검증 후 atomic 저장. 위반 시 ``StopNameError``(파일 무변경)."""
        normalized = _normalize(override)
        seed, _ = self.load_raw()
        problems = validate(_merge(seed, normalized))
        if problems:
            raise StopNameError(problems)
        payload = {"version": FILE_VERSION, **{k: dict(sorted(v.items())) for k, v in sorted(normalized.items())}}
        atomic_write_json(self.path, payload, ensure_ascii=False, indent=2)


def _mtime(path: Path | None) -> int | None:
    if path is None:
        return None
    try:
        return os.stat(path).st_mtime_ns
    except OSError:
        return None


_instances: dict[Path, StopNameDict] = {}
_instances_lock = threading.Lock()


def get_stop_names(data_dir) -> StopNames:
    """프로세스 공유 인스턴스로 유효 사전을 반환. 매 호출 stat() 2회로 다른 워커의 저장도 즉시 반영."""
    path = default_stop_names_path(data_dir)
    with _instances_lock:
        inst = _instances.get(path)
        if inst is None:
            inst = _instances[path] = StopNameDict(path)
    return inst.load()
