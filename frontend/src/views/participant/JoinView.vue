<script setup lang="ts">
// 참가자 입장: 입장 코드와 이름. 같은 이름으로 다시 들어오면 관리자 승인을 기다린다.
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ApiError, loadParticipant, participantApi, saveParticipant } from '../../lib/api'

const POLL_MS = 3000

const route = useRoute()
const router = useRouter()
const entryCode = ref(typeof route.query.code === 'string' ? route.query.code : '')
const name = ref('')
const error = ref('')
const pending = ref(false)
const busy = ref(false)
let poll: ReturnType<typeof setInterval> | null = null

async function tryEnter(): Promise<boolean> {
  try {
    await participantApi.state()
    await router.push('/run')
    return true
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) pending.value = true
    return false
  }
}

function startPolling() {
  poll = setInterval(async () => {
    if (await tryEnter()) stopPolling()
  }, POLL_MS)
}

function stopPolling() {
  if (poll) clearInterval(poll)
  poll = null
}

async function submit() {
  busy.value = true
  error.value = ''
  try {
    const joined = await participantApi.join(entryCode.value, name.value)
    saveParticipant({ token: joined.token, runId: joined.run_id, participantId: joined.participant_id })
    if (joined.status === 'pending') {
      pending.value = true
      startPolling()
    } else {
      await router.push('/run')
    }
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : '입장하지 못했습니다.'
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  if (loadParticipant() && !(await tryEnter()) && pending.value) startPolling()
})
onBeforeUnmount(stopPolling)
</script>

<template>
  <main class="center-page">
    <div v-if="pending" class="card narrow" role="status">
      <h1>재입장 승인을 기다리는 중</h1>
      <p>같은 이름으로 이미 입장한 기록이 있습니다. 관리자가 승인하면 자동으로 들어갑니다.</p>
    </div>
    <form v-else class="card narrow" @submit.prevent="submit">
      <h1>코딩테스트 입장</h1>
      <label>
        입장 코드
        <input v-model="entryCode" required maxlength="12" autocomplete="off" class="code-input" />
      </label>
      <label>
        이름
        <input v-model="name" required maxlength="30" autocomplete="name" />
      </label>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <button class="primary" type="submit" :disabled="busy">입장하기</button>
    </form>
  </main>
</template>
