"""노선별 세로 정류장 목록(/info 노선도 아래) 뷰 모델.

정류장 순서는 ``route_diagram`` 의 경로 데이터를 그대로 쓴다(노선 사실의 출처를 하나로 유지).
시행일 전에는 새로 서는 정류장을 "10/3부터", 곧 빠지는 정류장을 "10/2까지" 로 함께 보여 준다.

  - UNIST            → 그 노선 UNIST 출발 시간표(/busno?bus=…)
  - 도착 조회 가능 정류장 → 정류소별 실시간 도착(/stops?stop_id=…)
  - 그 외             → 링크 없음
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from bushexa.time_utils import get_now
from bushexa.web.route_diagram import (
    COLORS,
    LINE_ENDS,
    LINE_ORDER,
    NODES,
    ROUTE_CHANGES,
    stop_link,
    stops_for,
)

# 목록 표시명(없으면 노드 라벨 그대로).
STOP_LABEL: dict[str, str] = {
    "구영": "구영리 (선바위·우미린)",
    "범서중": "구영리 (범서중학교)",
    "태화루": "태화루 (국가정원)",
    "산단캠": "산학융합지구캠퍼스",
    "울산역": "울산역 (KTX)",
    "태화강역": "태화강역 (동해선)",
    "태화강역광장": "태화강역광장 (역 앞)",
}


@dataclass(frozen=True)
class StopView:
    key: str
    label: str
    href: str | None
    is_unist: bool
    is_branch: bool   # 구영리 안에서 노선마다 갈리는 정류장
    note: str | None  # "10/3부터" / "10/2까지"


@dataclass(frozen=True)
class LineView:
    line: str
    color: str
    ends: tuple[str, str]
    stops: list[StopView]


def _merge(now: list[str], new: list[str]) -> list[tuple[str, str | None]]:
    """운행 중 목록과 시행 후 목록을 순서대로 합친다. (정류장, 'add'|'drop'|None)."""
    out: list[tuple[str, str | None]] = []
    i = j = 0
    while i < len(now) or j < len(new):
        if i < len(now) and j < len(new) and now[i] == new[j]:
            out.append((now[i], None))
            i += 1
            j += 1
        elif j < len(new) and new[j] not in now[i:]:
            out.append((new[j], "add"))
            j += 1
        else:
            out.append((now[i], "drop"))
            i += 1
    return out


def build_route_lines(today: date | None = None) -> list[LineView]:
    """노선별 정류장 목록. 시행 전 변경은 예고(10/3부터 / 10/2까지)로 함께 표시한다."""
    today = today or get_now().date()
    now = stops_for(today)
    upcoming = [c for c in ROUTE_CHANGES if today < c.effective]
    after = stops_for(max((c.effective for c in upcoming), default=today))
    out: list[LineView] = []
    for line in sorted(LINE_ORDER, key=int):
        stops = []
        for key, change in _merge(now[line], after[line]):
            note = None
            if change is not None:
                eff = next(c.effective for c in upcoming if c.line == line)
                note = (f"{eff.month}/{eff.day}부터" if change == "add"
                        else f"{(eff - timedelta(days=1)).month}/{(eff - timedelta(days=1)).day}까지")
            link = stop_link(key)
            href = f"/busno?bus={line}" if key == "UNIST" else (link[0] if link else None)
            stops.append(StopView(
                key=key,
                label=STOP_LABEL.get(key, NODES[key].label or key),
                href=href,
                is_unist=(key == "UNIST"),
                is_branch=(key in ("범서중", "구영")),
                note=note,
            ))
        out.append(LineView(line=line, color=COLORS[line], ends=LINE_ENDS[line], stops=stops))
    return out
