<script setup lang="ts">
import AppDialog from './components/AppDialog.vue'
import ToastHost from './components/ToastHost.vue'
</script>

<template>
  <RouterView />
  <AppDialog />
  <ToastHost />
</template>
