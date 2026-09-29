"""노선도 — 실제 위치를 참고한 개략 노선도(지하철 노선도식) 인라인 SVG 빌더.

정류장을 격자 좌표(``NODES``)에 손으로 배치한다. 좌표는 실제 위치(국토부 TAGO 정류장 좌표)를
참고해 동서남북 관계와 순서만 맞춘 것이고, 거리는 정확하지 않다. 선은 가로·세로·45°로만 긋는다.
배경의 태화강·울산만·동해와 철도(KTX 경부고속선, 동해선)도 모양만 흉내 낸 것이다.

데이터:
  ``NODES``          정류장/경유점 → 격자 좌표. ``label`` 이 있으면 정류장, 없으면 선 모양을 잡는 경유점.
  ``LINE_PATHS``     노선별 운행 순서(경유점 포함, 최신 노선 기준). 라벨이 있는 노드는 그 노선이 서는 정류장.
  ``ROUTE_CHANGES``  시행일이 있는 경로 변경. 시행일(KST) 전에는 새 구간을 옛 구간으로 되돌려 그린다.
  ``RAILS``          철도(배경). 지나는 정류장은 환승 표시(검은 테두리)를 한다.

그리기 규칙:
  - 두 노드 사이 구간을 여러 노선이 함께 지나면 나란히(평행 오프셋) 그린다. 쌓는 순서는
    구간 양 끝에서 어느 쪽으로 갈라지는지로 정해, 교차는 정류장 캡슐 안에서만 생기게 한다.
  - 둘 이상 정차하는 정류장은 흰 캡슐, 한 노선만 서는 정류장은 노선 색 테두리 원.
  - 각 노선 양 끝(종점)에 번호 pill 을 붙인다(색만으로 노선을 구분하지 않게).
  - 정류장·pill 에는 ``data-*`` 속성을 달아 ``static/js/route_map.js`` 가 강조·정보 패널을 붙인다.
    JS 가 없어도 지도 자체는 완성된 그림이다.

이름이 같아도 노선마다 실제 정차 지점이 다르면 별도 노드로 둔다
(``구영`` vs ``범서중``, 713·743·753 의 ``태화강역`` 1번 정류소 vs 1115 의 ``태화강역광장``).
"""

from __future__ import annotations

import math
from datetime import date
from typing import NamedTuple

from markupsafe import Markup, escape

from bushexa.data.constants import ROUTE_MAP_STOP_LINK, STOP_IDS
from bushexa.time_utils import get_now

# ── 노선 ────────────────────────────────────────────────────────────────
# 나란히 지나는 노선의 갈라짐이 같을 때 쓰는 기본 순서.
LINE_ORDER: list[str] = ["513", "753", "713", "743", "1115"]

# 앱 전역 배지 색(static/style.css .route-XXX, css/timetable.css .bus-XXX)과 동기화.
COLORS: dict[str, str] = {
    "513": "#D32F2F",
    "713": "#388E3C",
    "743": "#1976D2",
    "753": "#7B1FA2",
    "1115": "#F57C00",
}

# 노선별 종점(시간표 JSON 종점 키와 같은 이름) — 범례·목록용.
LINE_ENDS: dict[str, tuple[str, str]] = {
    "513": ("삼남", "덕하"),
    "713": ("UNIST", "명촌"),
    "743": ("UNIST", "명촌"),
    "753": ("UNIST", "명촌"),
    "1115": ("UNIST", "꽃바위"),
}


class Node(NamedTuple):
    x: float
    y: float
    label: str | None = None   # None 이면 경유점(정류장 아님, 표시 안 함)
    anchor: str = "n"          # 라벨 방향: n s e w ne nw se sw


