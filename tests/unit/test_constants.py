"""W1 constants 이전 검증. 기대값은 데이터 자체의 무결성 불변식에서 도출(E-13)."""
from __future__ import annotations


def test_all_symbols_importable():
    """constants에서 7개 공개 심볼이 ImportError 없이 로드되고 ROUTEID 길이가 정확히 10인지."""
    from bushexa.data.constants import (  # noqa: F401
        ROUTEID, STOP_IDS, SERACH_STOPS, VIA_STOPS, UNISTBUS, ULSAN_CITYCODE, ULSAN_PREFIX,
    )

    assert len(ROUTEID) == 10


def test_routeid_stops_subset_of_stop_ids():
    """ROUTEID 각 노선의 정류장 시퀀스(4번째 요소)의 모든 stop_id가 STOP_IDS 키에 존재하는지.

    누락 시 govtrack의 stop_name 조회가 깨지므로 데이터 무결성 보증.
    """
    from bushexa.data.constants import ROUTEID, STOP_IDS

    missing = []
    for route_id, info in ROUTEID.items():
        stop_ids = info[3]
        for sid in stop_ids:
            if sid not in STOP_IDS:
                missing.append((route_id, sid))
    assert not missing, f"STOP_IDS에 없는 정류장: {missing}"


def test_stop_ids_values_nonempty():
    """STOP_IDS의 모든 값(정류장 한글명)이 빈 문자열이 아닌지."""
    from bushexa.data.constants import STOP_IDS

    assert all(str(v).strip() for v in STOP_IDS.values())
