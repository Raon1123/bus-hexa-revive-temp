bushexa 소스 배포 번들 (빌드는 서버에서)
========================================
모델: 단일 컨테이너(app) + supervisord(web + 2워커) + SQLite 단일 백엔드(postgres 불필요).

번들 생성 (개발 PC 또는 서버, 저장소 루트에서):
  tar cf bushexa-deploy.tar --transform 's,^,bushexa-deploy/,' \
    bushexa docker containers.conf pyproject.toml uv.lock .python-version \
    .dockerignore .env.example README.md README.txt scripts/recrawl_rail.sh
  # 콘텐츠(data/timetable, holidays, changelog 등)는 필요할 때만 별도로 추가.
  # 절대 포함 금지: .env, secret/, data/manager_password.txt, data/bushexa.db*,
  #                 data/logs.tsv, logs/, .venv, .git
  tar tf bushexa-deploy.tar | grep -E '\.env$|secret/|password|\.db'   # 출력이 없어야 함

compose 명령 (이 문서의 모든 podman 명령은 배포 루트에서, 이 형태로):
  CONTAINERS_CONF_OVERRIDE=$PWD/containers.conf podman-compose -f docker/compose.yaml <하위 명령>
  - CONTAINERS_CONF_OVERRIDE: rootless podman 의 keyring 생성(EDQUOT "Disk quota exceeded")을 끈다
    (containers.conf 머리 주석). 빠뜨리면 기동이 실패할 수 있다.
  - 아래의 pc 는 이 형태를 줄인 셸 함수다(배포 루트에서 한 번 정의):
      pc() { CONTAINERS_CONF_OVERRIDE=$PWD/containers.conf podman-compose -f docker/compose.yaml "$@"; }

서버에서 최초 빌드+기동:
  1) mkdir bushexa-deploy && tar xf bushexa-deploy.tar -C . && cd bushexa-deploy
  2) cp .env.example .env         # BUSHEXA_API_KEY, BUSHEXA_SESSION_SECRET, DATABASE_URL 채우기
  3) mkdir -p secret data logs    # secret/ 에 키 파일 배치(chmod 600)
  4) 최초 1회 스키마(SQLite, 기존 스키마 있으면 no-op):
       pc run --rm --entrypoint python app -m bushexa init-db
  5) pc up -d --build
  6) scripts/recrawl_rail.sh      # KTX·동해선 시간표 즉시 수집(안 하면 다음 새벽 02~03시)
  (docker 는 CONTAINERS_CONF_OVERRIDE 없이 docker compose -f docker/compose.yaml ...)

배포 시 1회 보안 조치 (2026-09-29 기준 미완료 — 끝나면 이 절을 지운다):
  a) 관리자 비밀번호 교체: 기동 후 http://<host>:8017/admin/password
     (예전 해시가 git 이력에 남아 있음 — docs/refactor/postmortems/PM-013)
  b) 수정(PM-016) 이전 로그에 남은 API 키 정리 — 앱을 멈춘 뒤 치환하고 다시 시작:
       pc stop app
       sudo sed -i -E "s/(service_?key=)[^&[:space:]\"'()<>]+/\\1***/Ig" logs/*.log*
       pc start app
       grep -ic "servicekey=[^*]" logs/*.log*   # 모두 0 이어야 함

갱신할 때 (코드만 바뀌어도 이 순서):
  새 번들의 bushexa/(와 필요한 data 파일)를 덮어쓴 뒤 컨테이너를 내렸다 올린다.
    pc down
    pc up -d --build
    scripts/recrawl_rail.sh      # 철도 수집 대상·규칙이 바뀐 배포면(예: /ktx) 즉시 재수집
  - restart app 만으로는 새 코드가 반영되지 않았다(운영 podman-compose, 2026-09-30). bushexa/ 는
    ro bind-mount 라 --build 는 캐시로 금방 끝난다.
  - data/·secret/·logs/ 는 호스트 bind-mount 라 down 해도 남는다. 덮어쓸 때 서버의 .env, secret/,
    data/, logs/ 는 건드리지 않는다(data/ 는 이번 배포에 새로 필요한 파일만 놓는다).

웹:   http://<host>:8017/        (compose 포트 매핑 8017:8000)
      http://<host>:8017/lite    (FASTER 모드 — 폰트/JS 없는 즉시 렌더 평문 HTML)
      http://<host>:8017/admin/  (관리자)
상태: pc ps
      pc exec app supervisorctl -c /app/docker/supervisord.conf status
로그: pc logs -f app     (호스트 logs/ 에도 파일로 기록)
참고: docker/compose.yaml 은 context: .. (= 번들 루트)로 빌드하며
      ../data(rw) ../secret(ro) ../logs 를 마운트합니다. (postgres-data 없음)