# 격자 좌표: x 는 서→동, y 는 북→남. 실제 위치를 참고한 개략 배치.
NODES: dict[str, Node] = {
    # 서부(울주)
    "삼남": Node(0, 3, "삼남", "s"),
    "울산역": Node(2, 3, "울산역", "se"),
    "UNIST": Node(4, 1, "UNIST", "s"),
    "범서읍": Node(7, 1),                         # 입암·범서읍행정복지센터 — 천상/구영리 갈림
    "천상": Node(8, 2, "천상", "sw"),
    "구영리입구": Node(8, 1),                     # 천상1교사거리·구영리입구
    "구영": Node(9, 1, "구영", "n"),              # 선바위교–우미린2차–범서파출소 길
    "현대3차": Node(9, 2),                        # 현대2차–일신–현대3차–한신 길(513·743)
    "범서중": Node(10, 2, "범서중", "s"),         # 범서중학교앞
    "주공1단지": Node(11, 1),
    "천상남": Node(9, 3),                         # 743 구 경로(범서초 → 구영교, 10/2까지)
    "구영교": Node(11, 3),
    "굴화주공": Node(12, 4, "굴화주공", "w"),
    # 태화강 북쪽
    "태화루": Node(16, 4, "태화루", "n"),
    "성남동": Node(18, 4, "성남동", "n"),
    # 태화강 남쪽
    "삼호": Node(13, 5),
    "태화로터리": Node(17, 5),
    "시청": Node(17, 6, "시청", "w"),
    "신복교차로": Node(12, 5, "신복교차로", "w"),
    "울산대학교": Node(12, 6, "울산대학교", "w"),
    "문수경기장": Node(12, 7),
    "갈림옥동": Node(13, 8),
    "법원": Node(14, 8, "법원", "s"),
    "공업탑": Node(17, 8, "공업탑", "sw"),
    "산단캠갈림": Node(12, 10),
    "산단캠": Node(13, 11, "산단캠", "s"),
    "산단캠동": Node(16, 11),
    "삼일고": Node(17, 10),
    "덕하": Node(17, 13, "덕하", "w"),
    "강남초": Node(19, 7),
    "공업탑동": Node(18, 8),
    "시청동": Node(18, 6),
    "목화": Node(20, 6),
    "삼산": Node(21, 6, "삼산", "s"),
    "터미널": Node(22, 6),
    "이마트": Node(23, 6),
    "태화강역": Node(24, 6, "태화강역", "s"),
    "태화강역광장": Node(24, 5, "태화강역광장", "n"),
    "태화강역북": Node(25, 5),
    "명촌남": Node(26, 4),
    "명촌": Node(26, 3, "명촌", "n"),
    # 1115 동구 방면
    # 1115 10/3~: 태화강을 건너 명촌에서 꺾어 강을 따라(아산로) 남목으로
    "명촌교": Node(25, 4),
    "아산로": Node(28, 7),
    # 1115 10/2까지: 현대자동차 명촌정문·양정
    "명촌정문": Node(24, 1),
    "현대출고": Node(25.5, 1),
    "현대자동차": Node(28.5, 4, "현대자동차", "e"),
    "성원상떼빌": Node(28.5, 7),
    "염포산": Node(29, 7),
    "남목": Node(30, 6, "남목", "n"),
    "현대중공업·울산대학병원": Node(31, 7, "현대중공업·울산대학병원", "e"),
    "동울산": Node(31, 10),
    "일산해수욕장": Node(31, 11, "일산해수욕장", "e"),
    "꽃바위": Node(30, 12, "꽃바위", "s"),
}

_UNIST_EAST = ["UNIST", "범서읍"]
# 구영리 안 두 갈래(BIS 정류장 순서 기준)
#   구영 길: 구영리입구 → 선바위교 → 굿모닝힐 → 우미린1·2차 → 범서파출소 → 주공1단지 → 대리 (713·753·1115)
#   범서중 길: 구영리입구 → 현대2차 → 일신 → 현대3차 → 한신 → 우미린2차 → 범서중학교앞 → 대리 (513·743)
_GUYEONG = ["구영리입구", "구영", "주공1단지", "구영교"]
_BEOMSEO = ["구영리입구", "현대3차", "범서중", "구영교"]

