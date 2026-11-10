<script setup lang="ts">
// 회차 진행 화면: 참가자 배정, 흐름도(박스 상태), 승인, 제출 코드 보기, 문제 수정.
// 흐름도 위의 "다음 할 일" 줄이 지금 관리자가 할 일을 항상 한 가지로 알려 준다.
import { Background } from '@vue-flow/background'
import { VueFlow, useVueFlow } from '@vue-flow/core'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import AppIcon from '../../components/AppIcon.vue'
import BoxNode from '../../components/BoxNode.vue'
import FileTabs from '../../components/FileTabs.vue'
import { ApiError, adminApi } from '../../lib/api'
import { confirmDialog } from '../../lib/dialog'
import { BOX_STATE_LABEL, BOX_TYPE_LABEL, autoLayout, needsLayout, toFlowEdges, toFlowNodes } from '../../lib/graph'
import {
  assignmentWarnings,
  boxBadges,
  boxStates,
  type Gate,
  isTyping,
  pendingGates,
  submitProgress,
  teamsWithoutFinal,
} from '../../lib/run'
import { RunSocket, runSocketUrl } from '../../lib/socket'
import { debounce } from '../../lib/timing'
import { toast } from '../../lib/toast'
import type { AdminState, ParticipantInfo, Submission } from '../../lib/types'

const STATUS_LABEL = { lobby: '대기실', running: '진행 중', finished: '종료' } as const
const STATUS_CLASS = { lobby: 'warn', running: 'live', finished: '' } as const
const CLOCK_MS = 5000

const route = useRoute()
const runId = Number(route.params.id)
const { fitView } = useVueFlow()

const state = ref<AdminState | null>(null)
const error = ref('')
const selectedBoxId = ref<string | null>(null)
const submission = ref<Submission | null>(null)
const markdownDraft = ref('')
const detailTab = ref<'code' | 'problem'>('code')
const connected = ref<boolean | null>(null)
// "작성 중" 표시가 스스로 꺼지도록 화면의 시계를 주기적으로 갱신한다
const now = ref(Date.now())
const clock = setInterval(() => (now.value = Date.now()), CLOCK_MS)

const personalBoxes = computed(() => state.value?.graph.boxes.filter((b) => b.type === 'personal') ?? [])
const gates = computed(() => (state.value ? pendingGates(state.value) : []))
const warnings = computed(() => (state.value ? assignmentWarnings(state.value) : []))
const progress = computed(() => (state.value ? submitProgress(state.value) : { done: 0, total: 0 }))
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
const markdownChanged = computed(() => markdownDraft.value !== (selectedBox.value?.config.markdown ?? ''))

const time = (iso: string) => new Date(iso).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })

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
  onStatus: (up) => (connected.value = up),
})

// ---------------------------------------------------------------- 회차
const start = () =>
  guard(async () => {
    if (warnings.value.length) {
      const ok = await confirmDialog({
        title: '이대로 시작할까요?',
        message: warnings.value.join(' '),
        confirmLabel: '회차 시작',
      })
      if (!ok) return
    }
    state.value = await adminApi.startRun(runId)
  })

const finish = () =>
  guard(async () => {
    const ok = await confirmDialog({
      title: '회차를 종료할까요?',
      message: '참가자는 더 이상 제출할 수 없습니다. 되돌릴 수 없습니다.',
      confirmLabel: '회차 종료',
      danger: true,
    })
    if (!ok) return
    state.value = await adminApi.finishRun(runId)
  })

async function copy(text: string, message: string) {
  try {
    await navigator.clipboard.writeText(text)
    toast(message)
  } catch {
    toast('복사하지 못했습니다. 직접 선택해 복사하세요.', 'error')
  }
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
    toast(`${p.name}님을 팀장으로 지정했습니다.`)
  })

const approveRejoin = (p: ParticipantInfo) =>
  guard(async () => {
    await adminApi.approveRejoin(runId, p.id)
    await refresh()
  })

const removePerson = (p: ParticipantInfo) =>
  guard(async () => {
    const ok = await confirmDialog({
      title: `${p.name}님을 회차에서 뺄까요?`,
      message: '이 참가자의 화면은 입장 화면으로 돌아갑니다.',
      confirmLabel: '참가자 빼기',
      danger: true,
    })
    if (!ok) return
    await adminApi.removeParticipant(runId, p.id)
    await refresh()
  })

