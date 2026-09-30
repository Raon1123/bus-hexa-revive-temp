"""기한형 공지(notice) 저장소 + 표시 규칙.

공지를 코드(i18n 키·템플릿 하드코딩)가 아니라 **데이터**로 관리한다. 표시 기간과 시행일이
지나면 문구가 저절로 바뀌거나 사라지므로, 날짜가 박힌 문구가 낡는 일을 막는다.

## 저장 위치

``<data_dir>/notices.json`` — 관리자 편집본(런타임 쓰기 가능 볼륨, 단일 진실원천).
seed: ``bushexa/data/notices.seed.json`` — 이미지에 구워진 공장 초기값(공개 static 이 아님).
data_dir 파일이 없거나 **깨져 있으면** 표시용으로 seed 를 쓴다. 관리자가 처음 저장하면 seed 항목이
live 로 이관되고, 그 뒤로는 live 만 쓴다(seed 와 달라진 항목은 /admin/notices 에서 알려 준다).

## 항목 형식

    {
      "id": "743-beomseo-2026",              # [A-Za-z0-9_-]{1,64}, 유일
      "kind": "route_change",                # info | route_change | warning | suspension
      "routes": ["743"],                     # 관련 노선. [] = 전체
      "surfaces": ["board", "unist"],        # 표시 화면. ["all"] = 모든 공개 화면
      "show_from": null,                     # 표시 시작(포함). null = 즉시
      "show_until": "2026-10-31",            # 표시 종료. 날짜만 쓰면 그날 끝까지. null = 무기한
      "effective_from": "2026-10-03",        # 시행일. 이 시각부터 text_after 로 바뀜(선택)
      "text": {"ko": "{date}부터 ...", "en": "From {date}, ..."},
      "text_after": {"ko": "...", "en": "..."},   # 선택. 쓰면 text 와 같은 언어를 모두 채운다
      "link": "info",                        # 선택. 공개 화면 이름(아래 LINK_ENDPOINTS)만 허용
      "priority": 0,                         # -1000~1000. 같은 종류 안에서 큰 값이 위
      "enabled": true
    }

시각 문자열은 ``YYYY-MM-DD`` 또는 ``YYYY-MM-DDTHH:MM`` (KST, 2000~2100년). 문구의 ``{date}`` 는
시행일(없으면 표시 시작일)을 언어별 짧은 날짜("10월 3일" / "Oct 3")로, ``{dow}`` 는 그 요일로 치환한다.
기준일이 없는 공지에는 ``{date}``/``{dow}`` 를 쓸 수 없다.

## 안전 원칙

- 읽기 경로는 절대 예외를 올리지 않는다. 잘못된 항목만 건너뛰고 로그를 남긴다.
- 쓰기 경로는 live 파일이 깨졌거나 거부된 항목이 있으면 **저장을 거부**한다(조용한 유실 방지).
  쓰기는 ``locked_update_json`` 으로 워커 간 직렬화한다.
- 링크는 임의 URL 을 받지 않고 공개 화면 이름만 받는다(오픈 리다이렉트·javascript: 차단).
- 멀티 워커: 파일 (inode, mtime_ns, ctime_ns, size) 서명이 바뀌면 다시 읽는다. atomic 저장은
  os.replace 로 새 inode 를 만들므로 같은 크기·같은 mtime 틱의 재기록도 감지된다.
"""
from __future__ import annotations

import datetime as _dt
import logging
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from bushexa.fileio import locked_update_json, read_json
from bushexa.time_utils import KST

log = logging.getLogger("bushexa.services.notices")

SEED_PATH = Path(__file__).resolve().parent.parent / "data" / "notices.seed.json"

# ── 어휘 ────────────────────────────────────────────────────────────────

KINDS: tuple[str, ...] = ("suspension", "warning", "route_change", "info")   # 위가 더 심각
SURFACES: tuple[str, ...] = ("board", "lite", "unist", "stops", "timetable", "busno", "info", "running")
ALL_SURFACES = "all"

