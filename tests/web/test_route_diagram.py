"""노선도 SVG 빌더 테스트 (route_diagram) — 실제 위치를 참고한 개략 노선도.

테스트 의도:
  test_five_lines            — 5개 노선 선(path)과 색이 모두 등장
  test_terminus_badges       — 노선마다 양 끝 종점에 번호 pill 이 붙는다(색만으로 구분하지 않음)
  test_east_termini          — 종점이 시간표 종점 키와 일치
  test_key_stations          — 핵심 정류장명이 모두 그려진다
  test_paths_defined         — 노선 경로의 모든 노드가 NODES 에 있고, 좌표가 겹치는 노드가 없다
  test_paths_octilinear      — 모든 구간이 가로·세로·45° (지하철 노선도식 규칙)
  test_rough_geography       — 동서남북 관계가 실제 위치와 맞는다(거리까지는 보지 않음)
  test_shared_capsules       — 여러 노선이 서는 정류장은 캡슐로 그린다
  test_743_beomseo_only_from_oct3 — 743 범서중 경유는 2026-10-03부터
  test_1115_skips_yeompo     — 1115 는 염포동·태화강역 1번 정류소에 서지 않는다
  test_1115_asanro_from_oct3 — 1115 는 10/3부터 현대자동차 대신 아산로로 간다
  test_guyeong_two_roads     — 구영리: 513·743 은 범서중 길만, 713·753·1115 는 구영 길만
  test_rails                 — KTX 는 울산역, 동해선은 태화강역·덕하와 환승 표시
  test_stations_interactive  — 정류장·pill 은 키보드로 누를 수 있고, 링크는 조회 가능한 정류소만
"""

from __future__ import annotations

from datetime import date

from bushexa.data.constants import ROUTE_MAP_STOP_LINK, SERACH_STOPS
from bushexa.web.route_diagram import (
    COLORS,
    LINE_ORDER,
    LINE_PATHS,
    LINE_STOPS,
    NODES,
    RAILS,
    ROUTE_CHANGES,
    paths_for,
    render_route_diagram,
    stops_for,
)

AFTER = date(2026, 10, 3)


def test_five_lines():
    """노선마다 선 하나(path)가 있고 앱 전역 노선 색을 쓴다."""
    svg = str(render_route_diagram(AFTER))
    assert svg.count('<path class="route-line"') == len(LINE_ORDER) == 5
    for line, color in COLORS.items():
        assert f'data-line="{line}"' in svg
        assert color in svg, f"색 {color} 누락"


def test_terminus_badges():
    """각 노선 양 끝(종점)에 번호 pill 이 있고, 번호가 글자로 표시된다."""
    svg = str(render_route_diagram(AFTER))
    assert svg.count('class="route-pill"') == len(LINE_ORDER) * 2 == 10
    for line in LINE_ORDER:
        assert f">{line}</text>" in svg, f"종점 배지 번호 {line} 누락"


def test_east_termini():
    """713/743/753 은 명촌, 513 은 덕하, 1115 는 꽃바위가 시내 방면 종점이다(시간표 JSON 종점 키)."""
    for line in ("713", "743", "753"):
        assert LINE_STOPS[line][0] == "UNIST"
        assert LINE_STOPS[line][-1] == "명촌", f"{line} 동쪽 종점이 명촌이 아님"
    assert LINE_STOPS["513"][0] == "삼남" and LINE_STOPS["513"][-1] == "덕하"
    assert LINE_STOPS["1115"][0] == "UNIST" and LINE_STOPS["1115"][-1] == "꽃바위"


def test_key_stations():
    """승객이 찾는 핵심 정류장 이름이 노선도에 모두 보인다."""
    svg = str(render_route_diagram(AFTER))
    for stop in (
        "삼남", "울산역", "UNIST", "천상", "구영", "범서중", "굴화주공", "태화루", "시청",
        "신복교차로", "울산대학교", "법원", "산단캠", "공업탑", "삼산", "태화강역",
        "태화강역광장", "명촌", "덕하", "남목", "현대중공업", "일산해수욕장", "꽃바위",
    ):
        assert f">{stop}<" in svg, f"정류장 {stop} 누락"
    assert ">현대자동차<" in str(render_route_diagram(date(2026, 10, 2)))  # 1115, 10/2까지


def test_paths_defined():
    """경로의 노드는 모두 정의돼 있고, 서로 다른 노드가 같은 격자 칸을 쓰지 않는다(겹쳐 보임 방지)."""
    for line, path in LINE_PATHS.items():
        for name in path:
            assert name in NODES, f"{line}: 정의되지 않은 노드 {name}"
    seen: dict[tuple[float, float], str] = {}
    for name, n in NODES.items():
        assert (n.x, n.y) not in seen, f"{name} 와 {seen.get((n.x, n.y))} 좌표가 같음"
        seen[(n.x, n.y)] = name


def test_paths_octilinear():
    """모든 구간은 가로·세로·45° 로만 그어진다(743 구 경로 포함)."""
    paths = list(LINE_PATHS.values()) + list(paths_for(date(2026, 10, 2)).values())
    for path in paths:
        for a, b in zip(path, path[1:]):
            dx = NODES[b].x - NODES[a].x
            dy = NODES[b].y - NODES[a].y
            assert (dx, dy) != (0, 0), f"{a}→{b} 길이 0"
            assert dx == 0 or dy == 0 or abs(dx) == abs(dy), f"{a}→{b} 가 45° 배수가 아님"


