"""노선도(graph-not-map) — 노선별 세로 정류장 목록(HTML) 데이터 모듈.

가로 SVG 다이어그램은 라벨이 겹쳐 읽기 어려워, 노선마다 카드 하나에 정류장을
경로 순서대로 세로로 나열하는 방식으로 바꿨다. UNIST를 강조하고, 정류장을 누르면
관련 화면으로 이동한다.

  - UNIST            → 그 노선 UNIST 출발 시간표(/busno?bus=…)
  - 도착 조회 가능 정류장 → 정류소별 도착(/stops?stop_id=…), UNIST 방면(돌아오는 방향)만
  - 그 외             → 링크 없음(일반 텍스트)

노선을 추가/수정하려면 ``LINE_STOPS`` / ``STOP_LABEL`` / ``STOP_LINK``만 바꾸면 된다.
구영리 안에서 513·743은 범서중학교 경유("범서중"), 713·753·1115는 "구영"이다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

LINE_ORDER: list[str] = ["513", "713", "743", "753", "1115"]

# 앱 전역 배지 색(static/style.css의 .route-XXX)과 일치.
COLORS: dict[str, str] = {
    "513": "#D32F2F",
    "713": "#388E3C",
    "743": "#1976D2",
    "753": "#7B1FA2",
    "1115": "#F57C00",
}

# 743은 이 날짜부터 구영리(범서중학교)를 경유한다(그 전에는 예고 표시).
VIA_743_BEOMSEO_FROM = date(2026, 10, 3)

# 각 노선의 정류장(경로 순서, 앞이 UNIST 쪽 — 513은 삼남 쪽부터).
LINE_STOPS: dict[str, list[str]] = {
    "513": ["삼남", "울산역", "UNIST", "범서중", "굴화주공", "시청", "덕하"],
    "713": ["UNIST", "천상", "구영", "굴화주공", "태화루", "성남동", "삼산", "태화강역", "명촌"],
    "743": [
        "UNIST", "천상", "범서중", "굴화주공", "신복교차로", "울산대학교", "법원",
        "공업탑", "삼산", "태화강역", "명촌",
    ],
    "753": [
        "UNIST", "구영", "굴화주공", "신복교차로", "울산대학교", "산단캠", "공업탑",
        "삼산", "태화강역", "명촌",
    ],
    "1115": [
        "UNIST", "천상", "구영", "굴화주공", "태화루", "시청", "삼산", "태화강역",
        "염포동", "남목", "현대중공업·울산대학병원", "일산해수욕장", "꽃바위",
    ],
}

# 화면 표시명(없으면 키 그대로).
STOP_LABEL: dict[str, str] = {
    "구영": "구영리",
    "범서중": "구영리 (범서중학교)",
    "태화루": "태화루 (국가정원)",
    "산단캠": "산학융합지구캠퍼스",
    "울산역": "울산역 (KTX)",
}

# 정류장 → 도착 조회용 stop_id. UNIST 방면(돌아오는 방향)이 확인된 정류소만 둔다.
# 값은 반드시 constants.SERACH_STOPS에 있어야 한다(/partial/stops 검증).
STOP_LINK: dict[str, str] = {
    "천상": "196020808",       # 천상 (UNIST)
    "구영": "196020416",       # 우미린2차 푸르지오2차 (UNIST)
    "굴화주공": "193040224",   # 굴화주공 아파트앞 (UNIST)
    "태화강역": "193012314",   # 태화강역 (UNIST)
}


@dataclass(frozen=True)
class StopView:
    label: str
    href: str | None
    is_unist: bool
    is_branch: bool  # 구영리 내 범서중 경유 등, 노선마다 갈리는 지점
    note: str | None


@dataclass(frozen=True)
class LineView:
    line: str
    color: str
    stops: list[StopView]


def _href(line: str, stop: str) -> str | None:
    if stop == "UNIST":
        return f"/busno?bus={line}"
    sid = STOP_LINK.get(stop)
    return f"/stops?stop_id={sid}" if sid else None


def build_route_lines(today: date | None = None) -> list[LineView]:
    """노선별 정류장 뷰 모델. 10/3 이전에는 743의 범서중을 "10/3부터" 예고로 표시한다."""
    today = today or date.today()
    out: list[LineView] = []
    for line in LINE_ORDER:
        stops = []
        for n in LINE_STOPS[line]:
            note = None
            if n == "범서중" and line == "743":
                note = "10/3부터" if today < VIA_743_BEOMSEO_FROM else None
            stops.append(StopView(
                label=STOP_LABEL.get(n, n),
                href=_href(line, n),
                is_unist=(n == "UNIST"),
                is_branch=(n in ("범서중", "구영")),
                note=note,
            ))
        out.append(LineView(line=line, color=COLORS[line], stops=stops))
    return out
