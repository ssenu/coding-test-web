// 회차 웹소켓. 끊기면 점점 간격을 늘려 다시 붙고, 붙을 때마다 onOpen으로 전체 상태를 다시 받게 한다.
// 서버는 인증 실패 시 4401, 없는 회차면 4404로 닫는다. 이때는 재접속하지 않는다.

export interface ServerEvent {
  event: string
  data: Record<string, unknown>
}

export interface SocketHandlers {
  onEvent: (event: ServerEvent) => void
  onOpen?: () => void
  onAuthFailed?: (code: number) => void
}

type WebSocketCtor = new (url: string) => WebSocket

export const AUTH_FAIL_CODES = [4401, 4404]
const BASE_DELAY_MS = 500
const MAX_DELAY_MS = 10_000

export function runSocketUrl(runId: number, token?: string, loc: Location = window.location): string {
  const proto = loc.protocol === 'https:' ? 'wss' : 'ws'
  const query = token ? `?token=${encodeURIComponent(token)}` : ''
  return `${proto}://${loc.host}/ws/runs/${runId}${query}`
}

export function reconnectDelay(attempt: number): number {
  return Math.min(BASE_DELAY_MS * 2 ** attempt, MAX_DELAY_MS)
}

export class RunSocket {
  private ws: WebSocket | null = null
  private attempt = 0
  private timer: ReturnType<typeof setTimeout> | null = null
  private stopped = false
  private readonly url: string
  private readonly handlers: SocketHandlers
  private readonly Impl: WebSocketCtor

  constructor(url: string, handlers: SocketHandlers, Impl: WebSocketCtor = WebSocket) {
    this.url = url
    this.handlers = handlers
    this.Impl = Impl
  }

  start(): void {
    this.stopped = false
    this.connect()
  }

  stop(): void {
    this.stopped = true
    if (this.timer) clearTimeout(this.timer)
    this.timer = null
    this.ws?.close()
    this.ws = null
  }

  send(message: Record<string, unknown>): boolean {
    if (!this.ws || this.ws.readyState !== 1) return false
    this.ws.send(JSON.stringify(message))
    return true
  }

  private connect(): void {
    const ws = new this.Impl(this.url)
    this.ws = ws
    ws.onopen = () => {
      this.attempt = 0
      this.handlers.onOpen?.()
    }
    ws.onmessage = (msg: MessageEvent) => {
      try {
        const parsed = JSON.parse(String(msg.data)) as ServerEvent
        if (parsed && typeof parsed.event === 'string') this.handlers.onEvent(parsed)
      } catch {
        // 형식이 맞지 않는 메시지는 무시한다
      }
    }
    ws.onclose = (ev: CloseEvent) => {
      if (this.ws !== ws || this.stopped) return
      this.ws = null
      if (AUTH_FAIL_CODES.includes(ev.code)) {
        this.handlers.onAuthFailed?.(ev.code)
        return
      }
      const delay = reconnectDelay(this.attempt)
      this.attempt += 1
      this.timer = setTimeout(() => this.connect(), delay)
    }
  }
}