def test_rough_geography():
    """정확한 거리는 아니지만 실제 위치의 동서·남북 관계는 지킨다(x 동쪽, y 남쪽이 큼)."""
    n = NODES
    west_to_east = ["삼남", "울산역", "UNIST", "천상", "굴화주공", "태화루", "시청", "삼산",
                    "태화강역", "현대자동차", "남목"]
    xs = [n[s].x for s in west_to_east]
    assert xs == sorted(xs), "서→동 순서가 실제와 다름"
    assert n["UNIST"].y < n["울산역"].y          # UNIST 는 울산역보다 북쪽
    assert n["명촌"].y < n["태화강역"].y          # 명촌은 태화강역 북쪽(강 건너)
    assert n["태화강역광장"].y < n["태화강역"].y  # 광장 정류장은 1번 정류소보다 북쪽
    assert n["태화루"].y < n["시청"].y < n["공업탑"].y < n["덕하"].y
    assert n["남목"].y < n["현대중공업·울산대학병원"].y < n["일산해수욕장"].y < n["꽃바위"].y


def test_shared_capsules():
    """둘 이상 정차하는 정류장(UNIST·굴화주공·삼산 등)은 흰 캡슐로, 단독 정류장은 원으로 그린다."""
    svg = str(render_route_diagram(AFTER))
    assert svg.count('class="route-box"') >= 8
    assert 'class="route-stop"' in svg


def test_743_beomseo_only_from_oct3():
    """743의 범서중 경유는 2026-10-03부터 반영된다(그 전에는 513만 범서중, 743은 천상 → 구영교)."""
    before = paths_for(date(2026, 10, 2))["743"]
    after = paths_for(date(2026, 10, 3))["743"]
    assert "범서중" not in before and "천상남" in before
    assert "범서중" in after and "천상남" not in after
    # 범서중: 시행 전에는 513 단독 원, 이후에는 513+743 캡슐
    svg_before = str(render_route_diagram(date(2026, 10, 2)))
    svg_after = str(render_route_diagram(date(2026, 10, 3)))
    assert svg_after.count('class="route-box"') == svg_before.count('class="route-box"') + 1


def test_1115_skips_yeompo():
    """(10/2까지) 1115는 태화강역광장 → 현대자동차(명촌정문·양정) → 남목으로 가고 염포동·태화강역 1번 정류소에 서지 않는다."""
    stops = stops_for(date(2026, 10, 2))["1115"]
    assert "염포동" not in stops
    assert "태화강역" not in stops  # 1번 정류소 미정차: 역 앞 태화강역광장만 지난다
    i = stops.index("태화강역광장")
    assert stops[i + 1 : i + 3] == ["현대자동차", "남목"]
    assert "염포동" not in str(render_route_diagram(AFTER))


def test_1115_asanro_from_oct3():
    """울산버스 공지(10/3 시행): 1115 는 명촌정문~성원상떼빌 7개 정류소에 서지 않고 아산로로 간다."""
    before = stops_for(date(2026, 10, 2))["1115"]
    after = stops_for(date(2026, 10, 3))["1115"]
    assert "현대자동차" in before and "현대자동차" not in after
    assert "아산로" in paths_for(date(2026, 10, 3))["1115"]
    assert "아산로" not in paths_for(date(2026, 10, 2))["1115"]
    assert after[after.index("태화강역광장") + 1] == "남목"
    assert {c.line for c in ROUTE_CHANGES} == {"743", "1115"}


def test_guyeong_two_roads():
    """구영리는 두 갈래: 범서중 길(513·743)과 구영 길(713·753·1115). 513은 구영에 서지 않는다."""
    for line in ("513", "743"):
        assert "범서중" in LINE_STOPS[line] and "구영" not in LINE_STOPS[line], line
    for line in ("713", "753", "1115"):
        assert "구영" in LINE_STOPS[line] and "범서중" not in LINE_STOPS[line], line


def test_rails():
    """철도는 배경으로 그리고, 지나는 정류장에 환승 테두리를 그린다."""
    by = {r.key: r for r in RAILS}
    assert by["ktx"].stations == ["울산역"]
    assert set(by["donghae"].stations) == {"태화강역", "덕하"}
    svg = str(render_route_diagram(AFTER))
    assert svg.count('class="route-rail"') == 2
    assert "KTX 경부고속선" in svg and "동해선" in svg
    assert 'data-stop="태화강역"' in svg and 'data-rail="동해선"' in svg


def test_stations_interactive():
    """정류장 그룹과 종점 pill 은 tabindex·role 을 갖고, 도착 링크는 SERACH_STOPS 정류소만 가리킨다."""
    svg = str(render_route_diagram(AFTER))
    n_stations = len({s for stops in LINE_STOPS.values() for s in stops})
    assert svg.count('class="route-station" tabindex="0" role="button"') == n_stations
    assert svg.count('class="route-pill-btn"') == 10
    for name, sid in ROUTE_MAP_STOP_LINK.items():
        assert sid in SERACH_STOPS, f"{name}: {sid} 는 /stops 에서 조회 불가"
        assert name in NODES and NODES[name].label, f"{name} 은 노선도 정류장이 아님"
        assert f'data-href="/stops?stop_id={sid}"' in svg