# 최신(2026-10-03 시행) 경로. 시행 전 모습은 ROUTE_CHANGES 로 되돌린다.
LINE_PATHS: dict[str, list[str]] = {
    "513": ["삼남", "울산역", *_UNIST_EAST, *_BEOMSEO, "굴화주공",
            "삼호", "태화로터리", "시청", "공업탑", "삼일고", "덕하"],
    "713": [*_UNIST_EAST, "천상", *_GUYEONG, "굴화주공",
            "태화루", "성남동", "목화", "삼산", "터미널", "이마트", "태화강역", "태화강역북", "명촌남", "명촌"],
    "743": [*_UNIST_EAST, "천상", *_BEOMSEO, "굴화주공", "신복교차로", "울산대학교",
            "문수경기장", "갈림옥동", "법원", "공업탑", "공업탑동", "강남초", "목화",
            "삼산", "터미널", "이마트", "태화강역", "태화강역북", "명촌남", "명촌"],
    "753": [*_UNIST_EAST, *_GUYEONG, "굴화주공", "신복교차로", "울산대학교",
            "문수경기장", "산단캠갈림", "산단캠", "산단캠동", "삼일고", "공업탑", "공업탑동", "강남초",
            "목화", "삼산", "터미널", "이마트", "태화강역", "태화강역북", "명촌남", "명촌"],
    "1115": [*_UNIST_EAST, "천상", *_GUYEONG, "굴화주공", "태화루",
             "태화로터리", "시청", "시청동", "강남초", "목화", "삼산", "터미널", "이마트", "태화강역광장",
             "명촌교", "아산로", "성원상떼빌", "염포산", "남목",
             "현대중공업·울산대학병원", "동울산", "일산해수욕장", "꽃바위"],
}


class RouteChange(NamedTuple):
    line: str
    effective: date          # 이 날짜(KST)부터 new 구간
    old: list[str]           # 시행 전 구간
    new: list[str]           # 시행 후 구간(LINE_PATHS 에 들어 있는 것)
    summary: str


# 2026-10-03 시행 (울산버스 공지 2272, 2026-09-18 인가)
ROUTE_CHANGES_FROM = date(2026, 10, 3)
ROUTE_CHANGES: list[RouteChange] = [
    RouteChange(
        "743", ROUTE_CHANGES_FROM,
        old=["천상", "천상남", "구영교"],
        new=["천상", *_BEOMSEO],
        summary="구영리 안쪽(현대2차–우미린2차–범서중학교–대리) 경유",
    ),
    RouteChange(
        "1115", ROUTE_CHANGES_FROM,
        old=["태화강역광장", "명촌정문", "현대출고", "현대자동차", "성원상떼빌", "염포산"],
        new=["태화강역광장", "명촌교", "아산로", "성원상떼빌", "염포산"],
        summary="현대자동차(명촌정문–양정–성원상떼빌) 미정차. 태화강을 건너 명촌에서 꺾어 강을 따라(아산로) 남목으로",
    ),
]

LINE_STOPS: dict[str, list[str]] = {
    line: [n for n in path if NODES[n].label] for line, path in LINE_PATHS.items()
}


class Rail(NamedTuple):
    key: str
    name: str
    points: list[tuple[float, float]]      # 격자 좌표 폴리라인
    stations: list[str]                    # 이 철도와 환승되는 정류장 노드
    ends: tuple[str, str]                  # (첫 점 쪽 방면, 끝 점 쪽 방면)
    label_side: tuple[str, str] = ("e", "e")  # 방면 라벨을 선의 왼쪽(w)/오른쪽(e) 어디에 둘지


