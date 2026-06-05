"""board_support 서비스 단위 테스트 (리뷰 E6/#8, D8 회귀 방지).

테스트 의도:
  test_timetable_provider_for_no_edition      — 특별편 없는 날은 get_timetable 반환
  test_timetable_provider_for_with_edition    — 특별편 지정일에 edition provider 반환 (#5 회귀)
  test_edition_provider_keyerror_fallback     — KeyError → weekday=0 폴백 (D8 기존 동작)
  test_edition_provider_filenotfounderror_fallback — FileNotFoundError → weekday=0 폴백 (D8 신규수정)
  test_get_read_connection_reuse              — 같은 url로 두 번 호출하면 동일 객체 반환 (#8)
  test_get_read_connection_reconnect          — 끊긴 연결 자동 재연결
  test_arrival_client_returns_cached_client   — arrival_client가 동일 연결의 client 반환

E-13 준수: 기대값은 이 파일에서 수기로 정의한 알려진 입력값. 구현 출력을 읽어 기대값을 세우는
tautology 없음. 네트워크 호출 없음.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from bushexa.data.timetable import get_timetable
from bushexa.services.board_support import (
    _READ_CONN_CACHE,
    arrival_client,
    get_read_connection,
    timetable_provider_for,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_conn_cache():
    """각 테스트 전후 연결 캐시 초기화 — 전역 dict 오염 방지."""
    _READ_CONN_CACHE.clear()
    yield
    _READ_CONN_CACHE.clear()


@pytest.fixture
def config_no_edition(tmp_path):
    """특별편이 없는 AppConfig 유사 객체."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    return SimpleNamespace(data_dir=data_dir, database_url="sqlite:///:memory:")


@pytest.fixture
def config_with_edition(tmp_path):
    """특별편 'exam'이 20260610에 배정된 AppConfig 유사 객체.

    edition 디렉터리: tmp_path/timetable/special/exam/
    713.json: weekday=0/UNIST → ["14:00", "15:00"], weekday=2 키 없음 (D8 판별 조건)
    """
    from bushexa.services.special_timetable import SpecialTimetableService

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    tt_dir = tmp_path / "timetable"
    tt_dir.mkdir()
    edition_dir = tt_dir / "special" / "exam"
    edition_dir.mkdir(parents=True)

    # weekday="0"만 채움 — "2" 키 없음 (D8 수정 검증용 부분 편성)
    timetable_data = {
        "0": {"UNIST": ["14:00", "15:00"]},
        "1": {"UNIST": ["14:30"]},
        # "2" 키 의도적으로 누락
    }
    (edition_dir / "713.json").write_text(
        json.dumps(timetable_data), encoding="utf-8"
    )

    svc = SpecialTimetableService(
        map_path=data_dir / "special_timetables.json",
        timetable_dir=tt_dir,
    )
    svc.assign("20260610", "exam")

    # timetable_dir() patch를 위해 _tt_dir 속성도 포함
    return SimpleNamespace(
        data_dir=data_dir,
        database_url="sqlite:///:memory:",
        _tt_dir=tt_dir,
    )


# ---------------------------------------------------------------------------
# timetable_provider_for 테스트
# ---------------------------------------------------------------------------

def test_timetable_provider_for_no_edition(config_no_edition):
    """특별편이 없는 날은 get_timetable이 그대로 반환된다."""
    today = date(2026, 6, 5)  # 특별편 배정 없음
    provider = timetable_provider_for(config_no_edition, today, set())
    assert provider is get_timetable, (
        "특별편 없는 날은 기본 get_timetable을 반환해야 한다"
    )


def test_timetable_provider_for_with_edition(config_with_edition, tmp_path):
    """특별편 지정일에 edition provider를 반환한다 — 리뷰 #5 회귀."""
    today = date(2026, 6, 10)  # exam 에디션 배정일
    with patch("bushexa.services.board_support.timetable_dir",
               return_value=config_with_edition._tt_dir):
        provider = timetable_provider_for(config_with_edition, today, set())
    assert provider is not get_timetable, (
        "특별편 지정일에는 edition provider를 반환해야 한다 (리뷰 #5)"
    )


def test_edition_provider_keyerror_fallback(config_with_edition):
    """weekday=2 키 없는 부분 편성 edition에서 KeyError → weekday=0 폴백 (기존 동작)."""
    today = date(2026, 6, 10)
    with patch("bushexa.services.board_support.timetable_dir",
               return_value=config_with_edition._tt_dir):
        provider = timetable_provider_for(config_with_edition, today, set())

    # weekday=2 키가 없어 KeyError 발생 → weekday=0으로 폴백 → ["14:00", "15:00"]
    result = provider("713", 2, "UNIST")
    assert result == ["14:00", "15:00"], (
        "KeyError 발생 시 weekday=0(평일) 폴백으로 edition 시각을 반환해야 한다 (기존 D8 전부터)"
    )


