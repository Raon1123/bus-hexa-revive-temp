"""W7c H9/EC-6 lint: bushexa/ 전체에 컨테이너 경로 하드코딩과 streamlit 의존이 0건인지 단언.

표본화·휘발성 결함과 달리 이런 결함은 grep으로 능동 탐지한다(PM-001 교훈). 본 테스트가
회귀 가드 역할을 해, 누군가 컨테이너 경로를 다시 박거나 streamlit을 들이면 즉시 실패한다.
"""
from __future__ import annotations

from pathlib import Path

BUSHEXA = Path(__file__).parents[2] / "bushexa"
_HARDCODED = "/app/" + "logs"  # 리터럴이 본 파일 자신에 박히지 않도록 분리 구성


def _py_files(root: Path):
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


def test_no_hardcoded_app_logs():
    """bushexa/ 전체를 스캔해 컨테이너 경로(/app/logs) 하드코딩이 0건인지 단언한다 — H9 회귀."""
    offenders = [str(p) for p in _py_files(BUSHEXA)
                 if _HARDCODED in p.read_text(encoding="utf-8")]
    assert offenders == [], f"컨테이너 경로 하드코딩 발견: {offenders}"


def test_no_streamlit_in_crawler():
    """bushexa/crawler/ 전체에 import streamlit이 0건인지 단언한다 — EC-6/AC-S2 회귀."""
    crawler = BUSHEXA / "crawler"
    offenders = [str(p) for p in _py_files(crawler)
                 if "import streamlit" in p.read_text(encoding="utf-8")]
    assert offenders == [], f"crawler에 streamlit 의존 발견: {offenders}"
