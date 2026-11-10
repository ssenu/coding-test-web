<script setup lang="ts">
// dialog.ts의 요청을 네이티브 <dialog>로 띄운다. Esc와 바깥 클릭은 취소.
import { nextTick, ref, watch } from 'vue'
import { closeDialog, dialogState } from '../lib/dialog'

const el = ref<HTMLDialogElement>()
const input = ref<HTMLInputElement>()
const value = ref('')

watch(
  () => dialogState.current,
  async (request) => {
    if (!request) {
      if (el.value?.open) el.value.close()
      return
    }
    value.value = request.value
    await nextTick()
    if (!el.value?.open) el.value?.showModal()
    input.value?.select()
  },
)

function cancel() {
  closeDialog(dialogState.current?.kind === 'confirm' ? false : null)
}

function accept() {
  closeDialog(dialogState.current?.kind === 'confirm' ? true : value.value)
}
</script>

<template>
  <dialog ref="el" class="app-dialog" @cancel.prevent="cancel" @click.self="cancel">
    <form v-if="dialogState.current" class="dialog-body" @submit.prevent="accept">
      <h2>{{ dialogState.current.title }}</h2>
      <p v-if="dialogState.current.message" class="dialog-message">{{ dialogState.current.message }}</p>
      <label v-if="dialogState.current.kind === 'prompt'">
        {{ dialogState.current.inputLabel }}
        <input ref="input" v-model="value" required maxlength="100" />
      </label>
      <div class="dialog-actions">
        <button type="button" @click="cancel">{{ dialogState.current.cancelLabel }}</button>
        <button type="submit" :class="dialogState.current.danger ? 'danger solid' : 'primary'">
          {{ dialogState.current.confirmLabel }}
        </button>
      </div>
    </form>
  </dialog>
</template>
