# coding-test-web

단계형 팀 코딩테스트를 진행하는 웹. 관리자가 박스(공통 · 개인 · 팀 · 결과)와 연결선으로 시험장을 만들고, 회차를 열어 참가자 입장 · 배정 · 승인 · 팀 단계를 실시간으로 관리한다.

- 설계: `docs/superpowers/specs/2026-11-08-coding-test-web-design.md`
- 백엔드(FastAPI + SQLite): `backend/README.md`
- 프런트엔드(Vue 3 + Vite): `frontend/README.md`

## 로컬에서 컨테이너로 실행

```bash
cp .env.example .env      # ADMIN_PASSWORD, SECRET_KEY 채우기
docker compose up -d --build
# http://localhost:8080/admin
```

컨테이너 1개가 API, 웹소켓(`/ws`), 빌드된 프런트엔드를 함께 서비스한다. 데이터(SQLite, 첨부 파일)는 볼륨 `data`(`/data`)에 남는다. 워커는 1개로 고정돼 있다.

## 서버 배포 (myserver)

다른 앱들과 같은 방식이다: 저장소를 `/srv/apps`에 clone하고, 서버 전용 설정은 git에 없는 파일로 둔다.

```bash
cd /srv/apps && git clone https://github.com/ssenu/coding-test-web.git && cd coding-test-web
cp .env.example .env && chmod 600 .env
# .env: ADMIN_PASSWORD, SECRET_KEY, COOKIE_SECURE=1, ALLOWED_ORIGINS=https://cotest.ssenu.cloud
```

`docker-compose.override.yml` (git에 없음, `chmod 600`):

```yaml
# 서버 전용: 127.0.0.1에만 열고 Cloudflare Tunnel(myserver)이 받는다
services:
  app:
    ports: !override
      - "127.0.0.1:8009:8080"
```

```bash
docker compose up -d --build
curl -s 127.0.0.1:8009/api/health
```

Cloudflare Tunnel: `~/.cloudflared/config-myserver.yml`의 `ingress`에서 404 규칙 앞에 아래를 넣고(수정 전 백업),

```yaml
- hostname: cotest.ssenu.cloud
  service: http://localhost:8009
```

```bash
cloudflared tunnel route dns myserver cotest.ssenu.cloud
systemctl --user restart cft-tunnel-myserver
```

### 업데이트

```bash
cd /srv/apps/coding-test-web && git pull && docker compose up -d --build
```

## 주차장 과제 넣기

문제 파일은 저장소에 두지 않는다. 학생용 문제 폴더(`a_entry.py`~`e_main.py`)를 가진 PC에서:

```bash
cd backend && source .venv/Scripts/activate
python ../scripts/seed_parking.py --url https://cotest.ssenu.cloud --password '<관리자 비밀번호>' --dir "<student 폴더>"
```
