# frontend

Vue 3 + Vite + TypeScript. 관리자 화면(`/admin`)과 참가자 화면(`/`, `/run`).

## 개발

백엔드를 먼저 띄운다(`backend/README.md` 또는 도커 `localhost:8000`). Vite가 `/api`, `/ws`를 `localhost:8000`으로 넘긴다.

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
npm test           # Vitest
npm run build      # 타입 검사 후 dist/ 생성
```

## 화면

| 주소 | 화면 |
|---|---|
| `/admin/login` | 관리자 로그인 |
| `/admin` | 시험장 목록, 회차 목록 |
| `/admin/templates/:id` | 시험장 에디터 (박스 끌어 놓기, 선 연결, 속성) |
| `/admin/runs/:id` | 회차 진행 (참가자 배정, 승인, 제출 코드, 문제 수정) |
| `/admin/runs/:id/result` | 팀 버전과 최종 코드 |
| `/?code=입장코드` | 참가자 입장 |
| `/run` | 참가자 작업 화면 |

## 실시간

화면은 `/ws/runs/{id}`에 붙어 있다가 이벤트가 오면 상태를 다시 받는다(`팀 초안`만 바로 반영).
끊기면 0.5초부터 최대 10초 간격으로 다시 붙고, 4401/4404로 닫히면 다시 붙지 않는다.