# 공개 라우트 endpoint → 공지 surface. 여기 없는 endpoint(부분 갱신 partial, admin)는 공지를 그리지 않는다.
ENDPOINT_SURFACES: dict[str, str] = {
    "board.departure_board": "board",
    "board_lite.board_lite": "lite",
    "unist_board.unist_board_page": "unist",
    "stops.stops_page": "stops",
    "unist_timetable.timetable_page": "timetable",
    "busno.busno_page": "busno",
    "info.info_page": "info",
    "running.running_page": "running",
}

# 전체 페이지를 다시 읽지 않고 HTMX 부분 갱신만 하는 화면. 공지 영역을 따로 주기 갱신한다.
POLL_SURFACES: frozenset[str] = frozenset({"board", "unist", "stops"})

# 공지 링크로 허용하는 목적지(surface 이름 → endpoint).
LINK_ENDPOINTS: dict[str, str] = {v: k for k, v in ENDPOINT_SURFACES.items()}

LANGS: tuple[str, ...] = ("ko", "en")

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")
_ROUTE_RE = re.compile(r"^[0-9A-Za-z-]{1,10}$")
_PLACEHOLDER_RE = re.compile(r"\{(date|dow)\}")
_MAX_TEXT = 500
_YEAR_MIN, _YEAR_MAX = 2000, 2100
_PRIORITY_MIN, _PRIORITY_MAX = -1000, 1000

_DOW = {
    "ko": ("월", "화", "수", "목", "금", "토", "일"),
    "en": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
}
_MONTH_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
             "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


class NoticeError(ValueError):
    """관리자 입력·파일 상태 검증 실패. 메시지는 관리자에게 그대로 보여 준다."""


# ── 시각 파싱 ────────────────────────────────────────────────────────────