RAILS: list[Rail] = [
    Rail("ktx", "KTX 경부고속선", [(2, 0.1), (2, 6.2)], ["울산역"], ("서울", "부산"), ("w", "e")),
    Rail("donghae", "동해선", [(23, 0.1), (23, 5), (24, 6), (17, 13), (16.2, 13.8)],
         ["태화강역", "덕하"], ("포항", "부산"), ("e", "w")),
]

# 정류장 정보 패널에 붙는 설명.
STOP_NOTE: dict[str, str] = {
    "UNIST": "513은 울산역·삼남 방면으로, 나머지는 시내로 갑니다.",
    "울산역": "KTX 경부고속선 울산역과 환승.",
    "구영": "713·753·1115: 선바위교–우미린–범서파출소–대리 길.",
    "범서중": "513·743(10/3~): 현대2차–우미린2차–범서중학교–대리 길.",
    "태화강역": "동해선 태화강역과 환승. 1115는 이 정류소에 서지 않고 역 앞 태화강역광장에 섭니다.",
    "태화강역광장": "1115 전용. 713·743·753의 태화강역(1번 정류소)과 다른 정류장입니다.",
    "현대자동차": "1115는 10/2까지만 경유. 10/3부터 명촌에서 꺾어 태화강을 따라(아산로) 남목으로 갑니다.",
    "덕하": "동해선 덕하역과 가깝습니다.",
}

# 종점 pill 을 붙이는 방향(종점 노드 → 방향).
_PILL_SIDE: dict[str, str] = {
    "삼남": "w", "UNIST": "n", "덕하": "e", "명촌": "w", "꽃바위": "w",
}

LABEL_OVERRIDE: dict[str, list[str]] = {
    "현대중공업·울산대학병원": ["현대중공업", "울산대학병원"],
}

# 배경 물(개략, 격자 좌표): 태화강
_RIVER = [(4.4, 2.5), (6.3, 2.5), (7.5, 1.5), (8.4, 1.5), (9, 2.4), (9.6, 3.5),
          (12.7, 3.5), (13.5, 4.5), (17, 4.5), (19, 4.9), (23, 4.9), (24.6, 4.45),
          (25.8, 5.2), (26.6, 6.2), (27, 7.7)]
# 울산만 + 동해(동구 반도는 빈 곳으로 남긴다).
_BAY = [(26.6, 7.6), (27.2, 9), (27.8, 10.5), (28.3, 12.5), (28, 14.5), (35, 14.5),
        (35, 1.5), (33, 1.5), (32.6, 4.5), (32.2, 7.5), (32.5, 9.8), (32.1, 12.2),
        (30.8, 13.1), (29.6, 12.2), (29.6, 9.5), (29.2, 8.4), (28.5, 7.8), (27.4, 7.5)]

# ── 기하 상수 ────────────────────────────────────────────────────────────
_G = 58          # 격자 한 칸(px)
_PAD_X = 110     # 왼쪽 여백(서쪽 pill)
_PAD_Y = 70
_GAP = 6.5       # 나란히 지나는 노선 간격
_LINE_W = 5
_R = 7
_PILL_H = 26
_PILL_CHAR = 11
_PILL_PAD = 12
_LABEL_GAP = 7


def _xy(n: Node) -> tuple[float, float]:
    return _PAD_X + n.x * _G, _PAD_Y + n.y * _G


def _gxy(p: tuple[float, float]) -> tuple[float, float]:
    return _PAD_X + p[0] * _G, _PAD_Y + p[1] * _G


def _replace(path: list[str], new: list[str], old: list[str]) -> list[str]:
    for i in range(len(path) - len(new) + 1):
        if path[i:i + len(new)] == new:
            return path[:i] + old + path[i + len(new):]
    raise ValueError(f"경로에 변경 구간 {new} 이 없음")


def paths_for(today: date) -> dict[str, list[str]]:
    """``today``(KST) 기준으로 운행 중인 경로. 시행 전 변경은 옛 구간으로 되돌린다."""
    paths = dict(LINE_PATHS)
    for ch in ROUTE_CHANGES:
        if today < ch.effective:
            paths[ch.line] = _replace(paths[ch.line], ch.new, ch.old)
    return paths


