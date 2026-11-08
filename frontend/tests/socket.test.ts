import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { RunSocket, type SocketHandlers, reconnectDelay, runSocketUrl } from '../src/lib/socket'

class FakeSocket {
  static instances: FakeSocket[] = []
  readyState = 0
  sent: string[] = []
  onopen: (() => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  onclose: ((e: { code: number }) => void) | null = null
  url: string

  constructor(url: string) {
    this.url = url
    FakeSocket.instances.push(this)
  }

  send(data: string) {
    this.sent.push(data)
  }

  close() {
    this.readyState = 3
  }

  open() {
    this.readyState = 1
    this.onopen?.()
  }

  serverClose(code: number) {
    this.readyState = 3
    this.onclose?.({ code })
  }
}

function make(handlers: Partial<SocketHandlers> = {}) {
  const onEvent = vi.fn()
  const socket = new RunSocket(
    'ws://x/ws/runs/1',
    { onEvent, ...handlers },
    FakeSocket as unknown as typeof WebSocket,
  )
  return { socket, onEvent }
}

beforeEach(() => {
  FakeSocket.instances = []
  vi.useFakeTimers()
})
afterEach(() => vi.useRealTimers())

describe('runSocketUrl', () => {
  it('http면 ws, https면 wss를 쓰고 토큰을 붙인다', () => {
    expect(runSocketUrl(3, undefined, { protocol: 'http:', host: 'h:5173' } as Location)).toBe(
      'ws://h:5173/ws/runs/3',
    )
    expect(runSocketUrl(3, 'a b', { protocol: 'https:', host: 'site' } as Location)).toBe(
      'wss://site/ws/runs/3?token=a%20b',
    )
  })
})

describe('RunSocket', () => {
  it('메시지를 이벤트로 넘기고 형식이 틀린 메시지는 버린다', () => {
    const { socket, onEvent } = make()
    socket.start()
    const ws = FakeSocket.instances[0]!
    ws.open()
    ws.onmessage?.({ data: '{"event":"box_state_changed","data":{"box_id":"a"}}' })
    ws.onmessage?.({ data: 'not json' })
    ws.onmessage?.({ data: '{"nope":1}' })
    expect(onEvent).toHaveBeenCalledTimes(1)
    expect(onEvent).toHaveBeenCalledWith({ event: 'box_state_changed', data: { box_id: 'a' } })
  })

  it('열려 있을 때만 보낸다', () => {
    const { socket } = make()
    socket.start()
    const ws = FakeSocket.instances[0]!
    expect(socket.send({ type: 'ping' })).toBe(false)
    ws.open()
    expect(socket.send({ type: 'ping' })).toBe(true)
    expect(ws.sent).toEqual(['{"type":"ping"}'])
  })

  it('끊기면 점점 늘어나는 간격으로 다시 붙고, 붙으면 onOpen을 부른다', () => {
    const onOpen = vi.fn()
    const { socket } = make({ onOpen })
    socket.start()
    FakeSocket.instances[0]!.serverClose(1006)
    vi.advanceTimersByTime(reconnectDelay(0) - 1)
    expect(FakeSocket.instances).toHaveLength(1)
    vi.advanceTimersByTime(1)
    expect(FakeSocket.instances).toHaveLength(2)
    FakeSocket.instances[1]!.serverClose(1006)
    vi.advanceTimersByTime(reconnectDelay(1))
    expect(FakeSocket.instances).toHaveLength(3)
    FakeSocket.instances[2]!.open()
    expect(onOpen).toHaveBeenCalledTimes(1)
  })

  it('인증 실패 코드로 닫히면 다시 붙지 않는다', () => {
    const onAuthFailed = vi.fn()
    const { socket } = make({ onAuthFailed })
    socket.start()
    FakeSocket.instances[0]!.serverClose(4401)
    vi.advanceTimersByTime(60_000)
    expect(FakeSocket.instances).toHaveLength(1)
    expect(onAuthFailed).toHaveBeenCalledWith(4401)
  })

  it('stop() 뒤에는 다시 붙지 않는다', () => {
    const { socket } = make()
    socket.start()
    const ws = FakeSocket.instances[0]!
    socket.stop()
    ws.serverClose(1006)
    vi.advanceTimersByTime(60_000)
    expect(FakeSocket.instances).toHaveLength(1)
  })

  it('재접속 간격은 10초를 넘지 않는다', () => {
    expect([0, 1, 2, 10].map(reconnectDelay)).toEqual([500, 1000, 2000, 10_000])
  })
})
