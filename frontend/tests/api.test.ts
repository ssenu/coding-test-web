import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  ApiError,
  adminApi,
  clearParticipant,
  loadParticipant,
  participantApi,
  saveParticipant,
} from '../src/lib/api'

function respond(status: number, body?: unknown) {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const fetchMock = vi.fn()

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
  localStorage.clear()
})
afterEach(() => vi.unstubAllGlobals())

describe('참가자 토큰 보관', () => {
  it('저장, 읽기, 지우기', () => {
    expect(loadParticipant()).toBeNull()
    saveParticipant({ token: 't', runId: 1, participantId: 2 })
    expect(loadParticipant()).toEqual({ token: 't', runId: 1, participantId: 2 })
    clearParticipant()
    expect(loadParticipant()).toBeNull()
  })

  it('깨진 값은 없는 것으로 본다', () => {
    localStorage.setItem('ctw.participant', '{oops')
    expect(loadParticipant()).toBeNull()
  })
})

describe('request', () => {
  it('JSON 본문을 보내고 응답을 돌려준다', async () => {
    fetchMock.mockResolvedValue(respond(200, { ok: true }))
    await expect(adminApi.login('pw')).resolves.toEqual({ ok: true })
    const [url, init] = fetchMock.mock.calls[0]!
    expect(url).toBe('/api/admin/login')
    expect(init).toMatchObject({ method: 'POST', body: '{"password":"pw"}', credentials: 'same-origin' })
    expect(init.headers['Content-Type']).toBe('application/json')
    expect(init.headers['X-Participant-Token']).toBeUndefined()
  })

  it('참가자 요청에는 토큰 헤더를 붙인다', async () => {
    saveParticipant({ token: 'tok', runId: 1, participantId: 2 })
    fetchMock.mockResolvedValue(respond(200, { box_id: 'a', submitted_at: 'x' }))
    await participantApi.submit('a', { 'a.py': 'x' })
    const [url, init] = fetchMock.mock.calls[0]!
    expect(url).toBe('/api/p/boxes/a/submit')
    expect(init.headers['X-Participant-Token']).toBe('tok')
    expect(JSON.parse(init.body)).toEqual({ files: { 'a.py': 'x' } })
  })

  it('204는 undefined를 돌려준다', async () => {
    fetchMock.mockResolvedValue(respond(204))
    await expect(adminApi.deleteTemplate(1)).resolves.toBeUndefined()
  })

  it('실패하면 detail 문자열을 메시지로 갖는 ApiError를 던진다', async () => {
    fetchMock.mockResolvedValue(respond(409, { detail: '이 단계는 닫혔습니다.' }))
    const err = await participantApi.submit('a', {}).catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err).toMatchObject({ status: 409, message: '이 단계는 닫혔습니다.' })
  })

  it('detail이 객체면 message를 쓰고 원본도 남긴다', async () => {
    const detail = { code: 'unsubmitted', box_ids: ['b'], message: '아직 제출하지 않은 파트가 1개 있습니다.' }
    fetchMock.mockResolvedValue(respond(409, { detail }))
    const err = (await adminApi.approve(1, ['b-team'], false).catch((e: unknown) => e)) as ApiError
    expect(err.message).toBe(detail.message)
    expect(err.detail).toEqual(detail)
  })

  it('검증 오류 배열은 일반 문구로 바꾼다', async () => {
    fetchMock.mockResolvedValue(respond(422, { detail: [{ loc: ['body'], msg: 'bad' }] }))
    await expect(adminApi.createTemplate('')).rejects.toThrow('입력값을 확인하세요.')
  })

  it('첨부 파일은 FormData로 올린다', async () => {
    fetchMock.mockResolvedValue(respond(201, { id: 1, box_id: 'a', filename: 'x.txt', size: 1 }))
    await adminApi.uploadTemplateFile(3, 'a', new File(['x'], 'x.txt'))
    const [url, init] = fetchMock.mock.calls[0]!
    expect(url).toBe('/api/templates/3/files')
    expect(init.body).toBeInstanceOf(FormData)
    expect((init.body as FormData).get('box_id')).toBe('a')
    expect(init.headers['Content-Type']).toBeUndefined()
  })
})