def stops_for(today: date) -> dict[str, list[str]]:
    return {ln: [n for n in p if NODES[n].label] for ln, p in paths_for(today).items()}


def _edge_key(a: str, b: str) -> tuple[str, str]:
    """구간의 표준 방향: 서→동(같으면 북→남). 평행 오프셋의 법선 방향을 구간 전체에서 일정하게."""
    na, nb = NODES[a], NODES[b]
    return (a, b) if (na.x, na.y) <= (nb.x, nb.y) else (b, a)


def _normal(a: str, b: str) -> tuple[float, float]:
    ax, ay = _xy(NODES[a])
    bx, by = _xy(NODES[b])
    dx, dy = bx - ax, by - ay
    d = math.hypot(dx, dy) or 1.0
    return -dy / d, dx / d


def _side_score(path: list[str], a: str, b: str, n: tuple[float, float]) -> float:
    """구간 a→b 를 지나는 노선이 양 끝 너머에서 법선 n 쪽으로 얼마나 꺾여 나가는지.

    같은 구간을 나란히 지나는 노선을 이 값 순서로 쌓으면, 갈라질 때 서로 가로지르지 않는다.
    가까운 노드일수록 가중치가 크다(1, 1/2, 1/4). 교차는 정류장 캡슐 안에서만 허용한다:
    구간 끝이 정류장이면 그 너머는 보지 않고, 경유점 너머도 첫 정류장까지만 본다.
    """
    i = next(k for k in range(len(path) - 1) if {path[k], path[k + 1]} == {a, b})
    if path[i] == a:
        after, before = path[i + 2:i + 5], path[max(i - 3, 0):i][::-1]
    else:
        after, before = path[max(i - 3, 0):i][::-1], path[i + 2:i + 5]
    score = 0.0
    for end, seq in ((b, after), (a, before)):
        if NODES[end].label:
            continue
        cut = next((k for k, nm in enumerate(seq) if NODES[nm].label), len(seq) - 1)
        seq = seq[:cut + 1]
        ex, ey = _xy(NODES[end])
        for w, name in zip((1.0, 0.5, 0.25), seq):
            x, y = _xy(NODES[name])
            d = math.hypot(x - ex, y - ey) or 1.0
            score += w * (n[0] * (x - ex) + n[1] * (y - ey)) / d
    return score


