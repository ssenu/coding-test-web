<script setup lang="ts">
// CodeMirror 6 래퍼. v-model로 코드를 주고받고, readonly면 편집을 막는다.
import { python } from '@codemirror/lang-python'
import { Annotation, Compartment, EditorState } from '@codemirror/state'
import { EditorView, basicSetup } from 'codemirror'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps<{ modelValue: string; readonly?: boolean; label?: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

// 부모가 내려준 값을 편집기에 넣는 변경은 사용자 입력이 아니므로 표시해 둔다
const external = Annotation.define<boolean>()

const host = ref<HTMLDivElement>()
const editable = new Compartment()
let view: EditorView | null = null

function editableExtensions(readonly: boolean) {
  return [EditorState.readOnly.of(readonly), EditorView.editable.of(!readonly)]
}

onMounted(() => {
  view = new EditorView({
    parent: host.value!,
    state: EditorState.create({
      doc: props.modelValue,
      extensions: [
        basicSetup,
        python(),
        editable.of(editableExtensions(!!props.readonly)),
        EditorView.contentAttributes.of({ 'aria-label': props.label ?? '코드 입력' }),
        EditorView.updateListener.of((update) => {
          if (update.docChanged && !update.transactions.some((tr) => tr.annotation(external))) emit('update:modelValue', update.state.doc.toString())
        }),
      ],
    }),
  })
})

watch(
  () => props.modelValue,
  (value) => {
    if (view && value !== view.state.doc.toString()) {
      view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: value },
        annotations: external.of(true),
      })
    }
  },
)

watch(
  () => props.readonly,
  (readonly) => view?.dispatch({ effects: editable.reconfigure(editableExtensions(!!readonly)) }),
)

onBeforeUnmount(() => view?.destroy())
</script>

<template>
  <div ref="host" class="code-editor" :class="{ readonly }" />
</template>
