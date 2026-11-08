import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, adminApi } from '../src/lib/api'
import { router } from '../src/router'

beforeEach(() => vi.restoreAllMocks())

describe('관리자 화면 보호', () => {
  it('로그인하지 않았으면 로그인 화면으로 보내고 돌아올 주소를 남긴다', async () => {
    vi.spyOn(adminApi, 'me').mockRejectedValue(new ApiError(401, '관리자 로그인이 필요합니다.'))
    await router.push('/admin')
    expect(router.currentRoute.value.path).toBe('/admin/login')
    expect(router.currentRoute.value.query.next).toBe('/admin')
  })

  it('로그인했으면 그대로 들어간다', async () => {
    vi.spyOn(adminApi, 'me').mockResolvedValue({ admin: true })
    await router.push('/admin')
    expect(router.currentRoute.value.path).toBe('/admin')
  })

  it('로그인 화면은 확인 없이 열린다', async () => {
    const me = vi.spyOn(adminApi, 'me')
    await router.push('/admin/login')
    expect(router.currentRoute.value.path).toBe('/admin/login')
    expect(me).not.toHaveBeenCalled()
  })
})
