# docker/Dockerfile — bushexa 운영 이미지 (COPY 최소화 / bind-mount 모델)
#
# 레거시(루트 Dockerfile + podman-compose) 방식을 따른다: 애플리케이션 소스·데이터·
# 시크릿을 이미지에 굽지 않고 compose 에서 호스트 디렉토리를 bind-mount 한다.
#   → 이미지에는 "의존성 venv"만 들어간다. 코드가 바뀌어도 재빌드가 필요 없으므로
#     매 배포마다 새 이미지/빌드캐시가 graphRoot(quota 걸린 저장소)에 쌓이지 않는다.
#
# 단일 이미지로 web/worker 를 모두 사용한다(compose 의 command 로 분기):
#   - web    : ["serve", ...]               → flask/gunicorn
#   - worker : ["crawl-loop"] / ["arrival-loop"]
#
# 실행: `python -m bushexa <subcommand>` (bushexa/__main__.py → cli.main).
#       editable 설치가 아니라 PYTHONPATH=/app 의 bind-mount 소스를 직접 import 한다.
#
# HEALTHCHECK 는 Dockerfile 에 두지 않는다 — worker 엔 HTTP 가 없어 항상 unhealthy 가
# 되기 때문. web 헬스체크는 compose 에만 둔다.

# ──────────────────────────── builder (의존성 전용) ────────────────────────────
FROM python:3.12-slim-bookworm AS builder

# uv 설치(빌드 전용)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

ENV UV_PYTHON_PREFERENCE=only-system \
    UV_PYTHON=python3.12 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

WORKDIR /app

# 락/메타만 복사하고 의존성만 설치한다(--no-install-project).
# 소스는 굽지 않으므로 코드 변경이 이 레이어를 무효화하지 않는다 = 재빌드 거의 없음.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --all-extras --no-install-project

# ──────────────────────────── runtime ────────────────────────────
FROM python:3.12-slim-bookworm AS runtime

# curl: compose 헬스체크용. ca-certificates: 외부 HTTPS 호출용.
# supervisor: 단일 컨테이너에서 web+worker 2개를 함께 구동(docker/supervisord.conf).
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates supervisor \
    && rm -rf /var/lib/apt/lists/*

ENV TZ=Asia/Seoul \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_NO_SYNC=1

WORKDIR /app

# 이미지에 굽는 것: 의존성 venv 하나뿐. (소스·data·secret·logs 는 모두 bind-mount)
COPY --from=builder /app/.venv /app/.venv

# supervisord 설정(거의 안 바뀜)만 굽는다 — 단일 컨테이너 통합 구동용.
COPY docker/supervisord.conf /app/docker/supervisord.conf

EXPOSE 8000

# rootless podman 에서 컨테이너 root 는 호스트 실행 유저로 매핑되므로 bind-mount 한
# 호스트 디렉토리(logs/data)에 그대로 쓸 수 있다. non-root 로 고정하면 bind-mount 쓰기에
# uid 매핑(--userns=keep-id) 추가 설정이 필요해 운영을 단순화하기 위해 root 로 둔다.
ENTRYPOINT ["python", "-m", "bushexa"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8000"]
