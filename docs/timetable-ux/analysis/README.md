# 경유 시각 예측 분석 스크립트

`03-addendum-notices-via-prediction.md` §2.3의 수치를 만든 스크립트입니다(2026-09-29).

- 입력: `logs/logs.tsv` (gitignore, 2026-04-16~06-01 봄학기 recorder 기록). `analyze.py`가 이를 운행 단위로 묶어 `runs_logs.csv`를 만들고, 나머지 스크립트는 그 CSV를 읽습니다.
- `owner_gate_sim*.py`: 오너 게이트(최근 30일·같은 요일군·같은 편 4건) × 편(slot)+오프셋 모델. `_pooled`는 토+일·공휴일 통합.
- `owner_gate_cluster*.py`: 오너 게이트 × UNIST 통과시각 군집 모델.
- 나머지(`analyze*.py`, `cluster.py`, `origin_match.py`, `gate_sim.py`)는 조사 단계 스크립트입니다. 경로·입력 파일명은 작성 당시 환경 기준이라 실행 전에 확인하세요.
- 저장소 코드가 아니라 일회성 분석입니다. 테스트 대상이 아닙니다.
