<script setup lang="ts">
// 시험장 목록: 만들기, 편집, 복제, 삭제, 회차 열기. 시험장마다 지난 회차가 붙는다.
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import AppIcon from '../../components/AppIcon.vue'
import { ApiError, adminApi } from '../../lib/api'
import { confirmDialog, promptDialog } from '../../lib/dialog'
import { toast } from '../../lib/toast'
import type { RunSummary, TemplateSummary } from '../../lib/types'

const STATUS_LABEL = { lobby: '대기실', running: '진행 중', finished: '종료' } as const
const STATUS_CLASS = { lobby: 'warn', running: 'live', finished: '' } as const

const router = useRouter()
const templates = ref<TemplateSummary[]>([])
const runs = ref<RunSummary[]>([])
const loaded = ref(false)
const newName = ref('')
const error = ref('')

async function load() {
  ;[templates.value, runs.value] = await Promise.all([adminApi.listTemplates(), adminApi.listRuns()])
  loaded.value = true
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
    toast(`"${t.name}" 시험장을 복제했습니다.`)
  })

const remove = (t: TemplateSummary) =>
  guard(async () => {
    const ok = await confirmDialog({
      title: '시험장을 삭제할까요?',
      message: `"${t.name}" 시험장과 첨부 파일이 지워집니다. 되돌릴 수 없습니다.`,
      confirmLabel: '시험장 삭제',
      danger: true,
    })
    if (!ok) return
    await adminApi.deleteTemplate(t.id)
    await load()
  })

const openRun = (t: TemplateSummary) =>
  guard(async () => {
    const name = await promptDialog({
      title: '새 회차 열기',
      message: `"${t.name}" 시험장을 지금 상태 그대로 복사해 회차를 만듭니다.`,
      inputLabel: '회차 이름',
      value: `${new Date().toLocaleDateString('ko-KR')} 회차`,
      confirmLabel: '회차 열기',
    })
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
  <header class="topbar">
    <div class="brand-mark" style="margin: 0" aria-hidden="true"><i /><i /><i /><i /></div>
    <h1>코딩테스트 관리</h1>
    <span class="grow" />
    <button type="button" class="quiet" @click="logout"><AppIcon name="logout" />로그아웃</button>
  </header>

  <main class="page">
    <div class="page-title">
      <h2>시험장</h2>
    </div>

    <form class="create-form" @submit.prevent="create">
      <input v-model="newName" placeholder="새 시험장 이름" required maxlength="100" aria-label="새 시험장 이름" />
      <button class="primary" type="submit"><AppIcon name="plus" />시험장 만들기</button>
    </form>
    <p v-if="error" class="error" role="alert">{{ error }}</p>

    <div v-if="loaded && templates.length === 0" class="card empty-state">
      <h2>아직 시험장이 없습니다</h2>
      <p>위에 이름을 넣고 시험장을 만들면, 박스와 연결선으로 시험 흐름을 짤 수 있습니다.</p>
    </div>

    <section v-for="t in templates" :key="t.id" class="card template-card">
      <div class="template-head">
        <div class="grow">
          <h3>
            {{ t.name }}
            <span v-if="!t.valid" class="tag warn">검사 미통과</span>
          </h3>
          <p class="muted">{{ t.description || '설명 없음' }}</p>
        </div>
        <div class="row">
          <button
            type="button"
            class="primary"
            :disabled="!t.valid"
            :title="t.valid ? '' : '편집 화면에서 검사를 통과해야 회차를 열 수 있습니다'"
            @click="openRun(t)"
          >
            <AppIcon name="play" />새 회차 열기
          </button>
          <RouterLink class="button" :to="`/admin/templates/${t.id}`"><AppIcon name="pencil" />편집</RouterLink>
          <button type="button" class="icon-button" :aria-label="`${t.name} 복제`" title="복제" @click="duplicate(t)">
            <AppIcon name="copy" />
          </button>
          <button
            type="button"
            class="icon-button danger"
            :aria-label="`${t.name} 삭제`"
            title="삭제"
            @click="remove(t)"
          >
            <AppIcon name="trash" />
          </button>
        </div>
      </div>
      <ul v-if="runsOf(t.id).length" class="run-list">
        <li v-for="r in runsOf(t.id)" :key="r.id">
          <RouterLink :to="`/admin/runs/${r.id}`">
            <span class="run-name">{{ r.name }}</span>
            <span class="tag" :class="STATUS_CLASS[r.status]">{{ STATUS_LABEL[r.status] }}</span>
            <span class="grow" />
            <span class="mono">{{ r.entry_code }}</span>
            <span class="muted">{{ new Date(r.created_at).toLocaleDateString('ko-KR') }}</span>
          </RouterLink>
        </li>
      </ul>
    </section>
  </main>
</template>
