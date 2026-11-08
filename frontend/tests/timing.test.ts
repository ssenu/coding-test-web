import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { debounce, throttle } from '../src/lib/timing'

describe('timing', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('debounce는 마지막 호출만 실행하고 flush, cancel을 지원한다', () => {
    const fn = vi.fn()
    const d = debounce(fn, 100)
    d(1)
    d(2)
    vi.advanceTimersByTime(100)
    expect(fn).toHaveBeenCalledTimes(1)
    expect(fn).toHaveBeenLastCalledWith(2)
    d(3)
    d.flush()
    expect(fn).toHaveBeenLastCalledWith(3)
    d(4)
    d.cancel()
    vi.advanceTimersByTime(500)
    expect(fn).toHaveBeenCalledTimes(2)
  })

  it('throttle은 간격 안의 호출을 버린다', () => {
    const fn = vi.fn()
    const t = throttle(fn, 1000)
    t()
    t()
    vi.advanceTimersByTime(1000)
    t()
    expect(fn).toHaveBeenCalledTimes(2)
  })
})