def parse_when(value: Any, *, end_of_day: bool = False) -> _dt.datetime | None:
    """``YYYY-MM-DD`` / ``YYYY-MM-DDTHH:MM`` → KST aware datetime. 빈 값은 None.

    ``end_of_day=True`` 이고 날짜만 주어지면 **다음 날 00:00** 을 돌려준다
    (표시 종료일을 '그날 끝까지'로 해석하기 위한 배타적 경계).
    형식이 틀리거나 2000~2100년 밖이면 :class:`NoticeError`.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if not (_DATE_RE.match(s) or _DATETIME_RE.match(s)):
        raise NoticeError(f"날짜 형식은 YYYY-MM-DD 또는 YYYY-MM-DDTHH:MM 이어야 합니다: {s}")
    if not (_YEAR_MIN <= int(s[:4]) <= _YEAR_MAX):
        raise NoticeError(f"날짜는 {_YEAR_MIN}~{_YEAR_MAX}년 사이여야 합니다: {s}")
    try:
        if _DATE_RE.match(s):
            d = _dt.date.fromisoformat(s)
            base = _dt.datetime(d.year, d.month, d.day, tzinfo=KST)
            return base + _dt.timedelta(days=1) if end_of_day else base
        return _dt.datetime.fromisoformat(s).replace(tzinfo=KST)
    except (ValueError, OverflowError) as exc:
        raise NoticeError(f"날짜가 올바르지 않습니다: {s}") from exc


def format_short_date(when: _dt.datetime, lang: str) -> str:
    """언어별 짧은 날짜: ko '10월 3일', en 'Oct 3'."""
    if lang == "en":
        return f"{_MONTH_EN[when.month - 1]} {when.day}"
    return f"{when.month}월 {when.day}일"


# ── 모델 ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Notice:
    id: str
    kind: str
    routes: tuple[str, ...]
    surfaces: tuple[str, ...]
    show_from: _dt.datetime | None
    show_until: _dt.datetime | None          # 배타적 경계
    effective_from: _dt.datetime | None
    text: dict[str, str]
    text_after: dict[str, str] = field(default_factory=dict)
    link: str | None = None
    priority: int = 0
    enabled: bool = True

    def status(self, now: _dt.datetime) -> str:
        """'disabled' | 'scheduled' | 'active' | 'expired'."""
        if not self.enabled:
            return "disabled"
        if self.show_from is not None and now < self.show_from:
            return "scheduled"
        if self.show_until is not None and now >= self.show_until:
            return "expired"
        return "active"

    def phase(self, now: _dt.datetime) -> str | None:
        """시행일 기준 단계: 'upcoming'(시행 전) | 'effective'(시행 후) | None(시행일 없음)."""
        if self.effective_from is None:
            return None
        return "effective" if now >= self.effective_from else "upcoming"

    def shows_on(self, surface: str) -> bool:
        return ALL_SURFACES in self.surfaces or surface in self.surfaces

    def concerns(self, routes: Iterable[str] | None) -> bool:
        """노선 필터. 공지가 전체 대상([])이거나 필터가 없거나 교집합이 있으면 True."""
        if not self.routes or routes is None:
            return True
        return bool(set(self.routes) & set(routes))

    def render_text(self, now: _dt.datetime, lang: str) -> str:
        """현재 시각·언어에 맞는 문구(치환 완료). 해당 언어가 없으면 ko 로 폴백.

        시행 후 문구는 언어별로 고른다: text_after[lang] → text[lang] → ko 순.
        (validate 가 text_after 의 언어 범위를 text 와 같게 강제하므로 보통 첫 단계에서 끝난다.)
        """
        after = self.phase(now) == "effective"
        candidates = ([self.text_after.get(lang)] if after else []) + [self.text.get(lang)]
        candidates += ([self.text_after.get("ko")] if after else []) + [self.text.get("ko")]
        raw = next((c for c in candidates if c), "")
        anchor = self.effective_from or self.show_from
        if anchor is not None:
            raw = raw.replace("{date}", format_short_date(anchor, lang))
            raw = raw.replace("{dow}", _DOW.get(lang, _DOW["ko"])[anchor.weekday()])
        return raw


@dataclass(frozen=True)
class RenderedNotice:
    """템플릿에 넘기는 완성본."""
    id: str
    kind: str
    text: str
    link: str | None      # surface 이름. 템플릿이 LINK_ENDPOINTS 로 url_for 한다.
    phase: str | None


# ── 검증 ────────────────────────────────────────────────────────────────

def _texts(value: Any, *, required: bool) -> dict[str, str]:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise NoticeError("문구는 {\"ko\": ..., \"en\": ...} 형식이어야 합니다.")
    out: dict[str, str] = {}
    for lang in LANGS:
        s = str(value.get(lang) or "").strip()
        if len(s) > _MAX_TEXT:
            raise NoticeError(f"문구는 {_MAX_TEXT}자를 넘을 수 없습니다 ({lang}).")
        if s:
            out[lang] = s
    if required and "ko" not in out:
        raise NoticeError("한국어 문구(ko)는 필수입니다.")
    return out


def _str_list(value: Any, name: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [v for v in re.split(r"[,\s]+", value) if v]
    if not isinstance(value, (list, tuple)):
        raise NoticeError(f"{name} 는 목록이어야 합니다.")
    return [str(v).strip() for v in value if str(v).strip()]


def _priority(value: Any) -> int:
    if value is None or value == "":
        return 0
    if isinstance(value, bool) or (isinstance(value, float) and not value.is_integer()):
        raise NoticeError("우선순위는 정수여야 합니다.")
    try:
        p = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise NoticeError("우선순위는 정수여야 합니다.") from exc
    if not (_PRIORITY_MIN <= p <= _PRIORITY_MAX):
        raise NoticeError(f"우선순위는 {_PRIORITY_MIN}~{_PRIORITY_MAX} 사이여야 합니다.")
    return p


def validate(entry: Any) -> dict:
    """원시 항목을 검증해 **정규화된 저장용 dict** 로 돌려준다. 실패 시 :class:`NoticeError`."""
    if not isinstance(entry, dict):
        raise NoticeError("공지 항목은 객체여야 합니다.")
    nid = str(entry.get("id") or "").strip()
    if not _ID_RE.match(nid):
        raise NoticeError("ID 는 영문·숫자·_·- 1~64자여야 합니다.")
    kind = str(entry.get("kind") or "info").strip()
    if kind not in KINDS:
        raise NoticeError(f"종류는 {', '.join(KINDS)} 중 하나여야 합니다.")
    routes = _str_list(entry.get("routes"), "routes")
    for r in routes:
        if not _ROUTE_RE.match(r):
            raise NoticeError(f"노선 번호가 올바르지 않습니다: {r}")
    surfaces = _str_list(entry.get("surfaces"), "surfaces") or [ALL_SURFACES]
    for s in surfaces:
        if s != ALL_SURFACES and s not in SURFACES:
            raise NoticeError(f"알 수 없는 표시 화면: {s}")
    if ALL_SURFACES in surfaces:
        surfaces = [ALL_SURFACES]

    def _when(key: str) -> str | None:
        v = entry.get(key)
        s = str(v).strip() if v is not None else ""
        if not s:
            return None
        parse_when(s)          # 형식·범위 검증
        return s

    show_from, show_until, effective_from = _when("show_from"), _when("show_until"), _when("effective_from")
    if show_from and show_until and parse_when(show_until, end_of_day=True) <= parse_when(show_from):
        raise NoticeError("표시 종료는 표시 시작보다 뒤여야 합니다.")

    text = _texts(entry.get("text"), required=True)
    text_after = _texts(entry.get("text_after"), required=False)
    if text_after and set(text_after) != set(text):
        raise NoticeError("시행 후 문구는 본 문구와 같은 언어를 모두 채워야 합니다 "
                          f"(본 문구: {', '.join(sorted(text))}).")
    if not (effective_from or show_from) and any(
            _PLACEHOLDER_RE.search(t) for t in (*text.values(), *text_after.values())):
        raise NoticeError("{date}/{dow} 를 쓰려면 시행일이나 표시 시작일이 있어야 합니다.")

    link = entry.get("link") or None
    if link is not None:
        link = str(link).strip() or None
        if link is not None and link not in LINK_ENDPOINTS:
            raise NoticeError(f"링크는 공개 화면 이름({', '.join(LINK_ENDPOINTS)})만 쓸 수 있습니다.")

    enabled = entry.get("enabled", True)
    if not isinstance(enabled, bool):
        raise NoticeError("enabled 는 true/false 여야 합니다.")

    return {
        "id": nid,
        "kind": kind,
        "routes": routes,
        "surfaces": surfaces,
        "show_from": show_from,
        "show_until": show_until,
        "effective_from": effective_from,
        "text": text,
        "text_after": text_after,
        "link": link,
        "priority": _priority(entry.get("priority")),
        "enabled": enabled,
    }


def to_notice(clean: dict) -> Notice:
    """:func:`validate` 결과 → :class:`Notice`."""
    return Notice(
        id=clean["id"],
        kind=clean["kind"],
        routes=tuple(clean["routes"]),
        surfaces=tuple(clean["surfaces"]),
        show_from=parse_when(clean["show_from"]),
        show_until=parse_when(clean["show_until"], end_of_day=True),
        effective_from=parse_when(clean["effective_from"]),
        text=dict(clean["text"]),
        text_after=dict(clean["text_after"]),
        link=clean["link"],
        priority=clean["priority"],
        enabled=clean["enabled"],
    )


def parse_entries_report(data: Any, *, source: str = "") -> tuple[list[dict], list[str]]:
    """원시 JSON(list) → (검증된 항목, 거부 사유 목록). 어떤 입력에도 예외를 올리지 않는다."""
    if not isinstance(data, list):
        return [], ["최상위가 목록(list)이 아닙니다."]
    out: list[dict] = []
    rejected: list[str] = []
    seen: set[str] = set()
    for i, entry in enumerate(data):
        label = entry.get("id") if isinstance(entry, dict) else None
        try:
            clean = validate(entry)
            to_notice(clean)                     # 변환까지 되는지 확인
        except Exception as exc:                 # noqa: BLE001 — 항목 하나가 전체를 막지 않게
            msg = exc if isinstance(exc, NoticeError) else f"{type(exc).__name__}: {exc}"
            rejected.append(f"#{i + 1} {label or '(ID 없음)'}: {msg}")
            continue
        if clean["id"] in seen:
            rejected.append(f"#{i + 1} {clean['id']}: ID 중복")
            continue
        seen.add(clean["id"])
        out.append(clean)
    for r in rejected:
        log.warning("공지 항목 무시 (%s) %s", source, r)
    return out, rejected


def parse_entries(data: Any, *, source: str = "") -> list[dict]:
    """:func:`parse_entries_report` 의 항목만."""
    return parse_entries_report(data, source=source)[0]


# ── 파일 캐시 ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class _Loaded:
    entries: list[dict]
    rejected: list[str]
    corrupt: bool          # JSON 자체를 읽지 못함


_cache_lock = threading.Lock()
_cache: dict[str, tuple[tuple[int, int, int, int], _Loaded]] = {}


def _signature(path: Path) -> tuple[int, int, int, int] | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return (st.st_ino, st.st_mtime_ns, st.st_ctime_ns, st.st_size)


def _load_cached(path: Path) -> _Loaded | None:
    """파일을 서명 캐시로 읽는다. 부재면 None."""
    sig = _signature(path)
    if sig is None:
        return None
    key = str(path)
    with _cache_lock:
        hit = _cache.get(key)
        if hit is not None and hit[0] == sig:
            return hit[1]
    data = read_json(path, None, expect=list)
    if data is None:
        log.error("공지 파일을 읽지 못했습니다(파손 또는 형식 오류): %s", path)
        loaded = _Loaded([], ["파일을 JSON 목록으로 읽지 못했습니다."], corrupt=True)
    else:
        entries, rejected = parse_entries_report(data, source=str(path))
        loaded = _Loaded(entries, rejected, corrupt=False)
    with _cache_lock:
        _cache[key] = (sig, loaded)
    return loaded


def _clear_cache() -> None:
    """테스트용."""
    with _cache_lock:
        _cache.clear()


# ── 저장소 ──────────────────────────────────────────────────────────────

def default_notices_path(data_dir) -> Path:
    return Path(data_dir) / "notices.json"


class NoticeStore:
    """공지 목록의 로드/저장/추가·수정/삭제."""

    def __init__(self, live_path, seed_path: Path | None = SEED_PATH):
        self.live_path = Path(live_path)
        self.seed_path = Path(seed_path) if seed_path is not None else None

    # ── 읽기 ──
    def _seed_entries(self) -> list[dict]:
        if self.seed_path is None:
            return []
        loaded = _load_cached(self.seed_path)
        return [dict(e) for e in loaded.entries] if loaded else []

    def load_entries(self) -> list[dict]:
        """표시용 항목. live 우선. live 가 없거나 **깨졌으면** seed(ERROR 로그), 둘 다 없으면 []."""
        loaded = _load_cached(self.live_path)
        if loaded is not None and not loaded.corrupt:
            return [dict(e) for e in loaded.entries]
        return self._seed_entries()

    def load(self) -> list[Notice]:
        return [to_notice(e) for e in self.load_entries()]

    def get(self, notice_id: str) -> dict | None:
        return next((e for e in self.load_entries() if e["id"] == notice_id), None)

    def health(self) -> dict:
        """관리 화면용 상태: source('live'|'seed'|'none'), corrupt, rejected(사유 목록)."""
        loaded = _load_cached(self.live_path)
        if loaded is None:
            return {"source": "seed" if self._seed_entries() else "none", "corrupt": False, "rejected": []}
        return {"source": "seed" if loaded.corrupt else "live",
                "corrupt": loaded.corrupt, "rejected": list(loaded.rejected)}

    def seed_drift(self) -> list[dict]:
        """live 가 있을 때, seed 에 있지만 live 에 없거나 내용이 다른 항목. [{entry, state}]."""
        loaded = _load_cached(self.live_path)
        if loaded is None or loaded.corrupt:
            return []
        live = {e["id"]: e for e in loaded.entries}
        out = []
        for e in self._seed_entries():
            if e["id"] not in live:
                out.append({"entry": e, "state": "missing"})
            elif live[e["id"]] != e:
                out.append({"entry": e, "state": "differs"})
        return out

    # ── 쓰기 (워커 간 잠금 + 조용한 유실 방지) ──
    def _mutate(self, fn) -> Any:
        """live 파일을 잠근 채 검증된 항목 목록을 fn(entries) 로 바꿔 저장한다.

        live 가 깨졌거나 거부된 항목이 있으면 NoticeError — 저장하면 그 항목이 사라지기 때문.
        live 가 없으면 seed 항목에서 시작한다(최초 이관).
        """
        result: dict[str, Any] = {}
        seed = self._seed_entries()

        def mutate(raw):
            if raw is None:
                if self.live_path.exists():          # 있는데 None → 파손
                    raise NoticeError("공지 파일(notices.json)이 깨져 있어 저장하지 않았습니다. "
                                      "파일을 고치거나 백업에서 복구한 뒤 다시 시도하세요.")
                entries = [dict(e) for e in seed]
            else:
                entries, rejected = parse_entries_report(raw, source=str(self.live_path))
                if rejected:
                    raise NoticeError("공지 파일에 잘못된 항목이 있어 저장하지 않았습니다(저장하면 사라짐): "
                                      + "; ".join(rejected))
            result["value"] = fn(entries)
            return entries

        locked_update_json(self.live_path, mutate, default=None)
        return result.get("value")

    def upsert(self, raw: dict, *, original_id: str | None = None) -> dict:
        """검증 후 저장. ``original_id`` 가 있으면 그 항목을 교체(ID 변경 포함), 없으면 같은 ID 교체/추가."""
        clean = validate(raw)
        target = (original_id or "").strip() or clean["id"]

        def fn(entries: list[dict]) -> dict:
            if target != clean["id"] and any(e["id"] == clean["id"] for e in entries):
                raise NoticeError(f"ID '{clean['id']}' 는 이미 있습니다.")
            for i, e in enumerate(entries):
                if e["id"] == target:
                    entries[i] = clean
                    break
            else:
                entries.append(clean)
            return clean

        return self._mutate(fn)

    def remove(self, notice_id: str) -> bool:
        def fn(entries: list[dict]) -> bool:
            before = len(entries)
            entries[:] = [e for e in entries if e["id"] != notice_id]
            return len(entries) != before
        return bool(self._mutate(fn))

    def set_enabled(self, notice_id: str, enabled: bool) -> bool:
        def fn(entries: list[dict]) -> bool:
            for e in entries:
                if e["id"] == notice_id:
                    e["enabled"] = bool(enabled)
                    return True
            return False
        return bool(self._mutate(fn))

    def import_seed(self, notice_id: str) -> bool:
        """seed 의 해당 항목으로 live 항목을 추가/교체."""
        entry = next((e for e in self._seed_entries() if e["id"] == notice_id), None)
        if entry is None:
            return False
        self.upsert(entry)
        return True


# ── 표시 선택 ────────────────────────────────────────────────────────────

def _sort_key(n: Notice) -> tuple:
    floor = _dt.datetime.min.replace(tzinfo=KST)
    return (KINDS.index(n.kind), -n.priority, n.show_from or floor, n.id)


def select_notices(notices: Iterable[Notice], *, surface: str, now: _dt.datetime,
                   lang: str, routes: Iterable[str] | None = None) -> list[RenderedNotice]:
    """``surface`` 화면에 ``now`` 시각 표시할 공지(심각도 → 우선순위 → 시작일 순)."""
    routes = list(routes) if routes is not None else None
    picked = [
        n for n in notices
        if n.status(now) == "active" and n.shows_on(surface) and n.concerns(routes)
    ]
    picked.sort(key=_sort_key)
    return [
        RenderedNotice(id=n.id, kind=n.kind, text=n.render_text(now, lang),
                       link=n.link, phase=n.phase(now))
        for n in picked
    ]
