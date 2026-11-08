"""회차별 웹소켓 연결을 들고 이벤트를 보낸다. uvicorn 워커 1개를 전제로 메모리에 둔다."""
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Protocol


class Socket(Protocol):
    async def send_json(self, data: Any) -> None: ...
    async def close(self, code: int = 1000) -> None: ...


@dataclass(eq=False)
class Conn:
    socket: Socket
    role: str                       # "admin" | "participant"
    participant_id: int | None = None
    token_hash: str | None = None


class Hub:
    def __init__(self) -> None:
        self._conns: dict[int, list[Conn]] = defaultdict(list)

    def connect(self, run_id: int, conn: Conn) -> None:
        self._conns[run_id].append(conn)

    def disconnect(self, run_id: int, conn: Conn) -> None:
        conns = self._conns.get(run_id, [])
        if conn in conns:
            conns.remove(conn)

    def online(self, run_id: int) -> set[int]:
        return {
            c.participant_id
            for c in self._conns.get(run_id, [])
            if c.role == "participant" and c.participant_id is not None
        }

    async def _send(self, run_id: int, targets: list[Conn], event: str, data: dict) -> None:
        message = {"event": event, "data": data}
        for conn in targets:
            try:
                await conn.socket.send_json(message)
            except Exception:
                self.disconnect(run_id, conn)

    async def to_all(self, run_id: int, event: str, data: dict) -> None:
        await self._send(run_id, list(self._conns.get(run_id, [])), event, data)

    async def to_admins(self, run_id: int, event: str, data: dict) -> None:
        targets = [c for c in self._conns.get(run_id, []) if c.role == "admin"]
        await self._send(run_id, targets, event, data)

    async def to_participants(
        self, run_id: int, event: str, data: dict, exclude: int | None = None
    ) -> None:
        targets = [
            c for c in self._conns.get(run_id, [])
            if c.role == "participant" and c.participant_id != exclude
        ]
        await self._send(run_id, targets, event, data)

    async def kick(self, run_id: int, participant_id: int, keep_token_hash: str | None = None) -> None:
        """해당 참가자의 연결 중 keep_token_hash가 아닌 것을 끊는다(재입장 승인 시 이전 기기)."""
        targets = [
            c for c in self._conns.get(run_id, [])
            if c.participant_id == participant_id and c.token_hash != keep_token_hash
        ]
        for conn in targets:
            self.disconnect(run_id, conn)
            try:
                await conn.socket.close(code=4401)
            except Exception:
                pass