function ownerOf(boxId: string) {
  return state.value?.participants.find((p) => p.assigned_box_id === boxId) ?? null
}

// ---------------------------------------------------------------- 승인
const approveGate = (gate: Gate) =>
  guard(async () => {
    const pendingTeams = state.value ? teamsWithoutFinal(state.value, gate) : []
    if (pendingTeams.length) {
      const ok = await confirmDialog({
        title: '팀이 아직 최종 제출하지 않았습니다',
        message: `"${pendingTeams.join(', ')}" 단계가 최종 제출 없이 닫힙니다. 닫힌 뒤에는 팀장이 더 제출할 수 없습니다.`,
        confirmLabel: '그래도 승인',
        danger: true,
      })
      if (!ok) return
    }
    try {
      state.value = await adminApi.approve(runId, gate.edgeIds, false)
    } catch (e) {
      const detail = e instanceof ApiError ? (e.detail as { code?: string; message?: string }) : null
      if (detail?.code !== 'unsubmitted') throw e
      const ok = await confirmDialog({
        title: '제출하지 않은 파트가 있습니다',
        message: `${detail.message} 지금 승인하면 그 파트는 시작 코드로 넘어가고, 더 이상 제출할 수 없습니다.`,
        confirmLabel: '그래도 승인',
        danger: true,
      })
      if (!ok) return
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

const selectBox = (boxId: string | null) => {
  selectedBoxId.value = boxId
  submission.value = null
  const box = state.value?.graph.boxes.find((b) => b.id === boxId)
  markdownDraft.value = box?.config.markdown ?? ''
  detailTab.value = box?.type === 'personal' ? 'code' : 'problem'
  // 제출 코드는 아래 watch가 선택이 바뀔 때 불러온다
}

// 선택이 바뀌거나 실시간으로 제출이 생기거나 다시 제출되면 상세를 불러온다
watch(
  () => (selectedBoxId.value ? state.value?.submissions[selectedBoxId.value]?.submitted_at : undefined),
  () => {
    if (selectedBoxId.value) loadSubmission(selectedBoxId.value)
  },
)

// 상세 패널이 열리고 닫히면 흐름도 너비가 바뀌므로 다시 화면에 맞춘다
watch(
  () => selectedBoxId.value !== null,
  async () => {
    await nextTick()
    // Vue Flow가 바뀐 캔버스 크기를 잰 뒤에 맞춘다
    setTimeout(() => fitView({ padding: 0.1, duration: 250 }), 80)
  },
)

const saveMarkdown = () =>
  guard(async () => {
    if (!selectedBoxId.value) return
    await adminApi.patchBox(runId, selectedBoxId.value, markdownDraft.value)
    await refresh()
    toast('문제를 저장했습니다. 참가자 화면에 반영됐습니다.')
  })

onMounted(() => {
  guard(refresh)
  socket.start()
})
onBeforeUnmount(() => {
  clearInterval(clock)
  socket.stop()
  refreshSoon.cancel()
})
</script>

<template>
  <main v-if="state" class="run-page">
    <header class="topbar">
      <RouterLink to="/admin" class="button quiet back" aria-label="시험장 목록으로"><AppIcon name="arrow-left" /></RouterLink>
      <h1>{{ state.run.name }}</h1>
      <span class="tag" :class="STATUS_CLASS[state.run.status]">
        <span v-if="state.run.status === 'running'" class="live-dot" />{{ STATUS_LABEL[state.run.status] }}
      </span>
      <span class="grow" />
      <template v-if="state.run.status !== 'finished'">
        <span class="muted" style="font-size: 0.85rem">입장 코드</span>
        <button
          type="button"
          class="entry-code"
          title="입장 코드 복사"
          @click="copy(state.run.entry_code, '입장 코드를 복사했습니다.')"
        >
          {{ state.run.entry_code }}<AppIcon name="copy" />
        </button>
        <button type="button" @click="copy(joinLink, '입장 링크를 복사했습니다.')"><AppIcon name="link" />링크 복사</button>
        <span class="divider" />
      </template>
      <RouterLink class="button" :to="`/admin/runs/${runId}/result`"><AppIcon name="chart" />결과</RouterLink>
      <button v-if="state.run.status !== 'finished'" type="button" class="danger" @click="finish">회차 종료</button>
    </header>
    <p v-if="error" class="banner error" role="alert"><AppIcon name="alert" />{{ error }}</p>
    <p v-else-if="connected === false" class="banner offline" role="status">
      <AppIcon name="alert" />서버와 연결이 끊겼습니다. 다시 연결하는 중이며, 그동안 화면이 최신이 아닐 수 있습니다.
    </p>

    <div class="run-grid" :class="{ 'has-detail': selectedBox }">
      <aside class="people" aria-label="참가자">
        <h2>참가자 {{ state.participants.length }}명</h2>
        <ul v-if="warnings.length" class="callouts">
          <li v-for="w in warnings" :key="w"><AppIcon name="alert" />{{ w }}</li>
        </ul>
        <p v-if="state.participants.length === 0" class="muted">
          입장 코드나 링크를 참가자에게 알려 주세요. 들어오면 여기에 나타납니다.
        </p>
        <div v-for="p in state.participants" :key="p.id" class="person" :class="{ rejoin: p.rejoin_requested }">
          <div class="row spread">
            <span class="person-name">
              <span class="dot" :class="{ on: p.online }" :title="p.online ? '접속 중' : '접속 끊김'" />
              {{ p.name }}
              <span v-if="p.is_leader" class="tag leader"><AppIcon name="crown" />팀장</span>
              <span v-if="isTyping(p, now)" class="tag live">작성 중</span>
              <span v-else-if="!p.online" class="muted" style="font-size: 0.78rem">접속 끊김</span>
            </span>
            <span class="row" style="gap: 0.1rem">
              <button
                v-if="!p.is_leader"
                type="button"
                class="icon-button"
                :aria-label="`${p.name} 팀장 지정`"
                title="팀장으로 지정"
                @click="makeLeader(p)"
              >
                <AppIcon name="crown" />
              </button>
              <button
                type="button"
                class="icon-button danger"
                :aria-label="`${p.name} 빼기`"
                title="회차에서 빼기"
                @click="removePerson(p)"
              >
                <AppIcon name="x" />
              </button>
            </span>
          </div>
          <select
            :value="p.assigned_box_id ?? ''"
            :aria-label="`${p.name} 파트`"
            @change="assign(p, ($event.target as HTMLSelectElement).value)"
          >
            <option value="">파트 미배정</option>
            <option
              v-for="b in personalBoxes"
              :key="b.id"
              :value="b.id"
              :disabled="!!ownerOf(b.id) && ownerOf(b.id)?.id !== p.id"
            >
              {{ b.title }}{{ ownerOf(b.id) && ownerOf(b.id)?.id !== p.id ? ` (${ownerOf(b.id)?.name})` : '' }}
            </option>
          </select>
          <div v-if="p.rejoin_requested" class="row spread">
            <span style="font-size: 0.82rem; color: var(--warn)">다른 기기에서 재입장을 요청했습니다</span>
            <button type="button" class="primary small" @click="approveRejoin(p)">재입장 승인</button>
          </div>
        </div>
      </aside>

      <section class="flow" aria-label="진행 흐름">
        <div class="next-step" role="status">
          <template v-if="state.run.status === 'lobby'">
            <p>참가자 배정이 끝나면 시작하세요. 시작하면 첫 박스가 열립니다.</p>
            <button class="primary" type="button" @click="start"><AppIcon name="play" />회차 시작</button>
          </template>
          <template v-else-if="state.run.status === 'finished'">
            <p><strong>회차가 끝났습니다.</strong></p>
            <RouterLink class="button primary" :to="`/admin/runs/${runId}/result`">결과 보기</RouterLink>
          </template>
          <template v-else-if="gates.length">
            <p>
              제출 <strong>{{ progress.done }}/{{ progress.total }}</strong>
            </p>
            <button v-for="g in gates" :key="g.target" type="button" class="primary" @click="approveGate(g)">
              "{{ g.targetTitle }}" 열기
              <span v-if="g.unsubmitted.length">· 미제출 {{ g.unsubmitted.length }}</span>
              <span v-else-if="teamsWithoutFinal(state, g).length">· 최종 제출 전</span>
            </button>
          </template>
          <p v-else>
            제출 <strong>{{ progress.done }}/{{ progress.total }}</strong> · 지금 승인할 단계가 없습니다.
          </p>
        </div>
        <VueFlow
          :nodes="nodes"
          :edges="edges"
          :nodes-draggable="false"
          :nodes-connectable="false"
          :fit-view-on-init="true"
          @node-click="({ node }) => selectBox(node.id)"
          @pane-click="selectBox(null)"
        >
          <template #node-box="props">
            <BoxNode :data="props.data" :selected="props.id === selectedBoxId" />
          </template>
          <Background :gap="22" pattern-color="#d5d9e0" />
        </VueFlow>
      </section>

      <aside v-if="selectedBox" class="detail" aria-label="박스 상세">
        <div class="detail-head">
          <div class="grow">
            <span class="type-chip" :class="`type-${selectedBox.type}`">{{ BOX_TYPE_LABEL[selectedBox.type] }}</span>
            <h2>{{ selectedBox.title }}</h2>
            <p class="muted">
              {{ BOX_STATE_LABEL[state.boxes[selectedBox.id]?.state ?? 'locked'] }}
              <template v-if="selectedBox.type === 'personal'">
                · 담당 {{ ownerOf(selectedBox.id)?.name ?? '미배정' }}
                <template v-if="submission"> · {{ time(submission.submitted_at) }} 제출</template>
              </template>
              <template v-if="selectedBox.type === 'team'">
                · 저장한 버전 {{ state.team_versions[selectedBox.id]?.length ?? 0 }}개
              </template>
            </p>
          </div>
          <button type="button" class="icon-button" aria-label="상세 닫기" @click="selectBox(null)">
            <AppIcon name="x" />
          </button>
        </div>

        <div v-if="selectedBox.type === 'personal'" class="detail-tabs">
          <div class="segmented" role="tablist">
            <button
              type="button"
              role="tab"
              :aria-selected="detailTab === 'code'"
              :class="{ active: detailTab === 'code' }"
              @click="detailTab = 'code'"
            >
              제출 코드
            </button>
            <button
              type="button"
              role="tab"
              :aria-selected="detailTab === 'problem'"
              :class="{ active: detailTab === 'problem' }"
              @click="detailTab = 'problem'"
            >
              문제 수정
            </button>
          </div>
        </div>

        <div class="detail-body">
          <template v-if="selectedBox.type === 'personal' && detailTab === 'code'">
            <FileTabs v-if="submission" :files="submission.files" readonly />
            <div v-else class="empty-state">
              <h2>아직 제출한 코드가 없습니다</h2>
              <p>참가자가 제출하면 여기에 바로 나타납니다.</p>
            </div>
          </template>
          <template v-else-if="selectedBox.type === 'result'">
            <div class="empty-state">
              <h2>결과 박스</h2>
              <p>이 박스가 열리면 회차가 끝나고, 참가자에게 팀의 최종 코드가 보입니다.</p>
              <RouterLink class="button" :to="`/admin/runs/${runId}/result`">버전과 최종 코드 보기</RouterLink>
            </div>
          </template>
          <template v-else>
            <RouterLink v-if="selectedBox.type === 'team'" class="button" :to="`/admin/runs/${runId}/result`">
              <AppIcon name="chart" />버전과 최종 코드 보기
            </RouterLink>
            <label class="grow" style="display: flex; margin: 0">
              문제 (마크다운) · 저장하면 참가자 화면에 바로 반영됩니다
              <textarea v-model="markdownDraft" spellcheck="false" />
            </label>
            <div class="row" style="justify-content: flex-end">
              <button type="button" class="primary" :disabled="!markdownChanged" @click="saveMarkdown">문제 저장</button>
            </div>
          </template>
        </div>
      </aside>
    </div>
  </main>
  <p v-else-if="error" class="banner error" role="alert">{{ error }}</p>
</template>
