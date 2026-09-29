"""동해선 광역전철 — 출발역 시간표와 도착역 시간표를 시각만으로 잇는다(순수 함수).

TAGO 지하철 역별 시간표에는 열차번호가 없다. 대신 다음 두 성질로 편을 잇는다.

1. **소요시간 최빈값**: 출발×도착 시각 차이 중 가장 흔한 값(30초 단위)이 정상 소요시간이다
   (2026-09-29 실측: 태화강→벡스코 55.5분, 태화강→부전 76분 — 평일·휴일 42편 중 약 30편이 정확히 일치).
2. **추월 없음**: 같은 방향 전철은 순서가 바뀌지 않는다. 출발순으로 보며 각 편에
   "최빈 소요시간 - 1분" 이후 아직 배정되지 않은 가장 이른 도착을 준다. 대피·정차 지연으로
   4~13분 늦는 편이 있어 ``max_wait`` 까지 기다린다.

도착역에는 중간역(일광 등)에서 출발한 편도 섞여 있어 도착이 출발보다 많다(평일 50 vs 42).
이 편들은 배정되지 않고 남는다 — 태화강 출발 편의 도착으로 잘못 쓰지 않는다.

시각은 ``"HH:MM:SS"``. 03시 이전은 전날 운행일의 심야(24시 이후)로 본다.
"""
from __future__ import annotations

from collections import Counter

# 이 시각 이전은 전날 운행일의 심야편으로 본다(00:16 도착 = 24:16).
_SERVICE_DAY_START_H = 3


def service_minutes(hhmmss: str) -> float:
    """``HH:MM:SS`` → 운행일 기준 분(03시 이전은 +24h)."""
    h, m, s = (int(x) for x in hhmmss.split(":"))
    minutes = h * 60 + m + s / 60
    return minutes + 24 * 60 if h < _SERVICE_DAY_START_H else minutes


def infer_run_minutes(departures: list[str], arrivals: list[str], *,
                      lo: float = 10, hi: float = 180) -> float | None:
    """출발·도착 시각 차이의 최빈값(30초 단위). 후보가 없으면 None."""
    deps = [service_minutes(t) for t in departures]
    arrs = [service_minutes(t) for t in arrivals]
    diffs = Counter(round((a - d) * 2) / 2 for d in deps for a in arrs if lo <= a - d <= hi)
    if not diffs:
        return None
    best = max(diffs.values())
    return min(v for v, n in diffs.items() if n == best)   # 동률이면 짧은 쪽


def match_by_time(departures: list[str], arrivals: list[str], *,
                  run_minutes: float | None = None, early: float = 1,
                  max_wait: float = 15) -> list[tuple[str, str | None]]:
    """출발 시각마다 도착 시각을 짝지어 ``[(출발, 도착|None)]`` 을 출발순으로 돌려준다.

    ``run_minutes`` 를 주지 않으면 :func:`infer_run_minutes` 로 추정한다. 창
    ``[출발 + run - early, 출발 + run + max_wait]`` 안에 남은 도착이 없으면 None.
    """
    deps = sorted(departures, key=service_minutes)
    if run_minutes is None:
        run_minutes = infer_run_minutes(deps, arrivals)
    if run_minutes is None:
        return [(d, None) for d in deps]
    arrs = sorted(arrivals, key=service_minutes)
    arr_min = [service_minutes(a) for a in arrs]
    out: list[tuple[str, str | None]] = []
    j = 0
    for d in deps:
        start = service_minutes(d) + run_minutes
        while j < len(arrs) and arr_min[j] < start - early:
            j += 1
        if j < len(arrs) and arr_min[j] <= start + max_wait:
            out.append((d, arrs[j]))
            j += 1
        else:
            out.append((d, None))
    return out
