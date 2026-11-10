<script setup lang="ts">
// 여러 코드 파일을 탭으로 보여 준다. 편집하면 바뀐 파일 묶음 전체를 update:files로 돌려준다.
// fill이면 부모 높이를 꽉 채운다(작업 화면의 코드 영역).
import { computed, ref, watch } from 'vue'
import type { Files } from '../lib/types'
import CodeEditor from './CodeEditor.vue'

const props = defineProps<{ files: Files; readonly?: boolean; fill?: boolean }>()
const emit = defineEmits<{ 'update:files': [files: Files] }>()

const names = computed(() => Object.keys(props.files))
const active = ref(names.value[0] ?? '')

watch(names, (list) => {
  if (!list.includes(active.value)) active.value = list[0] ?? ''
})

function update(code: string) {
  emit('update:files', { ...props.files, [active.value]: code })
}
</script>

<template>
  <div class="file-tabs" :class="{ fill }">
    <div class="tabs" role="tablist">
      <button
        v-for="name in names"
        :key="name"
        type="button"
        role="tab"
        :aria-selected="name === active"
        :class="{ active: name === active }"
        @click="active = name"
      >
        {{ name }}
      </button>
      <span v-if="readonly && names.length" class="tabs-note">읽기 전용</span>
    </div>
    <CodeEditor
      v-if="active"
      :key="active"
      :model-value="files[active] ?? ''"
      :readonly="readonly"
      :label="active"
      @update:model-value="update"
    />
    <p v-else class="muted empty">파일이 없습니다.</p>
  </div>
</template>
