// 확인·입력 대화상자. window.confirm / window.prompt 대신 쓴다. 화면은 AppDialog.vue가 그린다.
import { reactive } from 'vue'

export interface DialogRequest {
  kind: 'confirm' | 'prompt'
  title: string
  message?: string
  confirmLabel: string
  cancelLabel: string
  danger: boolean
  value: string
  inputLabel: string
  resolve: (result: string | boolean | null) => void
}

export interface DialogOptions {
  title: string
  message?: string
  confirmLabel?: string
  cancelLabel?: string
  danger?: boolean
}

export const dialogState = reactive<{ current: DialogRequest | null }>({ current: null })

function open(kind: DialogRequest['kind'], options: DialogOptions, value = '', inputLabel = '') {
  return new Promise<string | boolean | null>((resolve) => {
    // 이미 열린 대화상자가 있으면 취소로 닫는다
    dialogState.current?.resolve(dialogState.current.kind === 'confirm' ? false : null)
    dialogState.current = {
      kind,
      title: options.title,
      message: options.message,
      confirmLabel: options.confirmLabel ?? '확인',
      cancelLabel: options.cancelLabel ?? '취소',
      danger: options.danger ?? false,
      value,
      inputLabel,
      resolve,
    }
  })
}

export function confirmDialog(options: DialogOptions): Promise<boolean> {
  return open('confirm', options).then((r) => r === true)
}

export function promptDialog(options: DialogOptions & { value?: string; inputLabel: string }): Promise<string | null> {
  return open('prompt', options, options.value ?? '', options.inputLabel).then((r) =>
    typeof r === 'string' && r.trim() ? r.trim() : null,
  )
}

export function closeDialog(result: string | boolean | null): void {
  const current = dialogState.current
  dialogState.current = null
  current?.resolve(result)
}
