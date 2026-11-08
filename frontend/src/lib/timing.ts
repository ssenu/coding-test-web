// 마지막 호출 후 wait ms가 지나면 한 번 실행한다. flush()로 즉시 실행, cancel()로 취소.
export interface Debounced<A extends unknown[]> {
  (...args: A): void
  flush(): void
  cancel(): void
}

export function debounce<A extends unknown[]>(fn: (...args: A) => void, wait: number): Debounced<A> {
  let timer: ReturnType<typeof setTimeout> | null = null
  let pending: A | null = null
  const run = () => {
    timer = null
    if (pending) {
      const args = pending
      pending = null
      fn(...args)
    }
  }
  const debounced = ((...args: A) => {
    pending = args
    if (timer) clearTimeout(timer)
    timer = setTimeout(run, wait)
  }) as Debounced<A>
  debounced.flush = () => {
    if (timer) clearTimeout(timer)
    run()
  }
  debounced.cancel = () => {
    if (timer) clearTimeout(timer)
    timer = null
    pending = null
  }
  return debounced
}

/** interval ms에 한 번만 실행한다(첫 호출은 바로). */
export function throttle<A extends unknown[]>(fn: (...args: A) => void, interval: number): (...args: A) => void {
  let last = -Infinity
  return (...args: A) => {
    const now = Date.now()
    if (now - last >= interval) {
      last = now
      fn(...args)
    }
  }
}
