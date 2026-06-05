"""노선도(graph-not-map) — 데이터 기반 인라인 SVG 빌더.

PNG(static/media/graphisnotmap.png)를 손그림으로 박아두던 것을 데이터 모델로
대체한다. 노선을 추가/수정하려면 아래 ``LINE_STOPS`` / ``COLS`` / ``COLORS``
데이터만 바꾸면 된다(하드코딩 SVG 없음).

표현 규칙("graph, not map"):
  - 정류장 = 원, 노선 = 색선(가로 트랙=lane), 둘 이상이 정차하는 정류장 = 원들을
    감싸는 둥근 박스.
  - 각 노선은 자기 lane(고정 y)에서 좌→우로 흐르고, 정류장은 (컬럼 x, 그 노선의
    lane y)에 원으로 놓인다. 컬럼 순서는 모든 노선에서 경로 순서가 단조증가하도록
    배치돼 있어 선 꺾임이 필요 없다.

색상은 PNG 범례의 743/753 오기(법원 경유선=743=자홍, 산단캠 경유선=753=초록)를
실제 경로 기준으로 바로잡아 고정한다.
"""

from __future__ import annotations

from markupsafe import Markup, escape

# ── 노선 (위→아래 lane 순서 = 리스트 인덱스) ─────────────────────────────
LINE_ORDER: list[str] = ["713", "513", "1115", "743", "753"]

# 앱 전역 배지 색(static/style.css의 .route-XXX)과 일치시켜 출발보드 등 다른
# 화면과 색 일관성을 유지한다. (PNG 범례 색과는 다름 — 일관성 우선.)
COLORS: dict[str, str] = {
    "513": "#D32F2F",   # 빨강
    "713": "#388E3C",   # 초록
    "743": "#1976D2",   # 파랑
    "753": "#7B1FA2",   # 보라
    "1115": "#F57C00",  # 주황
}

# 각 노선이 정차하는 핵심 정류장(경로 순서). 굴화주공·공업탑·명촌 등은 생략.
LINE_STOPS: dict[str, list[str]] = {
    "713": ["UNIST", "천상", "구영", "태화루", "삼산", "태화강역", "명촌"],
    "513": ["삼남", "울산역", "UNIST", "구영", "시청", "덕하"],
    "1115": [
        "UNIST", "천상", "구영", "태화루", "시청", "삼산", "태화강역",
        "염포동", "남목", "현대중공업·울산대학병원", "일산해수욕장", "꽃바위",
    ],
    "743": ["UNIST", "천상", "신복교차로", "울산대학교", "법원", "삼산", "태화강역", "명촌"],
    "753": ["UNIST", "구영", "신복교차로", "울산대학교", "산단캠", "삼산", "태화강역", "명촌"],
}

# 정류장 → 컬럼 인덱스(x). 모든 노선의 경로에서 좌→우 단조증가하도록 배치.
COLS: dict[str, int] = {
    "삼남": 0,
    "울산역": 1,
    "UNIST": 2,
    "천상": 3,
    "구영": 4,
    "태화루": 5,
    "신복교차로": 5,
    "시청": 6,
    "울산대학교": 6,
    "법원": 7,
    "산단캠": 7,
    "삼산": 8,
    "태화강역": 9,
    "명촌": 10,
    "덕하": 11,
    "염포동": 12,
    "남목": 13,
    "현대중공업·울산대학병원": 14,
    "일산해수욕장": 15,
    "꽃바위": 16,
}

# 긴 라벨은 두 줄로 표시(없으면 정류장명 그대로).
LABEL_OVERRIDE: dict[str, list[str]] = {
    "현대중공업·울산대학병원": ["현대중공업", "울산대학병원"],
}

# ── 기하 상수 ────────────────────────────────────────────────────────────
_X0 = 150       # col0 x (왼쪽 범례 공간 확보)
_COL_W = 116
_Y0 = 165       # lane0 y (위쪽 라벨 공간)
_LANE_H = 64
_R = 16         # 원 반지름 (경유지 색을 키움)
_BOX_PAD = 11   # 공유박스 안쪽 여백
_BADGE_H = 28   # 종점 번호 배지 높이
_CHAR_W = 12    # 배지 글자폭(폭 계산용)
_BADGE_PAD = 16 # 배지 좌우 여백
_STUB = 24      # 종점 원 ~ 배지 사이 연장선 길이
_MARGIN = 24    # viewBox 바깥 여백

_LANES: dict[str, int] = {line: i for i, line in enumerate(LINE_ORDER)}


def _x(col: int) -> int:
    return _X0 + col * _COL_W


def _y(lane: int) -> int:
    return _Y0 + lane * _LANE_H


def _stations_lanes() -> dict[str, list[int]]:
    """정류장명 → 그 정류장에 정차하는 노선들의 lane 목록(정렬)."""
    out: dict[str, list[int]] = {}
    for line in LINE_ORDER:
        lane = _LANES[line]
        for stop in LINE_STOPS[line]:
            out.setdefault(stop, []).append(lane)
    for stop in out:
        out[stop].sort()
    return out


