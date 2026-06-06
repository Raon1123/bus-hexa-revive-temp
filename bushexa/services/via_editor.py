"""경유지(주요 정류소) 문자열 편집 저장소.

출발 게시판의 '경유' 표시는 노선·방향별 주요 정류소를 손질한 문자열(VIA_STOPS, 코드 상수)
이다. 운영자가 코드 수정 없이 이를 고칠 수 있도록, 편집분을 JSON 파일에 override로 저장한다.

우선순위(도메인 board._via_for): **override(이 파일) > 상수 VIA_STOPS > 노선 정류장 fallback**.
구조: ``{ busno: { dest_key: "경유 문자열" } }`` (dest_key = 목적지명, 예: "명촌").
"""
from __future__ import annotations

from pathlib import Path

from bushexa.fileio import atomic_write_json, read_json


def default_via_path(data_dir) -> Path:
    """override 파일의 기본 경로(`<data_dir>/via_overrides.json`)."""
    return Path(data_dir) / "via_overrides.json"


class ViaEditor:
    """경유지 override의 로드/저장. 파일이 없으면 빈 override로 간주."""

    def __init__(self, path):
        self.path = Path(path)

    def load(self) -> dict[str, dict[str, str]]:
        """override dict 반환. 파일 부재·파손 시 빈 dict(상수 fallback이 적용됨)."""
        data = read_json(self.path, {}, expect=dict)
        # 형태 정규화: busno→{dest:str}
        out: dict[str, dict[str, str]] = {}
        for busno, dests in data.items():
            if isinstance(dests, dict):
                out[str(busno)] = {
                    str(k): str(v) for k, v in dests.items() if isinstance(v, str) or v is not None
                }
        return out

    def save(self, overrides: dict[str, dict[str, str]]) -> None:
        """override dict를 atomic하게 저장. 빈 문자열 항목은 제거(상수 기본값으로 복귀)."""
        cleaned: dict[str, dict[str, str]] = {}
        for busno, dests in overrides.items():
            inner = {k: v.strip() for k, v in dests.items() if v and v.strip()}
            if inner:
                cleaned[str(busno)] = inner
        atomic_write_json(self.path, cleaned, ensure_ascii=False, indent=2)
