import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { ApiError, loadParticipant, participantApi } from '../src/lib/api'
import type { ParticipantState } from '../src/lib/types'
import JoinView from '../src/views/participant/JoinView.vue'

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: JoinView },
      { path: '/run', component: { template: '<p>work</p>' } },
    ],
  })
}

async function mountAt(path: string) {
  const router = makeRouter()
  await router.push(path)
  const wrapper = mount(JoinView, { global: { plugins: [router] } })
  await flushPromises()
  return { wrapper, router }
}

async function fillAndSubmit(wrapper: Awaited<ReturnType<typeof mountAt>>['wrapper'], code: string) {
  const [codeInput, nameInput] = wrapper.findAll('input')
  await codeInput!.setValue(code)
  await nameInput!.setValue('홍길동')
  await wrapper.find('form').trigger('submit')
  await flushPromises()
}

beforeEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

describe('JoinView', () => {
  it('?code= 로 입장 코드를 채운다', async () => {
    const { wrapper } = await mountAt('/?code=K7P2Q9')
    expect((wrapper.find('input').element as HTMLInputElement).value).toBe('K7P2Q9')
  })

  it('입장하면 토큰을 저장하고 작업 화면으로 간다', async () => {
    vi.spyOn(participantApi, 'join').mockResolvedValue({
      status: 'joined',
      token: 't',
      participant_id: 5,
      run_id: 2,
    })
    const { wrapper, router } = await mountAt('/')
    await fillAndSubmit(wrapper, 'K7P2Q9')
    expect(participantApi.join).toHaveBeenCalledWith('K7P2Q9', '홍길동')
    expect(loadParticipant()).toEqual({ token: 't', runId: 2, participantId: 5 })
    expect(router.currentRoute.value.path).toBe('/run')
  })

  it('같은 이름이면 승인 대기 화면을 보여 준다', async () => {
    vi.spyOn(participantApi, 'join').mockResolvedValue({
      status: 'pending',
      token: 't',
      participant_id: 5,
      run_id: 2,
    })
    const { wrapper } = await mountAt('/')
    await fillAndSubmit(wrapper, 'K7P2Q9')
    expect(wrapper.text()).toContain('재입장 승인을 기다리는 중')
    wrapper.unmount()
  })

  it('입장 실패 메시지를 보여 준다', async () => {
    vi.spyOn(participantApi, 'join').mockRejectedValue(new ApiError(404, '입장 코드를 확인하세요.'))
    const { wrapper } = await mountAt('/')
    await fillAndSubmit(wrapper, 'ZZZZZZ')
    expect(wrapper.find('[role=alert]').text()).toBe('입장 코드를 확인하세요.')
  })

  it('저장된 토큰이 살아 있으면 바로 작업 화면으로 간다', async () => {
    localStorage.setItem('ctw.participant', JSON.stringify({ token: 't', runId: 1, participantId: 1 }))
    vi.spyOn(participantApi, 'state').mockResolvedValue({} as ParticipantState)
    const { router } = await mountAt('/')
    expect(router.currentRoute.value.path).toBe('/run')
  })

  it('끝난 회차의 토큰이면 지우고 입장 화면에 머문다', async () => {
    localStorage.setItem('ctw.participant', JSON.stringify({ token: 't', runId: 1, participantId: 1 }))
    vi.spyOn(participantApi, 'state').mockResolvedValue({
      run: { id: 1, name: 'x', status: 'finished' },
    } as ParticipantState)
    const { wrapper, router } = await mountAt('/')
    expect(router.currentRoute.value.path).toBe('/')
    expect(loadParticipant()).toBeNull()
    expect(wrapper.find('form').exists()).toBe(true)
  })

  it('재입장 대기 중 토큰이 거절되면 안내와 함께 입장 화면으로 돌아간다', async () => {
    vi.useFakeTimers()
    try {
      vi.spyOn(participantApi, 'join').mockResolvedValue({
        status: 'pending',
        token: 't',
        participant_id: 5,
        run_id: 2,
      })
      vi.spyOn(participantApi, 'state').mockRejectedValue(new ApiError(401, '인증 실패'))
      const { wrapper } = await mountAt('/')
      await fillAndSubmit(wrapper, 'K7P2Q9')
      expect(wrapper.text()).toContain('재입장 승인을 기다리는 중')
      await vi.advanceTimersByTimeAsync(3000)
      await flushPromises()
      expect(wrapper.find('form').exists()).toBe(true)
      expect(wrapper.find('[role=alert]').text()).toBe('재입장이 승인되지 않았습니다. 다시 입장해 주세요.')
      expect(loadParticipant()).toBeNull()
      wrapper.unmount()
    } finally {
      vi.useRealTimers()
    }
  })
})
