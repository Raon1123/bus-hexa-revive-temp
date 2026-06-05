"""domain/unist_board + route 수정 회귀 테스트 (리뷰 #4/#5/D8).

테스트 의도:
  test_holiday_uses_weekday2_schedule     — #4 회귀: 공휴일에 /unist가 weekday=2 시간표를 사용
  test_normal_weekday_uses_weekday0       — #4 회귀 역: 공휴일 아닌 평일은 weekday=0 사용
  test_special_edition_applied_to_unist   — #5 회귀: 특별편 지정일에 /unist가 특별편 시각 반환
  test_d8_partial_edition_fallback        — D8 회귀: 부분 편성 edition에서 누락 노선이 빈 행 아닌
                                            평일-0 시각으로 폴백

E-13 준수: 기대값은 이 파일에서 수기로 정의한 알려진 입력. 도메인 구현 출력으로 기대값을
세우는 tautology 없음. 네트워크 호출 없음.
admin POST 없음 — SpecialTimetableService/HolidayEditor로 직접 설정한다.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from bushexa.domain.unist_board import get_unist_board_data
from bushexa.services.board_support import timetable_provider_for
from bushexa.services.holiday_editor import HolidayEditor
from bushexa.services.special_timetable import SpecialTimetableService

KST = ZoneInfo("Asia/Seoul")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class _FakeClock:
    def __init__(self, now: datetime.datetime) -> None:
        self._now = now

    def now(self) -> datetime.datetime:
        return self._now


def _make_fake_client(arrivals=None):
    """fetch_arrivals를 mock한 client. 기본 빈 목록 반환."""
    c = MagicMock()
    c.fetch_arrivals.return_value = arrivals or []
    return c


def _make_timetable_provider(data: dict):
    """알려진 (busno, weekday, departure) → list[str] 매핑 provider."""
    def provider(busno, weekday, departure):
        key = (str(busno), int(weekday), str(departure))
        if key not in data:
            raise FileNotFoundError(f"No timetable for {key}")
        return data[key]
    return provider


# 기준 시간표 — weekday=0(평일): 10:00, weekday=2(일/공휴일): 16:00
# 모든 UNIST 출발 노선(713/743/753/1115)과 513 via 노선 포함
_BASE_TIMETABLE = {
    ("513", 0, "덕하"): ["10:00"],
    ("513", 0, "삼남"): ["10:05"],
    ("513", 2, "덕하"): ["16:00"],
    ("513", 2, "삼남"): ["16:05"],
    ("713", 0, "UNIST"): ["10:10"],
    ("713", 2, "UNIST"): ["16:10"],
    ("743", 0, "UNIST"): ["10:15"],
    ("743", 2, "UNIST"): ["16:15"],
    ("753", 0, "UNIST"): ["10:20"],
    ("753", 2, "UNIST"): ["16:20"],
    ("1115", 0, "UNIST"): ["10:25"],
    ("1115", 2, "UNIST"): ["16:25"],
    # 1 (토)
    ("513", 1, "덕하"): ["11:00"],
    ("513", 1, "삼남"): ["11:05"],
    ("713", 1, "UNIST"): ["11:10"],
    ("743", 1, "UNIST"): ["11:15"],
    ("753", 1, "UNIST"): ["11:20"],
    ("1115", 1, "UNIST"): ["11:25"],
}


# ---------------------------------------------------------------------------
# #4 회귀: 공휴일에 weekday=2 시간표를 사용하는지
# ---------------------------------------------------------------------------

def test_holiday_uses_weekday2_schedule():
    """#4 회귀: 공휴일로 지정된 날(평일)에 get_unist_board_data가 weekday=2 시간표를 사용한다.

    설정:
    - 날짜: 2026-06-01(월요일) → 공휴일 집합 {"20260601"}에 포함
    - 시간: 09:00 KST (16:00이 미래 시간으로 board에 표시됨)
    - 평일(weekday=0) 시간표: ["10:10"] → 과거이므로 카드에 안 보임(09:00 기준 10:10은 미래)
      하지만 weekday=2에는 ["16:10"]이 있으므로 공휴일이면 16:10이 표시돼야 한다.

    기대: 713/UNIST 카드 entries에 "16:10 출발 예정"이 포함된다.
    기존 버그(리뷰 #4): holiday_set 미전달 → weekday=0 → "10:10 출발 예정"이 표시됨.
    """
    clock = _FakeClock(datetime.datetime(2026, 6, 1, 9, 0, 0, tzinfo=KST))
    holiday_set = {"20260601"}  # 2026-06-01(월요일)을 공휴일로 지정
    timetable = _make_timetable_provider(_BASE_TIMETABLE)
    client = _make_fake_client([])

    snapshot = get_unist_board_data(
        clock,
        client=client,
        timetable_provider=timetable,
        holiday_set=holiday_set,
    )

    # 713/UNIST from 카드 찾기
    from_713 = next(
        (c for c in snapshot.cards if c.busno == "713"),
        None,
    )
    assert from_713 is not None, "713 카드가 없음"

    entry_texts = [e.text for e in from_713.entries]
    assert any("16:10" in t for t in entry_texts), (
        f"공휴일에 weekday=2(16:10)이 표시돼야 함. 실제: {entry_texts} (리뷰 #4 회귀)"
    )
    assert not any("10:10" in t for t in entry_texts), (
        f"공휴일에 weekday=0(10:10)이 표시되면 안 됨. 실제: {entry_texts} (리뷰 #4 회귀)"
    )


def test_normal_weekday_uses_weekday0():
    """#4 역: 공휴일 아닌 평일에 weekday=0 시간표를 사용한다.

    공휴일 집합이 빈 경우 weekday=0이어야 한다.
    """
    # 시간을 9:00으로 설정 — 10:10이 미래 시간으로 board에 표시됨
    clock = _FakeClock(datetime.datetime(2026, 6, 1, 9, 0, 0, tzinfo=KST))
    holiday_set: set[str] = set()  # 공휴일 없음
    timetable = _make_timetable_provider(_BASE_TIMETABLE)
    client = _make_fake_client([])

    snapshot = get_unist_board_data(
        clock,
        client=client,
        timetable_provider=timetable,
        holiday_set=holiday_set,
    )

    from_713 = next(c for c in snapshot.cards if c.busno == "713")
    entry_texts = [e.text for e in from_713.entries]
    assert any("10:10" in t for t in entry_texts), (
        f"평일에 weekday=0(10:10)이 표시돼야 함. 실제: {entry_texts}"
    )


# ---------------------------------------------------------------------------
# #5 회귀: 특별편 지정일에 /unist가 특별편 시각을 반환하는지
# ---------------------------------------------------------------------------

def test_special_edition_applied_to_unist(tmp_path):
    """#5 회귀: 특별편 지정일에 timetable_provider_for가 특별편 시각을 반환한다.

    설정:
    - 오늘: 20260610(수요일, 평일)
    - 특별편 "exam": 713/weekday=0/UNIST → ["20:00"] (늦은 특별 운행)
    - 기본 시간표: 713/weekday=0/UNIST → ["10:10"]
    - 기대: timetable_provider_for를 통해 provider를 만들면 "20:00"이 반환된다.

    /board와 동일하게 timetable_provider_for를 사용함으로써 특별편이 적용된다 (리뷰 #5 수정).
    기존 버그(리뷰 #5): bare get_timetable 전달 → 기본 시간표 "10:10" 표시.
    """
    # 특별편 파일 설정 (SpecialTimetableService 직접 사용 — admin POST 없음)
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    tt_dir = tmp_path / "timetable"
    tt_dir.mkdir()
    edition_dir = tt_dir / "special" / "exam"
    edition_dir.mkdir(parents=True)

    # 특별 시간표: 713/weekday=0/UNIST → ["20:00"]
    special_data = {"0": {"UNIST": ["20:00"]}, "1": {"UNIST": []}, "2": {"UNIST": []}}
    (edition_dir / "713.json").write_text(
        json.dumps(special_data), encoding="utf-8"
    )
    # 나머지 노선(743/753/1115) 특별편 없음 — 기본 시간표 참조 시 FileNotFoundError 발생
    svc = SpecialTimetableService(
        map_path=data_dir / "special_timetables.json",
        timetable_dir=tt_dir,
    )
    svc.assign("20260610", "exam")

    config = SimpleNamespace(
        data_dir=data_dir,
        database_url="sqlite:///:memory:",
    )
    today = datetime.date(2026, 6, 10)
    # 시간: 09:00 KST (20:00이 미래 시간으로 표시됨)
    clock = _FakeClock(datetime.datetime(2026, 6, 10, 9, 0, 0, tzinfo=KST))
    holiday_set: set[str] = set()

    # timetable_dir()를 patch해 특별편 디렉터리를 올바르게 찾게 한다
    with patch("bushexa.services.board_support.timetable_dir", return_value=tt_dir):
        provider = timetable_provider_for(config, today, holiday_set)

    # provider가 특별편 시각을 반환해야 한다
    result_special = provider("713", 0, "UNIST")
    assert result_special == ["20:00"], (
        f"특별편 지정일에 provider가 특별편 시각(20:00)을 반환해야 함. 실제: {result_special} (리뷰 #5)"
    )

    # 실제로 unist_board 도메인에 주입해서 카드 확인
    # 나머지 노선은 edition에 없으므로 폴백 시도 → 기본 시간표도 없음 → 빈 entries
    base_provider = _make_timetable_provider(_BASE_TIMETABLE)

    def combined_provider(busno, weekday, departure):
        """특별편 provider + 기본 provider 연계. 실제 운영과 유사한 조합."""
        try:
            return provider(busno, weekday, departure)
        except FileNotFoundError:
            return base_provider(busno, weekday, departure)

    client = _make_fake_client([])
    snapshot = get_unist_board_data(
        clock,
        client=client,
        timetable_provider=combined_provider,
        holiday_set=holiday_set,
    )

    from_713 = next((c for c in snapshot.cards if c.busno == "713"), None)
    assert from_713 is not None, "713 카드가 없음"
    entry_texts = [e.text for e in from_713.entries]
    assert any("20:00" in t for t in entry_texts), (
        f"특별편 시각(20:00)이 713 카드에 표시돼야 함. 실제: {entry_texts} (리뷰 #5)"
    )
    assert not any("10:10" in t for t in entry_texts), (
        f"특별편 지정일에 기본 시간표(10:10)가 보이면 안 됨. 실제: {entry_texts} (리뷰 #5)"
    )


# ---------------------------------------------------------------------------
# D8 회귀: 부분 편성 edition에서 누락 노선이 평일-0 시각으로 폴백되는지
# ---------------------------------------------------------------------------

def test_d8_partial_edition_fallback(tmp_path):
    """D8 회귀: 부분 편성 edition(일부 노선 JSON만 있음)에서 누락 노선이 빈 행이 아닌
    기본 시간표 평일-0 시각으로 폴백된다.

    설정:
    - 오늘: 20260610 특별편 "exam" 배정
    - edition: 713만 있음, 743은 없음 (부분 편성)
    - 기본 시간표 디렉터리: 743.json 있음 → weekday=0/UNIST → ["07:30", "08:30"]
    - 요청: provider("743", 2, "UNIST") — weekday=2이지만 edition에 743.json 없음

    기대:
    - D8 수정 전: FileNotFoundError가 래퍼를 건너뛰어 도메인으로 흘러 빈 entries.
    - D8 수정 후: FileNotFoundError → 기본 시간표 디렉터리 weekday=0 폴백 → ["07:30", "08:30"].

    검증: 기본 시간표 디렉터리에 743.json을 준비하고 provider가 해당 시각을 반환하는지 확인.
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    tt_dir = tmp_path / "timetable"
    tt_dir.mkdir()
    edition_dir = tt_dir / "special" / "exam"
    edition_dir.mkdir(parents=True)

    # 713만 있음 — 743 없음 (부분 편성), weekday="0"만 채움
    (edition_dir / "713.json").write_text(
        json.dumps({"0": {"UNIST": ["18:00"]}, "1": {"UNIST": []}}),
        encoding="utf-8",
    )

    svc = SpecialTimetableService(
        map_path=data_dir / "special_timetables.json",
        timetable_dir=tt_dir,
    )
    svc.assign("20260610", "exam")

    config = SimpleNamespace(
        data_dir=data_dir,
        database_url="sqlite:///:memory:",
    )
    today = datetime.date(2026, 6, 10)
    holiday_set = {"20260610"}  # 오늘 공휴일 → weekday=2

    # 기본 시간표 디렉터리(BUSHEXA_TIMETABLE_DIR 참조) 준비
    default_tt_dir = tmp_path / "default_timetable"
    default_tt_dir.mkdir()
    (default_tt_dir / "743.json").write_text(
        json.dumps({"0": {"UNIST": ["07:30", "08:30"]}, "1": {"UNIST": []}, "2": {"UNIST": []}}),
        encoding="utf-8",
    )

    with patch("bushexa.services.board_support.timetable_dir", return_value=tt_dir):
        with patch("bushexa.data.timetable.timetable_dir", return_value=default_tt_dir):
            provider = timetable_provider_for(config, today, holiday_set)

            # 713에 대해 weekday=2 키가 없으면 edition 내 weekday=0 폴백 → ["18:00"]
            result_713 = provider("713", 2, "UNIST")
            assert result_713 == ["18:00"], (
                f"D8: 713/weekday=2 키 없을 때 edition weekday=0 폴백으로 ['18:00'] 반환해야 함. 실제: {result_713}"
            )

            # 743에 대해: edition에 743.json 없음 → FileNotFoundError → 기본 시간표 weekday=0 폴백
            # D8 수정 핵심: FileNotFoundError를 잡아 기본 시간표로 폴백 → ["07:30", "08:30"] 반환
            result_743 = provider("743", 2, "UNIST")
            assert result_743 == ["07:30", "08:30"], (
                f"D8 회귀: edition에 743.json 없을 때 기본 시간표 weekday=0으로 폴백해야 함 (빈 행 아님). "
                f"실제: {result_743}"
            )


def test_d8_distinguished_from_before_fix(tmp_path):
    """D8 수정 전과 후의 행동 차이를 직접 판별하는 테스트.

    edition에 weekday=2 키가 없을 때(KeyError):
    - 기존 래퍼: KeyError를 잡아 edition 내 weekday=0으로 폴백. ✓
    edition에 busno JSON이 없을 때(FileNotFoundError):
    - 기존 래퍼: FileNotFoundError를 잡지 못해 빈 행. ✗
    - D8 수정: FileNotFoundError를 잡아 기본 시간표 weekday=0으로 폴백. ✓

    이 테스트는 KeyError/FileNotFoundError 두 케이스 모두 weekday=0 폴백이 동작함을 확인한다.
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    tt_dir = tmp_path / "timetable"
    tt_dir.mkdir()
    edition_dir = tt_dir / "special" / "exam"
    edition_dir.mkdir(parents=True)

    # 713만 있고, weekday=0 키에 시간표 있음 (weekday=2 키 없음 → KeyError 발생 예정)
    (edition_dir / "713.json").write_text(
        json.dumps({"0": {"UNIST": ["07:00", "08:00"]}}),
        encoding="utf-8",
    )

    svc = SpecialTimetableService(
        map_path=data_dir / "special_timetables.json",
        timetable_dir=tt_dir,
    )
    svc.assign("20260610", "exam")

    config = SimpleNamespace(data_dir=data_dir, database_url="sqlite:///:memory:")
    today = datetime.date(2026, 6, 10)

    # 기본 시간표 디렉터리: 743.json 있음 (edition에 없는 노선)
    default_tt_dir = tmp_path / "default_timetable"
    default_tt_dir.mkdir()
    (default_tt_dir / "743.json").write_text(
        json.dumps({"0": {"UNIST": ["06:00"]}, "1": {"UNIST": []}, "2": {"UNIST": []}}),
        encoding="utf-8",
    )

    with patch("bushexa.services.board_support.timetable_dir", return_value=tt_dir):
        with patch("bushexa.data.timetable.timetable_dir", return_value=default_tt_dir):
            provider = timetable_provider_for(config, today, set())

            # 케이스 1: KeyError(기존 동작 유지) — edition 내 weekday=2 키 없음 → weekday=0 폴백
            result_keyerror = provider("713", 2, "UNIST")
            assert result_keyerror == ["07:00", "08:00"], (
                f"D8: KeyError 발생 시 edition 내 weekday=0 폴백으로 시각 반환해야 함. 실제: {result_keyerror}"
            )

            # 케이스 2: FileNotFoundError(D8 신규 수정) — edition에 743.json 없음 → 기본 시간표 weekday=0
            result_fnf = provider("743", 2, "UNIST")
            assert result_fnf == ["06:00"], (
                f"D8: FileNotFoundError 발생 시 기본 시간표 weekday=0으로 폴백해야 함. 실제: {result_fnf}"
            )