def _route_points(
    paths: dict[str, list[str]],
) -> tuple[dict[str, list[tuple[float, float]]], list[tuple[str, str, float, float]]]:
    """노선별 꼭짓점(평행 오프셋 적용)과 노선별 정류장 표시 위치(line, 정류장, x, y)를 돌려준다.

    꺾이는 노드에서는 두 오프셋 선의 교점(마이터)을 쓰고, 나란한 구간에서 오프셋이 바뀌면
    노드 앞뒤로 짧게 비스듬히 옮겨 탄다.
    """
    edge_lines: dict[tuple[str, str], list[str]] = {}
    for line in LINE_ORDER:
        p = paths[line]
        for a, b in zip(p, p[1:]):
            edge_lines.setdefault(_edge_key(a, b), []).append(line)
    for key, users in edge_lines.items():
        n = _normal(*key)
        users.sort(key=lambda ln: (round(_side_score(paths[ln], *key, n), 3),
                                   LINE_ORDER.index(ln)))

    def offset(line: str, a: str, b: str) -> tuple[float, float]:
        key = _edge_key(a, b)
        users = edge_lines[key]
        k = users.index(line) - (len(users) - 1) / 2
        nx, ny = _normal(*key)
        return nx * k * _GAP, ny * k * _GAP

    def unit(a: str, b: str) -> tuple[float, float]:
        (ax, ay), (bx, by) = _xy(NODES[a]), _xy(NODES[b])
        d = math.hypot(bx - ax, by - ay) or 1.0
        return (bx - ax) / d, (by - ay) / d

    out: dict[str, list[tuple[float, float]]] = {}
    stops: list[tuple[str, str, float, float]] = []
    for line in LINE_ORDER:
        p = paths[line]
        pts: list[tuple[float, float]] = []
        for i, name in enumerate(p):
            n_before = len(pts)
            x, y = _xy(NODES[name])
            if i == 0 or i == len(p) - 1:
                o = offset(line, p[0], p[1]) if i == 0 else offset(line, p[-2], p[-1])
                pts.append((x + o[0], y + o[1]))
            else:
                o1, o2 = offset(line, p[i - 1], name), offset(line, name, p[i + 1])
                d1, d2 = unit(p[i - 1], name), unit(name, p[i + 1])
                cross = d1[0] * d2[1] - d1[1] * d2[0]
                if abs(cross) > 0.2:
                    # 두 오프셋 선의 교점(마이터)
                    p1 = (x + o1[0], y + o1[1])
                    p2 = (x + o2[0], y + o2[1])
                    t = ((p2[0] - p1[0]) * d2[1] - (p2[1] - p1[1]) * d2[0]) / cross
                    pts.append((p1[0] + d1[0] * t, p1[1] + d1[1] * t))
                elif math.hypot(o1[0] - o2[0], o1[1] - o2[1]) < 0.5:
                    pts.append((x + o1[0], y + o1[1]))
                else:
                    # 나란한 구간인데 오프셋이 바뀜 → 노드 앞뒤로 짧게 비스듬히 옮겨 탄다
                    j = _GAP * 1.5
                    pts.append((x + o1[0] - d1[0] * j, y + o1[1] - d1[1] * j))
                    pts.append((x + o2[0] + d2[0] * j, y + o2[1] + d2[1] * j))
            if NODES[name].label:
                new = pts[n_before:]
                stops.append((line, name, sum(q[0] for q in new) / len(new),
                              sum(q[1] for q in new) / len(new)))
        out[line] = pts
    return out, stops


def stop_link(name: str) -> tuple[str, str] | None:
    """정류장 → (실시간 도착 URL, 정류소 표시명). 조회 가능한 정류소가 없으면 None."""
    sid = ROUTE_MAP_STOP_LINK.get(name)
    if not sid:
        return None
    return f"/stops?stop_id={sid}", STOP_IDS.get(sid, name)


def render_route_diagram(today: date | None = None) -> Markup:
    """노선도 전체를 인라인 SVG(Markup)로 렌더한다.

    ``today``(KST)가 ``ROUTE_CHANGES`` 시행일 이전이면 그 노선은 옛 경로로 그린다.
    """
    today = today or get_now().date()
    return _render(paths_for(today))


