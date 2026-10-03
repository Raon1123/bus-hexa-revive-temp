"""노포 연계 구간 소요 실측 — cache-refresh 가 통과기록(bus_timelog)에서 하루 1회 요약한다.

``/busan`` 노포 루트의 "시간표로 보는 연계"가 읽는 입력(``<data_dir>/nopo_leg_profile.json``)이다.
형식·측정 방법은 ``leg_profile`` 과 같고 구간만 ``BUSAN_NOPO_LEGS`` 다. 통과기록이 없거나 읽기에
실패하면 기존 파일을 덮지 않는다(좋은 캐시를 실패 결과로 덮지 않는다).
"""
from __future__ import annotations

import logging
from pathlib import Path

from bushexa.data.constants import BUSAN_NOPO_LEGS
from bushexa.services.leg_profile import (
    build_leg_profile,
    collect_passages,
    holidays_for_span,
    load_profile,
    save_profile,
)
from bushexa.services.holiday_service import read_effective_holidays
from bushexa.time_utils import KSTClock

logger = logging.getLogger("bushexa.services.nopo_profile")


def nopo_profile_path(data_dir) -> Path:
    return Path(data_dir) / "nopo_leg_profile.json"


def load_nopo_profile(data_dir) -> dict | None:
    """공개 화면용 읽기. 없거나 깨졌으면 None(화면은 추정치로 대체한다)."""
    return load_profile(nopo_profile_path(data_dir))


def refresh_nopo_profile(config, *, clock=None) -> bool:
    """DB 통과기록 → 노포 구간 프로필 갱신. 갱신했으면 True, 기록이 없어 건너뛰면 False."""
    clock = clock or KSTClock()
    passages, sources = collect_passages(db_url=config.database_url, legs=BUSAN_NOPO_LEGS)
    if not passages:
        logger.info("노포 구간 통과기록이 아직 없습니다 — 프로필 갱신 건너뜀")
        return False
    holidays = holidays_for_span(passages, read_effective_holidays(config.data_dir))
    profile = build_leg_profile(passages, holidays, generated_at=clock.now().isoformat(),
                                sources=sources, legs=BUSAN_NOPO_LEGS)
    save_profile(nopo_profile_path(config.data_dir), profile)
    logger.info("노포 구간 프로필 갱신: %s", {k: sum(d["all"]["n"] for d in v["by_day"].values())
                                          for k, v in profile["legs"].items()})
    return True
