<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ApiError, adminApi } from '../../lib/api'
import type { RunSummary, TemplateSummary } from '../../lib/types'

const STATUS_LABEL = { lobby: '대기실', running: '진행 중', finished: '종료' } as const

const router = useRouter()
const templates = ref<TemplateSummary[]>([])
const runs = ref<RunSummary[]>([])
const newName = ref('')
const error = ref('')

async function load() {
  ;[templates.value, runs.value] = await Promise.all([adminApi.listTemplates(), adminApi.listRuns()])
}

function runsOf(templateId: number) {
  return runs.value.filter((r) => r.template_id === templateId)
}

async function guard(action: () => Promise<unknown>) {
  error.value = ''
  try {
    await action()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : '요청을 처리하지 못했습니다.'
  }
}

const create = () =>
  guard(async () => {
    const t = await adminApi.createTemplate(newName.value.trim())
    newName.value = ''
    await router.push(`/admin/templates/${t.id}`)
  })

const duplicate = (t: TemplateSummary) =>
  guard(async () => {
    await adminApi.duplicateTemplate(t.id)
    await load()
  })

const remove = (t: TemplateSummary) =>
  guard(async () => {
    if (!window.confirm(`"${t.name}" 시험장을 삭제할까요?`)) return
    await adminApi.deleteTemplate(t.id)
    await load()
  })

const openRun = (t: TemplateSummary) =>
  guard(async () => {
    const name = window.prompt('회차 이름', `${new Date().toLocaleDateString('ko-KR')} 회차`)
    if (!name) return
    const run = await adminApi.createRun(t.id, name)
    await router.push(`/admin/runs/${run.id}`)
  })

const logout = () =>
  guard(async () => {
    await adminApi.logout()
    await router.push('/admin/login')
  })

onMounted(() => guard(load))
</script>

<template>
  <main class="page">
    <header class="page-head">
      <h1>시험장</h1>
      <button type="button" @click="logout">로그아웃</button>
    </header>

    <form class="row" @submit.prevent="create">
      <input v-model="newName" placeholder="새 시험장 이름" required maxlength="100" aria-label="새 시험장 이름" />
      <button class="primary" type="submit">시험장 만들기</button>
    </form>
    <p v-if="error" class="error" role="alert">{{ error }}</p>

    <p v-if="templates.length === 0" class="muted">아직 시험장이 없습니다. 이름을 넣고 시험장을 만들어 보세요.</p>

    <section v-for="t in templates" :key="t.id" class="card template-card">
      <div class="row spread">
        <div>
          <h2>{{ t.name }}</h2>
          <p class="muted">{{ t.description || '설명 없음' }}</p>
        </div>
        <span class="tag" :class="t.valid ? 'ok' : 'warn'">{{ t.valid ? '회차를 열 수 있음' : '검사 미통과' }}</span>
      </div>
      <div class="row">
        <RouterLink class="button" :to="`/admin/templates/${t.id}`">편집</RouterLink>
        <button type="button" :disabled="!t.valid" @click="openRun(t)">새 회차 열기</button>
        <button type="button" @click="duplicate(t)">복제</button>
        <button type="button" class="danger" @click="remove(t)">삭제</button>
      </div>
      <ul v-if="runsOf(t.id).length" class="run-list">
        <li v-for="r in runsOf(t.id)" :key="r.id">
          <RouterLink :to="`/admin/runs/${r.id}`">{{ r.name }}</RouterLink>
          <span class="tag">{{ STATUS_LABEL[r.status] }}</span>
          <span class="muted">입장 코드 {{ r.entry_code }}</span>
        </li>
      </ul>
    </section>
  </main>
</template>