def _render(paths: dict[str, list[str]]) -> Markup:
    pts, stop_list = _route_points(paths)

    stop_pts: dict[str, list[tuple[str, float, float]]] = {}
    for line, name, x, y in stop_list:
        stop_pts.setdefault(name, []).append((line, x, y))
    rail_stations = {s: r for r in RAILS for s in r.stations}

    max_x = max(_xy(n)[0] for n in NODES.values()) + 200
    max_y = max(max(_xy(n)[1] for n in NODES.values()) + 60,
                max(_gxy(p)[1] for r in RAILS for p in r.points) + 24)
    parts: list[str] = [
        f'<svg class="route-svg" viewBox="0 0 {max_x:.0f} {max_y:.0f}" role="group" '
        f'aria-label="버스 노선도 (실제 위치를 참고한 개략도)" xmlns="http://www.w3.org/2000/svg">'
    ]

    # 1) 배경: 바다·울산만, 태화강
    def gpt(p: tuple[float, float]) -> str:
        x, y = _gxy(p)
        return f"{x:.1f} {y:.1f}"

    parts.append('<path class="route-water" d="M ' + " L ".join(gpt(p) for p in _BAY) + ' Z" />')
    parts.append('<path class="route-river" d="M ' + " L ".join(gpt(p) for p in _RIVER) + '" />')
    for text, (gx, gy), anchor in (("태화강", (14.3, 4.59), "start"), ("동해", (33.2, 5), "start"),
                                   ("울산만", (28.5, 11.5), "middle")):
        x, y = _gxy((gx, gy))
        parts.append(f'<text class="route-water-label" x="{x:.0f}" y="{y:.0f}" '
                     f'text-anchor="{anchor}">{text}</text>')

    # 2) 철도(배경): 검은 선 + 흰 점선
    for rail in RAILS:
        d = "M " + " L ".join(gpt(p) for p in rail.points)
        parts.append(f'<g class="route-rail" data-rail="{rail.key}">'
                     f'<path class="route-rail-base" d="{d}" />'
                     f'<path class="route-rail-dash" d="{d}" /></g>')
        for p, dest, side, is_start in (
            (rail.points[0], rail.ends[0], rail.label_side[0], True),
            (rail.points[-1], rail.ends[1], rail.label_side[1], False),
        ):
            x, y = _gxy(p)
            text = f"{rail.name} · {dest} 방면" if is_start else f"{rail.name} · {dest} 방면"
            dy = 16 if is_start else 0
            dx, anchor = (9, "start") if side == "e" else (-9, "end")
            parts.append(f'<text class="route-rail-label" x="{x + dx:.0f}" y="{y + dy:.0f}" '
                         f'text-anchor="{anchor}">{escape(text)}</text>')

    # 3) 노선
    for line in LINE_ORDER:
        d = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in pts[line])
        parts.append(
            f'<path class="route-line" data-line="{line}" d="{d}" fill="none" '
            f'stroke="{COLORS[line]}" stroke-width="{_LINE_W}" '
            f'stroke-linecap="round" stroke-linejoin="round" />'
        )

    # 4) 정류장(클릭 가능한 그룹): 공유 = 흰 캡슐, 단독 = 노선 색 원, 철도 환승 = 검은 테두리
    for name, lst in stop_pts.items():
        lines = [p[0] for p in lst]
        link = stop_link(name)
        rail = rail_stations.get(name)
        note = STOP_NOTE.get(name, "")
        attrs = [
            f'data-stop="{escape(name)}"',
            f'data-label="{escape(NODES[name].label or name)}"',
            f'data-lines="{" ".join(lines)}"',
        ]
        if link:
            attrs += [f'data-href="{escape(link[0])}"', f'data-href-label="{escape(link[1])}"']
        if rail:
            attrs.append(f'data-rail="{escape(rail.name)}"')
        if note:
            attrs.append(f'data-note="{escape(note)}"')
        aria = f"{NODES[name].label} 정류장 — {', '.join(lines)}번"
        parts.append(f'<g class="route-station" tabindex="0" role="button" '
                     f'aria-label="{escape(aria)}" {" ".join(attrs)}>')
        if len(lst) >= 2:
            a, b = max(
                ((p, q) for p in lst for q in lst),
                key=lambda pq: math.hypot(pq[0][1] - pq[1][1], pq[0][2] - pq[1][2]),
            )
            seg = f'x1="{a[1]:.1f}" y1="{a[2]:.1f}" x2="{b[1]:.1f}" y2="{b[2]:.1f}"'
            if rail:
                parts.append(f'<line class="route-rail-ring" {seg} stroke-width="{2 * _R + 12}" '
                             f'stroke-linecap="round" />')
            parts.append(f'<line class="route-box" {seg} stroke-width="{2 * _R + 4}" '
                         f'stroke-linecap="round" />'
                         f'<line class="route-box-fill" {seg} stroke-width="{2 * _R}" '
                         f'stroke-linecap="round" />')
        else:
            line, x, y = lst[0]
            if rail:
                parts.append(f'<circle class="route-rail-ring-c" cx="{x:.1f}" cy="{y:.1f}" '
                             f'r="{_R + 6}" />')
            parts.append(f'<circle class="route-stop" cx="{x:.1f}" cy="{y:.1f}" r="{_R}" '
                         f'stroke="{COLORS[line]}" />')
        parts.append("</g>")

    # 5) 라벨
    for name, lst in stop_pts.items():
        node = NODES[name]
        xs = [p[1] for p in lst]
        ys = [p[2] for p in lst]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        reach = _R + 2 + _LABEL_GAP + (6 if name in rail_stations else 0)
        a = node.anchor
        dx = (max(xs) - cx + reach) * (1 if "e" in a else -1 if "w" in a else 0)
        dy = (max(ys) - cy + reach) * (1 if "s" in a else -1 if "n" in a else 0)
        tx, ty = cx + dx, cy + dy
        anchor = "start" if "e" in a else "end" if "w" in a else "middle"
        lines_txt = LABEL_OVERRIDE.get(name, [node.label or name])
        line_h = 22
        if "n" in a:
            ty -= (len(lines_txt) - 1) * line_h
        elif "s" in a:
            ty += 16
        else:
            ty += 7 - (len(lines_txt) - 1) * line_h / 2
        tspans = "".join(
            f'<tspan x="{tx:.1f}" dy="{0 if i == 0 else line_h}">{escape(t)}</tspan>'
            for i, t in enumerate(lines_txt)
        )
        parts.append(
            f'<text class="route-label" data-stop="{escape(name)}" x="{tx:.1f}" y="{ty:.1f}" '
            f'text-anchor="{anchor}">{tspans}</text>'
        )

    # 6) 종점 번호 pill (누르면 그 노선 강조)
    termini: dict[str, list[str]] = {}
    for line in LINE_ORDER:
        for end in (paths[line][0], paths[line][-1]):
            termini.setdefault(end, []).append(line)
    for end, lines in termini.items():
        side = _PILL_SIDE.get(end, "e")
        lst = stop_pts[end]
        xs = [p[1] for p in lst]
        ys = [p[2] for p in lst]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        widths = [len(line) * _PILL_CHAR + _PILL_PAD for line in lines]
        if side in ("w", "e"):
            total = len(lines) * _PILL_H + (len(lines) - 1) * 4
            y0 = cy - total / 2
            for line, w in zip(lines, widths):
                x0 = (min(xs) - _R - 10 - w) if side == "w" else (max(xs) + _R + 10)
                parts.append(_pill(line, x0, y0, w))
                y0 += _PILL_H + 4
        else:
            total = sum(widths) + (len(lines) - 1) * 4
            x0 = cx - total / 2
            y0 = (min(ys) - _R - 8 - _PILL_H) if side == "n" else (max(ys) + _R + 8)
            for line, w in zip(lines, widths):
                parts.append(_pill(line, x0, y0, w))
                x0 += w + 4

    parts.append(
        f'<text class="route-credit" x="{max_x - 12:.0f}" y="{max_y - 12:.0f}" '
        f'text-anchor="end">실제 위치를 참고한 개략도 · 거리는 정확하지 않음</text>'
    )
    parts.append("</svg>")
    return Markup("".join(parts))


def _pill(line: str, x0: float, y0: float, w: float) -> str:
    return (
        f'<g class="route-pill-btn" data-line="{line}" tabindex="0" role="button" '
        f'aria-label="{line}번 노선만 보기">'
        f'<rect class="route-pill" x="{x0:.1f}" y="{y0:.1f}" width="{w:.1f}" '
        f'height="{_PILL_H}" rx="5" fill="{COLORS[line]}" />'
        f'<text class="route-pill-text" x="{x0 + w / 2:.1f}" y="{y0 + _PILL_H / 2:.1f}" '
        f'text-anchor="middle" dominant-baseline="central">{escape(line)}</text></g>'
    )
