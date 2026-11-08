# syntax=docker/dockerfile:1
# coding-test-web: 컨테이너 1개, 프로세스 1개 (FastAPI가 API, 웹소켓, 빌드된 프런트엔드를 함께 서비스)

# 1) 프런트엔드 빌드 (타입 검사 포함)
FROM node:24-bookworm-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# 2) 런타임: Python + 백엔드 + 프런트 dist
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    WEB_DIST=/app/web
WORKDIR /app
COPY backend/pyproject.toml ./
COPY backend/app ./app
RUN pip install --no-cache-dir . \
    && useradd --system --uid 10001 --no-create-home app \
    && mkdir -p /data \
    && chown app /data
COPY --from=web /web/dist ./web
USER app
VOLUME ["/data"]
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=4).status == 200 else 1)"]
# 워커는 반드시 1개 (웹소켓 연결과 시도 제한을 메모리에 둔다).
# --proxy-headers: Cloudflare Tunnel이 붙인 X-Forwarded-For로 실제 접속 IP를 쓴다. 포트는 서버에서 127.0.0.1에만 연다.
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
