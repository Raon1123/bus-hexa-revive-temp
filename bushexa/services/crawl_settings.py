"""크롤 주기 런타임 설정 — admin이 쓰고(단일 writer) 데몬이 매 사이클 재읽는다.

2026-06-05 사용자 요구: 관리자 페이지에서 govtrack/arrival 폴링 주기를 변경할 수 있어야
한다. 설계 제약(같은 날 코드리뷰 #6·#9의 교훈): ``current_app.config`` 같은 프로세스
메모리는 gunicorn 워커 사이에서도 공유되지 않으므로 별도 supervisord 데몬에는 절대 닿지
않는다 → 반드시 파일로 영속하고 데몬이 사이클마다 재읽는다. 적용 지연은 최대
'현재 주기 + 사이클 시간' 1회분이다.

editor-서비스 패턴(holiday_editor 등)과 동일하게 ``fileio.atomic_write_json`` 으로 기록한다.
writer는 admin 단 한 곳이므로 audit_log(리뷰 #7)와 같은 lost-update 문제가 없다.

하한 ``MIN_POLL_SECONDS`` 는 0/음수 설정이 busy-loop로 API 쿼터를 소진하는 사고 방지
(2026-06-05에 수정한 쿼터 오류 계열의 회귀 방지). 검증 정책의 비대칭에 주의:
- ``save()`` 는 엄격 — 범위 밖 값은 ValueError (admin 폼이 사용자에게 거부 사유 표시).
- ``load()`` 는 관대 — 파일 부재/파손/범위 밖 필드는 경고 로그 후 무시하고 기본값으로
  폴백한다(설정 파일이 깨져도 데몬은 절대 죽거나 멈추지 않는다, ADR-013).
"""
from __future__ import annotations

import logging
from pathlib import Path

from bushexa.fileio import atomic_write_json, read_json

logger = logging.getLogger("bushexa.services.crawl_settings")

MIN_POLL_SECONDS = 3.0    # busy-loop·쿼터 소진 방지 하한
MAX_POLL_SECONDS = 600.0  # 실수로 사실상 정지시키는 값 방지 상한

#: 저장 파일이 가질 수 있는 필드(이외 키는 load 시 무시).
FIELDS = ("govtrack_poll_seconds", "arrival_poll_seconds")


def default_crawl_settings_path(data_dir) -> Path:
    """설정 파일 경로 (``<data_dir>/crawl_settings.json``)."""
    return Path(data_dir) / "crawl_settings.json"


def validate_poll_seconds(name: str, value) -> float:
    """폴링 주기 1개 값 검증. 숫자이며 [MIN, MAX] 범위여야 한다. 위반 시 ValueError."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name}: 숫자가 아님: {value!r}") from None
    if not (MIN_POLL_SECONDS <= v <= MAX_POLL_SECONDS):
        raise ValueError(
            f"{name}: {v:g}초는 허용 범위({MIN_POLL_SECONDS:g}~{MAX_POLL_SECONDS:g}초) 밖"
        )
    return v


class CrawlSettingsStore:
    """``crawl_settings.json`` 읽기/쓰기. 데몬은 read-only, admin만 write."""

    def __init__(self, path):
        self.path = Path(path)

    def load(self) -> dict[str, float]:
        """검증을 통과한 필드만 담은 dict. 파일 부재/파손/범위 밖 값은 무시(기본값 폴백)."""
        data = read_json(self.path, {}, expect=dict,
                                warn_label="크롤 설정", logger=logger)
        out: dict[str, float] = {}
        for name in FIELDS:
            if name not in data:
                continue
            try:
                out[name] = validate_poll_seconds(name, data[name])
            except ValueError as exc:
                logger.warning("크롤 설정 값 무시(기본값 사용): %s", exc)
        return out

    def govtrack_poll_seconds(self, default) -> float:
        """govtrack 데몬 유효 주기 — 설정값이 있으면 그 값, 없으면 ``default``."""
        return self.load().get("govtrack_poll_seconds", float(default))

    def arrival_poll_seconds(self, default) -> float:
        """arrival poller 유효 주기 — 설정값이 있으면 그 값, 없으면 ``default``."""
        return self.load().get("arrival_poll_seconds", float(default))

    def save(self, *, govtrack_poll_seconds=None, arrival_poll_seconds=None) -> dict[str, float]:
        """주어진 필드만 기록(None은 해당 필드 제거 → 기본값 복귀). 기록된 dict 반환.

        범위 밖 값은 ValueError — 호출자(admin 폼)가 거부 사유를 표시한다.
        """
        given = {"govtrack_poll_seconds": govtrack_poll_seconds,
                 "arrival_poll_seconds": arrival_poll_seconds}
        out: dict[str, float] = {}
        for name, value in given.items():
            if value is not None:
                out[name] = validate_poll_seconds(name, value)
        atomic_write_json(self.path, out, ensure_ascii=False, indent=2)
        return out
