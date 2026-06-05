"""변경이력(changelog) CRUD 저장소.

info 페이지의 "Update History"에 표시되는 항목을 관리자 페이지에서 편집할 수 있게 한다.

저장 위치(단일 진실원천): ``<data_dir>/changelog.json`` — 런타임 쓰기 가능 볼륨.
(holidays.json·special_timetables.json 과 동일 범주: 관리자 편집 데이터)

seed: ``<package>/web/static/data/changelog.json`` — 이미지에 구워진 공장 초기값.
data_dir 파일이 아직 없을 때만 **읽기 전용**으로 폴백한다. 저장은 항상 data_dir 에만 쓴다.
admin이 처음 추가/삭제하면 seed 항목이 그대로 data_dir 로 이관(persist)된다.

구조: ``[{"date": "YYYY-MM-DD", "description": "..."}, ...]`` (표시 순서 = 날짜 오름차순).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from bushexa.fileio import atomic_write_json

# info.html 의 기존 항목이 "2024-12-21" 형식이므로 <input type="date">와 동일한 YYYY-MM-DD.
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def default_changelog_path(data_dir) -> Path:
    """편집본 changelog 파일의 기본 경로 (``<data_dir>/changelog.json``)."""
    return Path(data_dir) / "changelog.json"


def _read(path: Path) -> list[dict] | None:
    """파일을 읽어 검증된 항목 리스트로 반환. 부재·파손·형식불일치 시 None."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    if not isinstance(data, list):
        return None
    rows: list[dict] = []
    for e in data:
        if (
            isinstance(e, dict)
            and isinstance(e.get("date"), str)
            and isinstance(e.get("description"), str)
        ):
            rows.append({"date": e["date"], "description": e["description"]})
    return rows


class ChangelogEditor:
    """변경이력의 로드/추가/제거/저장.

    live_path(data_dir)가 있으면 그것만 사용한다. 없을 때만 seed_path(static)로 폴백.
    """

    def __init__(self, live_path, seed_path=None):
        self.live_path = Path(live_path)
        self.seed_path = Path(seed_path) if seed_path is not None else None

    def load(self) -> list[dict]:
        """현재 변경이력. live(data_dir) 우선, 없으면 seed(static) 폴백, 둘 다 없으면 []."""
        if self.live_path.exists():
            rows = _read(self.live_path)
            if rows is not None:
                return rows
        if self.seed_path is not None and self.seed_path.exists():
            rows = _read(self.seed_path)
            if rows is not None:
                return rows
        return []

    def save(self, rows) -> None:
        """항목 리스트를 data_dir 에 원자적으로 저장. 형식 불일치 항목은 제거, 날짜 오름차순 정렬."""
        cleaned = [
            {"date": str(r["date"]), "description": str(r["description"]).strip()}
            for r in rows
            if isinstance(r, dict)
            and _DATE_RE.match(str(r.get("date", "")))
            and str(r.get("description", "")).strip()
        ]
        cleaned.sort(key=lambda r: r["date"])
        atomic_write_json(self.live_path, cleaned, ensure_ascii=False, indent=2)

    def add(self, date_str: str, description: str) -> bool:
        """항목 추가 후 저장. 날짜가 YYYY-MM-DD가 아니거나 설명이 비면 False."""
        date_str = (date_str or "").strip()
        description = (description or "").strip()
        if not _DATE_RE.match(date_str) or not description:
            return False
        rows = self.load()
        rows.append({"date": date_str, "description": description})
        self.save(rows)
        return True

    def remove(self, index: int) -> bool:
        """표시 순서 기준 index 항목을 제거 후 저장. 범위 밖이면 False.

        load()가 날짜 오름차순(=템플릿 표시 순서)을 반환하므로 index가 화면과 일치한다.
        """
        rows = self.load()
        if not isinstance(index, int) or not (0 <= index < len(rows)):
            return False
        rows.pop(index)
        self.save(rows)
        return True
