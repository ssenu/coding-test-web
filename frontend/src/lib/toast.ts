// 잠깐 떴다 사라지는 안내. 화면은 ToastHost.vue가 그린다.
import { reactive } from 'vue'

export interface Toast {
  id: number
  message: string
  kind: 'ok' | 'error'
}

const SHOW_MS = 3500
let nextId = 1

export const toasts = reactive<Toast[]>([])

export function toast(message: string, kind: Toast['kind'] = 'ok'): void {
  const id = nextId++
  toasts.push({ id, message, kind })
  setTimeout(() => dismissToast(id), SHOW_MS)
}

export function dismissToast(id: number): void {
  const index = toasts.findIndex((t) => t.id === id)
  if (index >= 0) toasts.splice(index, 1)
}
