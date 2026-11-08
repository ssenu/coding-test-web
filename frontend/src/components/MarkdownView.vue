<script setup lang="ts">
import { computed } from 'vue'
import { renderMarkdown } from '../lib/markdown'

const props = defineProps<{ source: string }>()
const html = computed(() => renderMarkdown(props.source))
</script>

<template>
  <!-- renderMarkdown이 DOMPurify로 정리한 HTML만 넣는다 -->
  <div class="markdown" v-html="html" />
</template>
