"""노선도 SVG 빌더 테스트 (route_diagram).

테스트 의도:
  test_five_lines        — 5개 노선 색·path가 모두 등장
  test_key_stations      — 핵심 정류장명(1115 동측 포함)이 모두 등장
  test_columns_monotonic — 각 노선의 정류장 컬럼이 경로순으로 단조증가(꺾임 불필요 전제)
  test_shared_box        — 둘 이상 정차하는 정류장에 공유박스가 생긴다
"""

from __future__ import annotations

from bushexa.web.route_diagram import (
    COLORS,
    COLS,
    LINE_ORDER,
    LINE_STOPS,
    render_route_diagram,
)


def test_five_lines():
    svg = str(render_route_diagram())
    # 노선 본선 path 5개 (stub <line>은 별도)
    assert svg.count('<path class="route-line"') == len(LINE_ORDER) == 5
    for color in COLORS.values():
        assert color in svg, f"색 {color} 누락"


def test_terminus_badges():
    """각 노선 양 끝(종점)에 번호 배지가 있고, 번호 텍스트가 배지로 표시된다."""
    svg = str(render_route_diagram())
    # 노선마다 양끝 2개 → rect 배지 5*2 = 10
    assert svg.count('class="route-pill"') == len(LINE_ORDER) * 2 == 10
    for line in LINE_ORDER:
        # 배지 텍스트로 노선번호 등장
        assert f">{line}</text>" in svg, f"종점 배지 번호 {line} 누락"


def test_east_termini():
    """713/743/753 동쪽 종점이 명촌까지 연장된다(timetable JSON 종점 키와 일치)."""
    for line in ("713", "743", "753"):
        assert LINE_STOPS[line][-1] == "명촌", f"{line} 동쪽 종점이 명촌이 아님"
    assert LINE_STOPS["513"][-1] == "덕하"
    assert LINE_STOPS["1115"][-1] == "꽃바위"


def test_key_stations():
    svg = str(render_route_diagram())
    for stop in (
        "삼남", "울산역", "UNIST", "천상", "구영", "태화루", "시청",
        "신복교차로", "울산대학교", "법원", "산단캠", "삼산", "태화강역",
        "덕하", "염포동", "남목", "현대중공업", "일산해수욕장", "꽃바위",
    ):
        assert stop in svg, f"정류장 {stop} 누락"


def test_columns_monotonic():
    """각 노선의 정류장 컬럼이 경로순으로 strictly increasing — 선 꺾임이 불필요한 전제."""
    for line, stops in LINE_STOPS.items():
        cols = [COLS[s] for s in stops]
        assert cols == sorted(cols) and len(set(cols)) == len(cols), (
            f"{line} 컬럼이 단조증가 아님: {cols}"
        )


def test_shared_box():
    """둘 이상 정차하는 정류장(UNIST 등)에 공유박스(rect)가 생긴다."""
    svg = str(render_route_diagram())
    # UNIST(5개)·삼산·태화강역 등 공유박스가 있어야 하고, 노선 수보다 박스가 적어야 함
    n_boxes = svg.count("route-box")
    assert n_boxes >= 5, f"공유박스가 너무 적음: {n_boxes}"
