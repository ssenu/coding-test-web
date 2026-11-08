# backend

FastAPI 서버. 설계는 `docs/superpowers/specs/2026-11-08-coding-test-web-design.md`.

## 개발

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate      # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## 실행

```bash
ADMIN_PASSWORD=change-me SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))") DATA_DIR=./data \
  uvicorn app.main:create_app --factory --workers 1 --port 8000
```

- 워커는 반드시 1개. 웹소켓 연결과 입장 시도 제한을 메모리에 둔다.
- HTTPS 프록시 뒤에서는 `COOKIE_SECURE=1`.
- API 문서: http://localhost:8000/docs