def render_route_diagram() -> Markup:
    """노선도 전체를 인라인 SVG 문자열(Markup)로 렌더한다."""
    stations = _stations_lanes()

    n_lanes = len(LINE_ORDER)

    # 종점 배지(지하철 노선도식): 각 노선의 양 끝(서쪽=첫 정류장, 동쪽=마지막
    # 정류장)에 번호 배지를 둔다. 좌측 범례를 대체한다.
    # 배지는 양쪽 공통 가장자리(west_inner / east_inner)에 정렬하고, 종점 원에서
    # 그 가장자리까지 같은 색 선으로 잇는다.
    first_cols = [COLS[LINE_STOPS[line][0]] for line in LINE_ORDER]
    last_cols = [COLS[LINE_STOPS[line][-1]] for line in LINE_ORDER]
    west_inner = _x(min(first_cols)) - _R - _STUB   # 모든 서쪽 배지의 안쪽 끝
    east_inner = _x(max(last_cols)) + _R + _STUB    # 모든 동쪽 배지의 안쪽 끝

    # (cx_circle, cy, dir, text, color, badge_w, inner_x) — dir: -1 서쪽 / +1 동쪽
    badges: list[tuple[float, float, int, str, str, float, float]] = []
    for line in LINE_ORDER:
        stops = LINE_STOPS[line]
        cy = _y(_LANES[line])
        bw = len(line) * _CHAR_W + _BADGE_PAD
        badges.append((_x(COLS[stops[0]]), cy, -1, line, COLORS[line], bw, west_inner))
        badges.append((_x(COLS[stops[-1]]), cy, +1, line, COLORS[line], bw, east_inner))

    def _badge_cx(inner: float, d: int, bw: float) -> float:
        return inner + d * (bw / 2)

    # viewBox 범위를 배지 실제 끝까지 계산(우측 1115·좌측 삼남 배지가 잘리지 않게)
    _edges = [
        (_badge_cx(inner, d, bw) - bw / 2, _badge_cx(inner, d, bw) + bw / 2)
        for _, _, d, _, _, bw, inner in badges
    ]
    min_x = min(lo for lo, _ in _edges)
    max_x = max(hi for _, hi in _edges)
    vb_x = min_x - _MARGIN
    width = (max_x + _MARGIN) - vb_x
    height = _y(n_lanes - 1) + 150  # 아래쪽 라벨 공간

    parts: list[str] = [
        f'<svg class="route-svg" viewBox="{vb_x:.0f} 0 {width:.0f} {height}" '
        f'role="img" aria-label="버스 노선도" '
        f'xmlns="http://www.w3.org/2000/svg">'
    ]

    # 1) 공유 정류장 박스 (원/선보다 먼저 그려 뒤에 깔리게)
    for stop, lanes in stations.items():
        if len(lanes) < 2:
            continue
        x = _x(COLS[stop])
        top = _y(lanes[0])
        bot = _y(lanes[-1])
        bx = x - _R - _BOX_PAD
        by = top - _R - _BOX_PAD
        bw = 2 * (_R + _BOX_PAD)
        bh = (bot - top) + 2 * (_R + _BOX_PAD)
        parts.append(
            f'<rect class="route-box" x="{bx}" y="{by}" width="{bw}" '
            f'height="{bh}" rx="{_R + _BOX_PAD}" />'
        )

    # 2) 노선 선 (각 노선은 자기 lane에서 좌→우 직선)
    for line in LINE_ORDER:
        stops = LINE_STOPS[line]
        y = _y(_LANES[line])
        pts = [(_x(COLS[s]), y) for s in stops]
        d = "M " + " L ".join(f"{px} {py}" for px, py in pts)
        parts.append(
            f'<path class="route-line" d="{d}" fill="none" '
            f'stroke="{COLORS[line]}" stroke-width="5" '
            f'stroke-linecap="round" stroke-linejoin="round" />'
        )

    # 3) 정류장 원 (노선별 lane 위)
    for line in LINE_ORDER:
        y = _y(_LANES[line])
        for stop in LINE_STOPS[line]:
            x = _x(COLS[stop])
            parts.append(
                f'<circle class="route-stop" cx="{x}" cy="{y}" r="{_R}" '
                f'stroke="{COLORS[line]}" />'
            )

    # 4) 정류장 라벨 (위쪽 lane → 위에, 아래쪽 → 아래에, 기울임)
    for stop, lanes in stations.items():
        x = _x(COLS[stop])
        above = lanes[0] <= 1
        if above:
            ly = _y(lanes[0]) - _R - 8
            anchor = "start"
        else:
            ly = _y(lanes[-1]) + _R + 8
            anchor = "end"
        lines_txt = LABEL_OVERRIDE.get(stop, [stop])
        tspans = ""
        for i, t in enumerate(lines_txt):
            dy = "0" if i == 0 else "1.1em"
            tspans += f'<tspan x="{x}" dy="{dy}">{escape(t)}</tspan>'
        parts.append(
            f'<text class="route-label" x="{x}" y="{ly}" '
            f'text-anchor="{anchor}" transform="rotate(-30 {x} {ly})">'
            f'{tspans}</text>'
        )

    # 5) 종점 번호 배지 (선을 양쪽 공통 가장자리까지 연장 + 색상 번호 pill)
    for cx_circle, cy, d, text, color, bw, inner in badges:
        bcx = _badge_cx(inner, d, bw)
        parts.append(
            f'<line class="route-line" x1="{cx_circle + d * _R}" y1="{cy}" '
            f'x2="{inner}" y2="{cy}" stroke="{color}" stroke-width="5" '
            f'stroke-linecap="round" />'
        )
        parts.append(
            f'<rect class="route-pill" x="{bcx - bw / 2:.1f}" '
            f'y="{cy - _BADGE_H / 2}" width="{bw}" height="{_BADGE_H}" '
            f'rx="6" fill="{color}" />'
        )
        parts.append(
            f'<text class="route-pill-text" x="{bcx:.1f}" y="{cy}" '
            f'text-anchor="middle" dominant-baseline="central">'
            f'{escape(text)}</text>'
        )

    parts.append("</svg>")
    return Markup("".join(parts))
