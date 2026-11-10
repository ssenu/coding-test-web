<script setup lang="ts">
// 결과 보기: 팀 박스별 저장 버전 목록과 선택한 버전의 파일.
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import AppIcon from '../../components/AppIcon.vue'
import FileTabs from '../../components/FileTabs.vue'
import { ApiError, adminApi } from '../../lib/api'
import type { AdminState, Files, VersionSummary } from '../../lib/types'

const route = useRoute()
const runId = Number(route.params.id)

const state = ref<AdminState | null>(null)
const selected = ref<(VersionSummary & { files: Files }) | null>(null)
const error = ref('')

const teamBoxes = computed(() => state.value?.graph.boxes.filter((b) => b.type === 'team') ?? [])

async function open(version: VersionSummary) {
  error.value = ''
  try {
    selected.value = await adminApi.version(runId, version.id)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : '버전을 불러오지 못했습니다.'
  }
}

onMounted(async () => {
  try {
    state.value = await adminApi.runState(runId)
    const all = Object.values(state.value.team_versions).flat()
    const final = [...all].reverse().find((v) => v.is_final) ?? all.at(-1)
    if (final) await open(final)
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : '결과를 불러오지 못했습니다.'
  }
})
</script>

<template>
  <main class="result-page">
    <header class="topbar">
      <RouterLink :to="`/admin/runs/${runId}`" class="button quiet back" aria-label="진행 화면으로">
        <AppIcon name="arrow-left" />
      </RouterLink>
      <h1>{{ state?.run.name ?? '결과' }}</h1>
      <span class="tag">결과</span>
    </header>
    <p v-if="error" class="banner error" role="alert"><AppIcon name="alert" />{{ error }}</p>
    <div class="result-grid">
      <aside aria-label="버전">
        <section v-for="box in teamBoxes" :key="box.id">
          <h3 style="margin-top: 0">{{ box.title }}</h3>
          <p v-if="!state?.team_versions[box.id]?.length" class="muted">아직 저장한 버전이 없습니다.</p>
          <ul class="version-list">
            <li v-for="v in state?.team_versions[box.id] ?? []" :key="v.id">
              <button type="button" :class="{ active: selected?.id === v.id }" @click="open(v)">
                버전 {{ v.version_no }}
                <span v-if="v.is_final" class="tag ok">최종</span>
                <span class="muted">{{ new Date(v.saved_at).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' }) }}</span>
              </button>
            </li>
          </ul>
        </section>
      </aside>
      <section v-if="selected">
        <h2>버전 {{ selected.version_no }}<span v-if="selected.is_final"> · 최종 제출</span></h2>
        <FileTabs :files="selected.files" readonly />
      </section>
      <section v-else>
        <div class="empty-state">
          <h2>볼 버전이 없습니다</h2>
          <p>팀장이 버전을 저장하거나 최종 제출하면 여기서 코드를 볼 수 있습니다.</p>
        </div>
      </section>
    </div>
  </main>
</template>