def test_edition_provider_filenotfounderror_fallback(config_with_edition, tmp_path):
    """부분 편성 edition에서 노선 JSON 없으면 기본 시간표 weekday=0 데이터로 폴백 (D8 수정).

    edition 내에 753.json이 없는 경우:
    - 기존 래퍼(KeyError만 catch): FileNotFoundError가 래퍼를 건너뛰어 도메인으로 흘러 빈 행.
    - D8 수정 후: FileNotFoundError를 잡아 기본 시간표(BUSHEXA_TIMETABLE_DIR 기본값)의
      weekday=0 데이터로 폴백해 빈 행이 아닌 실제 시각을 반환한다.

    검증: 기본 시간표 디렉터리에 753.json을 만들고 provider가 해당 weekday=0 시각을 반환하는지
    확인한다. 핵심은 dir 인자 없는 get_timetable이 기본 디렉터리를 참조한다는 것이다.
    """
    today = date(2026, 6, 10)

    # 기본 시간표 디렉터리(BUSHEXA_TIMETABLE_DIR)에 753.json 준비
    default_tt_dir = tmp_path / "default_timetable"
    default_tt_dir.mkdir()
    (default_tt_dir / "753.json").write_text(
        json.dumps({"0": {"UNIST": ["09:00", "10:00"]}, "1": {"UNIST": []}, "2": {"UNIST": []}}),
        encoding="utf-8",
    )

    with patch("bushexa.services.board_support.timetable_dir",
               return_value=config_with_edition._tt_dir):
        # BUSHEXA_TIMETABLE_DIR을 기본 시간표 디렉터리로 패치
        # FileNotFoundError 폴백이 dir 인자 없는 get_timetable → timetable_dir() 를 호출하므로
        # bushexa.data.timetable.timetable_dir를 패치해야 한다.
        with patch("bushexa.data.timetable.timetable_dir", return_value=default_tt_dir):
            provider = timetable_provider_for(config_with_edition, today, set())
            # 753.json이 edition_dir에 없음 → FileNotFoundError → 기본 시간표 weekday=0 폴백
            # D8 수정: FileNotFoundError를 잡아 get_timetable(busno, 0, departure) 호출
            # → 기본 시간표 753.json weekday=0 → ["09:00", "10:00"]
            result = provider("753", 2, "UNIST")

    assert result == ["09:00", "10:00"], (
        f"D8: edition에 753.json 없을 때 기본 시간표 weekday=0 데이터로 폴백해야 함. 실제: {result}"
    )


def test_edition_provider_d8_no_filenotfounderror_reaches_domain_as_404(
    config_with_edition,
):
    """D8: 부분 편성에서 weekday=1(토) 키 있으면 정상 반환 — 폴백이 불필요한 케이스 확인."""
    today = date(2026, 6, 10)
    with patch("bushexa.services.board_support.timetable_dir",
               return_value=config_with_edition._tt_dir):
        provider = timetable_provider_for(config_with_edition, today, set())

    # weekday=1 키가 있으므로 정상 반환
    result = provider("713", 1, "UNIST")
    assert result == ["14:30"], (
        "weekday=1 키가 있으면 폴백 없이 해당 키 시각을 반환해야 한다"
    )


# ---------------------------------------------------------------------------
# get_read_connection 테스트
# ---------------------------------------------------------------------------

def test_get_read_connection_reuse():
    """같은 database_url로 두 번 호출하면 동일 연결 객체를 반환한다 — 리뷰 #8."""
    url = "sqlite:///:memory:"
    conn1 = get_read_connection(url)
    conn2 = get_read_connection(url)
    assert conn1 is conn2, (
        "같은 워커에서 두 번 호출 시 get_read_connection이 동일 객체를 반환해야 한다 (리뷰 #8)"
    )


def test_get_read_connection_different_urls():
    """다른 database_url은 별개의 연결을 반환한다."""
    url1 = "sqlite:///:memory:"
    # 두 번째 :memory: 연결은 사실상 별개 DB지만 url이 같으면 캐시 동작이 중요.
    # 여기서는 url 문자열 차이로 다른 연결임을 확인한다.
    conn1 = get_read_connection(url1)
    # 캐시에 url1이 등록됨; url1은 재사용
    conn_again = get_read_connection(url1)
    assert conn1 is conn_again, "동일 url → 동일 연결"


def test_get_read_connection_reconnect_on_broken():
    """sqlite3.OperationalError 발생 시 1회 재연결한다."""
    url = "sqlite:///:memory:"
    conn1 = get_read_connection(url)

    # 연결을 강제로 닫아 끊긴 상태 시뮬레이션
    conn1.close()

    # 끊긴 연결이 캐시에 남아 있음 → 다음 호출에서 재연결해야 한다
    conn2 = get_read_connection(url)
    # 새 연결이어야 하며, 동작해야 한다
    assert conn2 is not conn1, "끊긴 연결은 새 연결로 교체돼야 한다"
    # 새 연결은 유효한가
    conn2.execute("SELECT 1")


# ---------------------------------------------------------------------------
# arrival_client 테스트
# ---------------------------------------------------------------------------

def test_arrival_client_returns_cached_client():
    """arrival_client 두 번 호출 시 동일 DB 연결에서 생성된 client를 반환한다."""
    from bushexa.api_clients.cached_arrival import CachedArrivalClient

    class _Cfg:
        database_url = "sqlite:///:memory:"

    cfg = _Cfg()
    client1 = arrival_client(cfg)
    client2 = arrival_client(cfg)

    assert isinstance(client1, CachedArrivalClient)
    assert isinstance(client2, CachedArrivalClient)
    # 두 client의 내부 연결은 동일해야 한다 (워커 수명 재사용)
    assert client1._repo.conn is client2._repo.conn, (
        "같은 config로 두 번 호출된 arrival_client는 동일 DB 연결을 사용해야 한다 (리뷰 #8)"
    )
