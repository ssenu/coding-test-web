<script setup lang="ts">
import { dismissToast, toasts } from '../lib/toast'
import AppIcon from './AppIcon.vue'
</script>

<template>
  <div class="toast-host" aria-live="polite">
    <TransitionGroup name="toast">
      <div v-for="t in toasts" :key="t.id" class="toast" :class="`toast-${t.kind}`" role="status">
        <AppIcon :name="t.kind === 'ok' ? 'check' : 'alert'" />
        <span>{{ t.message }}</span>
        <button type="button" class="icon-button" aria-label="닫기" @click="dismissToast(t.id)">
          <AppIcon name="x" />
        </button>
      </div>
    </TransitionGroup>
  </div>
</template>
