<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ApiError, adminApi } from '../../lib/api'

const router = useRouter()
const route = useRoute()
const password = ref('')
const error = ref('')
const busy = ref(false)

async function submit() {
  busy.value = true
  error.value = ''
  try {
    await adminApi.login(password.value)
    const next = typeof route.query.next === 'string' ? route.query.next : '/admin'
    await router.push(next)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : '로그인하지 못했습니다.'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <main class="center-page">
    <form class="card narrow" @submit.prevent="submit">
      <h1>관리자 로그인</h1>
      <label>
        비밀번호
        <input v-model="password" type="password" autocomplete="current-password" required autofocus />
      </label>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <button class="primary" type="submit" :disabled="busy">로그인</button>
    </form>
  </main>
</template>
