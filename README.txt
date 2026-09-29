bushexa 소스 배포 번들 (빌드는 서버에서)
========================================
모델: 단일 컨테이너(app) + supervisord(web + 2워커) + SQLite 단일 백엔드(postgres 불필요).

번들 생성 (개발 PC 또는 서버, 저장소 루트에서):
  tar cf bushexa-deploy.tar --transform 's,^,bushexa-deploy/,' \
    bushexa docker containers.conf pyproject.toml uv.lock .python-version \
    .dockerignore .env.example README.md README.txt
  # 콘텐츠(data/timetable, holidays, changelog 등)는 필요할 때만 별도로 추가.
  # 절대 포함 금지: .env, secret/, data/manager_password.txt, data/bushexa.db*,
  #                 data/logs.tsv, logs/, .venv, .git
  tar tf bushexa-deploy.tar | grep -E '\.env$|secret/|password|\.db'   # 출력이 없어야 함

서버에서 최초 빌드+기동 (podman compose 권장):
  1) mkdir bushexa-deploy && tar xf bushexa-deploy.tar -C . && cd bushexa-deploy
  2) cp .env.example .env         # BUSHEXA_API_KEY, BUSHEXA_SESSION_SECRET, DATABASE_URL 채우기
  3) mkdir -p secret data logs    # secret/ 에 키 파일 배치(chmod 600)
  4) 최초 1회 스키마(SQLite, 기존 스키마 있으면 no-op):
       podman compose -f docker/compose.yaml run --rm --entrypoint python app -m bushexa init-db
  5) podman compose -f docker/compose.yaml up -d --build
  (docker 도 동일: docker compose -f docker/compose.yaml ...)

배포 시 1회 보안 조치 (2026-09-29 기준 미완료 — 끝나면 이 절을 지운다):
  a) 관리자 비밀번호 교체: 기동 후 http://<host>:8017/admin/password
     (예전 해시가 git 이력에 남아 있음 — docs/refactor/postmortems/PM-013)
  b) 수정(PM-016) 이전 로그에 남은 API 키 정리 — 앱을 멈춘 뒤 치환하고 다시 시작:
       podman compose -f docker/compose.yaml stop app
       sudo sed -i -E "s/(service_?key=)[^&[:space:]\"'()<>]+/\\1***/Ig" logs/*.log*
       podman compose -f docker/compose.yaml start app
       grep -ic "servicekey=[^*]" logs/*.log*   # 모두 0 이어야 함

코드만 갱신할 때 (재빌드 불필요):
  compose 가 ../bushexa 를 /app/bushexa 로 ro bind-mount 하므로, 새 번들의 bushexa/ 를 덮어쓴 뒤
  재시작만 하면 된다. 이미지 재빌드는 pyproject.toml/uv.lock/docker/ 가 바뀔 때만.
    podman compose -f docker/compose.yaml restart app        # 코드만
    podman compose -f docker/compose.yaml up -d --build       # 의존성·Dockerfile 변경 시
  덮어쓸 때 서버의 .env, secret/, data/, logs/ 는 건드리지 않는다.

웹:   http://<host>:8017/        (compose 포트 매핑 8017:8000)
      http://<host>:8017/lite    (FASTER 모드 — 폰트/JS 없는 즉시 렌더 평문 HTML)
      http://<host>:8017/admin/  (관리자)
상태: podman compose -f docker/compose.yaml ps
      podman compose -f docker/compose.yaml exec app supervisorctl -c /app/docker/supervisord.conf status
로그: podman compose -f docker/compose.yaml logs -f app     (호스트 logs/ 에도 파일로 기록)
참고: docker/compose.yaml 은 context: .. (= 번들 루트)로 빌드하며
      ../data(rw) ../secret(ro) ../logs 를 마운트합니다. (postgres-data 없음)
