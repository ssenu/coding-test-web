<script setup lang="ts">
// Vue Flow 사용자 정의 노드. 에디터와 진행 화면이 함께 쓴다.
import { Handle, Position } from '@vue-flow/core'
import { BOX_STATE_LABEL, BOX_TYPE_LABEL, type BoxNodeData } from '../lib/graph'

defineProps<{ data: BoxNodeData; selected?: boolean }>()
</script>

<template>
  <div
    class="box-node"
    :class="[`type-${data.box.type}`, data.state ? `state-${data.state}` : '', { invalid: data.invalid, selected }]"
  >
    <Handle type="target" :position="Position.Left" />
    <div class="box-head">
      <span class="box-type">{{ BOX_TYPE_LABEL[data.box.type] }}</span>
      <span v-if="data.state" class="box-state">{{ BOX_STATE_LABEL[data.state] }}</span>
    </div>
    <div class="box-title">{{ data.box.title }}</div>
    <div v-if="data.badge" class="box-badge">{{ data.badge }}</div>
    <Handle v-if="data.box.type !== 'result'" type="source" :position="Position.Right" />
  </div>
</template>
