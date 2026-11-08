<script setup lang="ts">
// 회차 진행 화면: 참가자 배정, 흐름도(박스 상태), 승인, 제출 코드 보기, 문제 수정.
import { Background } from '@vue-flow/background'
import { VueFlow } from '@vue-flow/core'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import BoxNode from '../../components/BoxNode.vue'
import FileTabs from '../../components/FileTabs.vue'
import { ApiError, adminApi } from '../../lib/api'
import { BOX_STATE_LABEL, BOX_TYPE_LABEL, autoLayout, needsLayout, toFlowEdges, toFlowNodes } from '../../lib/graph'
import { assignmentWarnings, boxBadges, boxStates, type Gate, pendingGates } from '../../lib/run'
import { RunSocket, runSocketUrl } from '../../lib/socket'
import { debounce } from '../../lib/timing'
import type { AdminState, ParticipantInfo, Submission } from '../../lib/types'

const STATUS_LABEL = { lobby: '대기실', running: '진행 중', finished: '종료' } as const

const route = useRoute()
const runId = Number(route.params.id)

const state = ref<AdminState | null>(null)
const error = ref('')
const selectedBoxId = ref<string | null>(null)
const submission = ref<Submission | null>(null)
const markdownDraft = ref('')
const copied = ref(false)

const personalBoxes = computed(() => state.value?.graph.boxes.filter((b) => b.type === 'personal') ?? [])
const gates = computed(() => (state.value ? pendingGates(state.value) : []))
const warnings = computed(() => (state.value ? assignmentWarnings(state.value) : []))
const nodes = computed(() =>
  state.value
    ? toFlowNodes(needsLayout(state.value.graph) ? autoLayout(state.value.graph) : state.value.graph, {
        states: boxStates(state.value),
        badges: boxBadges(state.value),
      })
    : [],
)
const edges = computed(() => (state.value ? toFlowEdges(state.value.graph, state.value.approved_edges) : []))
const selectedBox = computed(() => state.value?.graph.boxes.find((b) => b.id === selectedBoxId.value) ?? null)
const joinLink = computed(() => (state.value ? `${location.origin}/?code=${state.value.run.entry_code}` : ''))

async function refresh() {
  state.value = await adminApi.runState(runId)
}

const refreshSoon = debounce(() => {
  refresh().catch(() => undefined)
}, 200)

async function guard(action: () => Promise<unknown>) {
  error.value = ''
  try {
    await action()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : '요청을 처리하지 못했습니다.'
  }
}

const socket = new RunSocket(runSocketUrl(runId), {
  onOpen: () => refreshSoon(),
  onEvent: () => refreshSoon(),
  onAuthFailed: () => {
    error.value = '관리자 로그인이 만료되었습니다. 다시 로그인하세요.'
  },
})

// ---------------------------------------------------------------- 회차
const start = () => guard(async () => (state.value = await adminApi.startRun(runId)))
const finish = () =>
  guard(async () => {
    if (!window.confirm('회차를 종료할까요? 참가자는 더 이상 제출할 수 없습니다.')) return
    state.value = await adminApi.finishRun(runId)
  })

async function copyLink() {
  await navigator.clipboard.writeText(joinLink.value)
  copied.value = true
  setTimeout(() => (copied.value = false), 1500)
}

// ---------------------------------------------------------------- 참가자
const assign = (p: ParticipantInfo, boxId: string) =>
  guard(async () => {
    await adminApi.patchParticipant(runId, p.id, { assigned_box_id: boxId || null })
    await refresh()
  })

const makeLeader = (p: ParticipantInfo) =>
  guard(async () => {
    await adminApi.patchParticipant(runId, p.id, { is_leader: true })
    await refresh()
  })

const approveRejoin = (p: ParticipantInfo) =>
  guard(async () => {
    await adminApi.approveRejoin(runId, p.id)
    await refresh()
  })

const removePerson = (p: ParticipantInfo) =>
  guard(async () => {
    if (!window.confirm(`${p.name}님을 회차에서 뺄까요?`)) return
    await adminApi.removeParticipant(runId, p.id)
    await refresh()
  })

function ownerOf(boxId: string) {
  return state.value?.participants.find((p) => p.assigned_box_id === boxId) ?? null
}

// ---------------------------------------------------------------- 승인
const approveGate = (gate: Gate) =>
  guard(async () => {
    try {
      state.value = await adminApi.approve(runId, gate.edgeIds, false)
    } catch (e) {
      const detail = e instanceof ApiError ? (e.detail as { code?: string; message?: string }) : null
      if (detail?.code !== 'unsubmitted') throw e
      if (!window.confirm(`${detail.message} 그래도 승인할까요? 제출하지 않은 파트는 시작 코드로 넘어갑니다.`)) return
      state.value = await adminApi.approve(runId, gate.edgeIds, true)
    }
  })

// ---------------------------------------------------------------- 박스 상세
// 제출이 있는 박스만 불러오고, 응답이 늦게 와도 지금 선택한 박스일 때만 반영한다
const loadSubmission = async (boxId: string) => {
  if (!state.value?.submissions[boxId]) return
  try {
    const loaded = await adminApi.submission(runId, boxId)
    if (selectedBoxId.value === boxId) submission.value = loaded
  } catch (e) {
    // 실시간 갱신이 보고 있던 오류 표시를 지우지 않도록 guard를 거치지 않는다
    error.value = e instanceof ApiError ? e.message : '제출 코드를 불러오지 못했습니다.'
  }
}

const selectBox = (boxId: string) => {
  selectedBoxId.value = boxId
  submission.value = null
  markdownDraft.value = state.value?.graph.boxes.find((b) => b.id === boxId)?.config.markdown ?? ''
  // 제출 코드는 아래 watch가 선택이 바뀔 때 불러온다
}

