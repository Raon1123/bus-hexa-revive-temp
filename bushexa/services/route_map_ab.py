"""/info 노선도 A/B 테스트 카운터 — A(개략 지도) vs B(노선별 정류장 목록).

첫 방문에 A·B 중 하나를 무작위로 보여 주고(쿠키로 유지), 날짜별로 센다.
  - 노출: 보여 줄 때마다 view_a / view_b
  - 전환: 사용자가 다른 쪽으로 넘어갈 때 switch_to_a / switch_to_b
  - 참고: 지도 조작(map_*)·목록 링크(list_link) 사용 횟수
개인 식별 정보는 저장하지 않는다(이벤트 이름과 횟수만).

파일: ``<data_dir>/route_map_ab.json`` = ``{"YYYY-MM-DD": {"event": count, ...}, ...}``.
여러 gunicorn 워커가 동시에 쓰므로 ``fileio.locked_update_json`` 으로만 갱신한다.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path

from bushexa.fileio import locked_update_json, read_json

log = logging.getLogger("bushexa.services.route_map_ab")

# 이벤트 → (방식, 설명). 이 목록 밖의 이벤트는 받지 않는다.
EVENTS: dict[str, tuple[str, str]] = {
    "view_a": ("A 지도", "노출"),
    "view_b": ("B 목록", "노출"),
    "switch_to_b": ("A 지도", "B 목록으로 전환"),
    "switch_to_a": ("B 목록", "A 지도로 전환"),
    "map_line": ("A 지도", "노선 선택(번호 칩·pill·선)"),
    "map_stop": ("A 지도", "정류장 선택"),
    "map_link": ("A 지도", "지도 패널에서 링크 이동"),
    "list_link": ("B 목록", "목록에서 링크 이동"),
}

VARIANTS = ("a", "b")
# 브라우저(sendBeacon)가 보낼 수 있는 이벤트. 노출(view_*)은 서버만 센다.
CLIENT_EVENTS = frozenset(EVENTS) - {"view_a", "view_b"}

KEEP_DAYS = 400


def default_path(data_dir) -> Path:
    return Path(data_dir) / "route_map_ab.json"


def record(path: Path, event: str, today: date) -> None:
    """이벤트 1회를 센다. 알 수 없는 이벤트는 ValueError."""
    if event not in EVENTS:
        raise ValueError(f"unknown event: {event}")
    day = today.isoformat()
    cutoff = (today - timedelta(days=KEEP_DAYS)).isoformat()

    def _mutate(data: dict) -> dict:
        if not isinstance(data, dict):
            data = {}
        bucket = data.setdefault(day, {})
        bucket[event] = int(bucket.get(event, 0)) + 1
        for old in [d for d in data if d < cutoff]:
            del data[old]
        return data

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    locked_update_json(path, _mutate, default={}, logger=log)


def summary(path: Path, today: date, days: int = 7) -> dict:
    """관리자 화면용 요약: 이벤트별 (최근 days일, 전체) 합계, 방식별 노출·전환·전환율."""
    data = read_json(path, {}, expect=dict)
    since = (today - timedelta(days=days - 1)).isoformat()
    rows = []
    for ev, (variant, desc) in EVENTS.items():
        total = sum(int(v.get(ev, 0)) for v in data.values() if isinstance(v, dict))
        recent = sum(int(v.get(ev, 0)) for d, v in data.items()
                     if d >= since and isinstance(v, dict))
        rows.append({"event": ev, "variant": variant, "desc": desc,
                     "recent": recent, "total": total})
    daily = [
        {"day": d, **{ev: int(data[d].get(ev, 0)) for ev in EVENTS}}
        for d in sorted(data, reverse=True)[:days] if isinstance(data[d], dict)
    ]
    by = {r["event"]: r for r in rows}

    def arm(view: str, switch_away: str, name: str) -> dict:
        out = {"name": name}
        for span in ("recent", "total"):
            shown, left = by[view][span], by[switch_away][span]
            out[span] = {"views": shown, "switches": left,
                         "rate": (left / shown) if shown else None}
        return out

    return {
        "days": days,
        "rows": rows,
        "daily": daily,
        "arms": [arm("view_a", "switch_to_b", "A 지도"), arm("view_b", "switch_to_a", "B 목록")],
    }
