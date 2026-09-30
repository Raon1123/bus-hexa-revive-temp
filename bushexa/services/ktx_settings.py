"""KTX 연계표 환승 최소 시간 기본값(``ktx_settings.json``) — 관리자가 쓰고 /ktx·CLI 가 읽는다.

쿼리 ``?ts=&tj=`` 가 우선. save 는 엄격(ValueError), load 는 관대(깨진 값 → 기본값).
"""
from __future__ import annotations

import logging
from pathlib import Path

from bushexa.data.constants import (
    KTX_CONNECT_TRANSFER_MIN,
    KTX_JINMOK_TRANSFER_MIN,
    KTX_TRANSFER_MAX_MIN,
)
from bushexa.fileio import atomic_write_json, read_json

logger = logging.getLogger("bushexa.services.ktx_settings")

#: 필드 → 코드 기본값
DEFAULTS = {"transfer_station_min": KTX_CONNECT_TRANSFER_MIN,
            "transfer_jinmok_min": KTX_JINMOK_TRANSFER_MIN}


def default_ktx_settings_path(data_dir) -> Path:
    return Path(data_dir) / "ktx_settings.json"


def validate_minutes(name: str, value) -> int:
    """0 ~ ``KTX_TRANSFER_MAX_MIN`` 정수 분. 위반 시 ValueError."""
    try:
        v = int(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError(f"{name}: 정수가 아님: {value!r}") from None
    if not 0 <= v <= KTX_TRANSFER_MAX_MIN:
        raise ValueError(f"{name}: {v}분은 허용 범위(0~{KTX_TRANSFER_MAX_MIN}분) 밖")
    return v


class KtxSettingsStore:
    def __init__(self, path):
        self.path = Path(path)

    def load(self) -> dict[str, int]:
        """저장된 필드 중 검증을 통과한 것만(없으면 빈 dict)."""
        data = read_json(self.path, {}, expect=dict, warn_label="KTX 연계 설정", logger=logger)
        out: dict[str, int] = {}
        for name in DEFAULTS:
            if name not in data:
                continue
            try:
                out[name] = validate_minutes(name, data[name])
            except ValueError as exc:
                logger.warning("KTX 연계 설정 값 무시(기본값 사용): %s", exc)
        return out

    def effective(self) -> dict[str, int]:
        """코드 기본값 위에 저장값을 덮은 유효 설정."""
        return {**DEFAULTS, **self.load()}

    def save(self, **values) -> dict[str, int]:
        """주어진 필드만 기록(None 은 제거 → 코드 기본값 복귀). 기록된 dict 반환."""
        out: dict[str, int] = {}
        for name in DEFAULTS:
            value = values.get(name)
            if value is not None and str(value).strip() != "":
                out[name] = validate_minutes(name, value)
        atomic_write_json(self.path, out, ensure_ascii=False, indent=2)
        return out