// 선택이 바뀌거나 실시간으로 제출이 생기거나 다시 제출되면 상세를 불러온다
watch(
  () => (selectedBoxId.value ? state.value?.submissions[selectedBoxId.value]?.submitted_at : undefined),
  () => {
    if (selectedBoxId.value) loadSubmission(selectedBoxId.value)
  },
)

const saveMarkdown = () =>
  guard(async () => {
    if (!selectedBoxId.value) return
    await adminApi.patchBox(runId, selectedBoxId.value, markdownDraft.value)
    await refresh()
  })

onMounted(() => {
  guard(refresh)
  socket.start()
})
onBeforeUnmount(() => {
  socket.stop()
  refreshSoon.cancel()
})
</script>

<template>
  <main v-if="state" class="run-page">
    <header class="page-head">
      <RouterLink to="/admin">← 시험장 목록</RouterLink>
      <h1>{{ state.run.name }}</h1>
      <span class="tag">{{ STATUS_LABEL[state.run.status] }}</span>
      <span class="entry-code" title="입장 코드">{{ state.run.entry_code }}</span>
      <button type="button" @click="copyLink">{{ copied ? '복사했습니다' : '입장 링크 복사' }}</button>
      <button v-if="state.run.status === 'lobby'" class="primary" type="button" @click="start">회차 시작</button>
      <button v-if="state.run.status !== 'finished'" type="button" class="danger" @click="finish">회차 종료</button>
      <RouterLink class="button" :to="`/admin/runs/${runId}/result`">결과 보기</RouterLink>
    </header>
    <p v-if="error" class="error" role="alert">{{ error }}</p>

    <div class="run-grid">
      <aside class="people" aria-label="참가자">
        <h2>참가자 {{ state.participants.length }}명</h2>
        <ul class="warnings">
          <li v-for="w in warnings" :key="w">{{ w }}</li>
        </ul>
        <p v-if="state.participants.length === 0" class="muted">
          입장 코드 {{ state.run.entry_code }}로 참가자가 들어오면 여기에 나타납니다.
        </p>
        <div v-for="p in state.participants" :key="p.id" class="person">
          <div class="row spread">
            <span>
              <span class="dot" :class="p.online ? 'on' : 'off'" :title="p.online ? '접속 중' : '접속 끊김'" />
              {{ p.name }}
              <span v-if="p.is_leader" class="tag ok">팀장</span>
              <span v-if="p.typing" class="tag">작성 중</span>
            </span>
            <button type="button" class="danger small" @click="removePerson(p)">빼기</button>
          </div>
          <div class="row">
            <select
              :value="p.assigned_box_id ?? ''"
              :aria-label="`${p.name} 파트`"
              @change="assign(p, ($event.target as HTMLSelectElement).value)"
            >
              <option value="">미배정</option>
              <option
                v-for="b in personalBoxes"
                :key="b.id"
                :value="b.id"
                :disabled="!!ownerOf(b.id) && ownerOf(b.id)?.id !== p.id"
              >
                {{ b.title }}
              </option>
            </select>
            <button v-if="!p.is_leader" type="button" class="small" @click="makeLeader(p)">팀장 지정</button>
          </div>
          <button v-if="p.rejoin_requested" type="button" class="primary small" @click="approveRejoin(p)">
            재입장 승인
          </button>
        </div>
      </aside>

      <section class="flow" aria-label="진행 흐름">
        <div v-if="gates.length" class="gates">
          <button v-for="g in gates" :key="g.target" type="button" class="primary" @click="approveGate(g)">
            "{{ g.targetTitle }}" 열기 승인
            <span v-if="g.unsubmitted.length">(미제출 {{ g.unsubmitted.length }})</span>
          </button>
        </div>
        <VueFlow
          :nodes="nodes"
          :edges="edges"
          :nodes-draggable="false"
          :nodes-connectable="false"
          fit-view-on-init
          @node-click="({ node }) => selectBox(node.id)"
        >
          <template #node-box="props">
            <BoxNode :data="props.data" :selected="props.id === selectedBoxId" />
          </template>
          <Background />
        </VueFlow>
      </section>

      <aside v-if="selectedBox" class="detail" aria-label="박스 상세">
        <h2>{{ selectedBox.title }}</h2>
        <p class="muted">
          {{ BOX_TYPE_LABEL[selectedBox.type] }} 박스 · {{ BOX_STATE_LABEL[state.boxes[selectedBox.id]?.state ?? 'locked'] }}
        </p>
        <template v-if="selectedBox.type === 'personal'">
          <p>담당: {{ ownerOf(selectedBox.id)?.name ?? '미배정' }}</p>
          <template v-if="submission">
            <p class="muted">제출 시각 {{ new Date(submission.submitted_at).toLocaleTimeString('ko-KR') }}</p>
            <FileTabs :files="submission.files" readonly />
          </template>
          <p v-else class="muted">아직 제출한 코드가 없습니다.</p>
        </template>
        <template v-if="selectedBox.type === 'team'">
          <p>저장한 버전 {{ state.team_versions[selectedBox.id]?.length ?? 0 }}개</p>
          <RouterLink :to="`/admin/runs/${runId}/result`">버전과 최종 코드 보기</RouterLink>
        </template>
        <template v-if="selectedBox.type !== 'result'">
          <label>
            문제 수정 (참가자 화면에 바로 반영)
            <textarea v-model="markdownDraft" rows="8" />
          </label>
          <button type="button" @click="saveMarkdown">문제 저장</button>
        </template>
      </aside>
    </div>
  </main>
  <p v-else-if="error" class="error page" role="alert">{{ error }}</p>
</template>
