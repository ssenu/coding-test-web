<script setup lang="ts">
// 참가자 작업 화면: 대기실, 개인 문제 풀이와 제출, 팀 단계(팀장 편집 / 팀원 실시간 보기), 종료.
// 위쪽에 단계 줄, 아래는 왼쪽 문제 · 오른쪽 코드로 나눠 문제를 보면서 코드를 쓸 수 있게 한다.
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import AppIcon from '../../components/AppIcon.vue'
import FileTabs from '../../components/FileTabs.vue'
import MarkdownView from '../../components/MarkdownView.vue'
import { ApiError, clearParticipant, loadParticipant, participantApi } from '../../lib/api'
import { confirmDialog } from '../../lib/dialog'
import { BOX_STATE_LABEL, BOX_TYPE_LABEL } from '../../lib/graph'
import { RunSocket, type ServerEvent, runSocketUrl } from '../../lib/socket'
import { debounce, throttle } from '../../lib/timing'
import { toast } from '../../lib/toast'
import type { Files, ParticipantState, StoredFile } from '../../lib/types'
import { defaultBoxId, initialFiles, isWaiting, loadDraft, saveDraft } from '../../lib/workspace'

const TYPING_INTERVAL_MS = 5000
const TEAM_DRAFT_DELAY_MS = 500
const SPLIT_KEY = 'ctw.split'
const SPLIT_MIN = 25
const SPLIT_MAX = 70

const router = useRouter()
const stored = loadParticipant()

const st = ref<ParticipantState | null>(null)
const selectedId = ref<string | null>(null)
// 기본 박스가 바뀌면(시작, 팀 단계 열림 등) 그쪽으로 옮겨 준다. 그 외에는 참가자가 고른 박스를 유지한다.
let lastDefaultId: string | null = null
const personalFiles = ref<Files>({})
const personalBoxLoaded = ref<string | null>(null)
const teamFiles = ref<Record<string, Files>>({})
const error = ref('')
const busy = ref(false)
// null: 아직 한 번도 연결되지 않음
const connected = ref<boolean | null>(null)

const selected = computed(() => st.value?.boxes.find((b) => b.id === selectedId.value) ?? null)
const isMine = computed(() => selected.value?.type === 'personal' && selected.value.id === st.value?.me.assigned_box_id)
const canEditTeam = computed(
  () => selected.value?.type === 'team' && selected.value.state === 'open' && !!st.value?.me.is_leader,
)
const hasCode = computed(
  () => !!selected.value && selected.value.state !== 'locked' && (isMine.value || selected.value.type === 'team'),
)
// 마지막 제출본과 지금 편집기 내용이 다르면 다시 제출하라고 알려 준다
const changedSinceSubmit = computed(() => {
  const submitted = st.value?.my_submission?.files
  if (!submitted) return false
  return Object.entries(personalFiles.value).some(([name, code]) => submitted[name] !== code)
})

// 다른 박스로 옮기면 이전 박스의 오류는 지운다
watch(selectedId, () => {
  error.value = ''
})

const time = (iso: string) => new Date(iso).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })

async function leaveWaiting() {
  const ok = await confirmDialog({
    title: '대기실에서 나갈까요?',
    message: '같은 이름으로 다시 입장하려면 관리자 승인이 필요합니다.',
    confirmLabel: '나가기',
    danger: true,
  })
  if (ok) leave()
}

function leave() {
  clearParticipant()
  router.push('/')
}

async function load(): Promise<boolean> {
  try {
    const next = await participantApi.state()
    st.value = next
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 409)) {
      if (e.status === 401) clearParticipant()
      await router.push('/')
      return false
    }
    throw e
  }
  const s = st.value
  const nextDefault = defaultBoxId(s)
  if (nextDefault !== lastDefaultId || !s.boxes.some((b) => b.id === selectedId.value)) {
    selectedId.value = nextDefault
    lastDefaultId = nextDefault
  }

  const mine = s.boxes.find((b) => b.id === s.me.assigned_box_id)
  if (mine && mine.state !== 'locked' && personalBoxLoaded.value !== mine.id) {
    personalFiles.value = initialFiles(mine, s.my_submission?.files ?? null, loadDraft(s.run.id, mine.id))
    personalBoxLoaded.value = mine.id
  }
  for (const [boxId, team] of Object.entries(s.team)) {
    // 팀장이 편집 중인 팀 박스는 화면의 내용을 덮어쓰지 않는다
    const editing = s.me.is_leader && s.boxes.find((b) => b.id === boxId)?.state === 'open' && teamFiles.value[boxId]
    if (!editing) teamFiles.value = { ...teamFiles.value, [boxId]: team.files }
  }
  return true
}

const refreshSoon = debounce(() => {
  load().catch(() => undefined)
}, 200)

function onEvent(e: ServerEvent) {
  if (e.event === 'team_draft') {
    const boxId = String(e.data.box_id)
    if (!canEditTeam.value || selectedId.value !== boxId) {
      teamFiles.value = { ...teamFiles.value, [boxId]: e.data.files as Files }
    }
    return
  }
  if (e.event === 'participant_removed' && e.data.id === st.value?.me.id) {
    leave()
    return
  }
  refreshSoon()
}

const socket = stored
  ? new RunSocket(runSocketUrl(stored.runId, stored.token), {
      onOpen: () => refreshSoon(),
      onEvent,
      onAuthFailed: leave,
      onStatus: (up) => (connected.value = up),
    })
  : null

const sendTyping = throttle(() => socket?.send({ type: 'typing' }), TYPING_INTERVAL_MS)
const sendTeamDraft = debounce((boxId: string, files: Files) => {
  // 연결이 끊겨 있으면 REST로 초안을 저장한다
  if (!socket?.send({ type: 'team_draft', box_id: boxId, files })) {
    participantApi.saveDraft(boxId, files).catch(() => undefined)
  }
}, TEAM_DRAFT_DELAY_MS)

// ---------------------------------------------------------------- 개인 박스
function onPersonalChange(files: Files) {
  personalFiles.value = files
  if (st.value && selectedId.value) saveDraft(st.value.run.id, selectedId.value, files)
  sendTyping()
}

async function submitPersonal() {
  if (!selectedId.value) return
  busy.value = true
  error.value = ''
  try {
    await participantApi.submit(selectedId.value, personalFiles.value)
    toast('제출했습니다. 이 단계가 닫히기 전까지 다시 제출할 수 있습니다.')
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : '제출하지 못했습니다.'
  } finally {
    busy.value = false
  }
}

// ---------------------------------------------------------------- 팀 박스
function onTeamChange(files: Files) {
  if (!selectedId.value) return
  teamFiles.value = { ...teamFiles.value, [selectedId.value]: files }
  sendTeamDraft(selectedId.value, files)
  sendTyping()
}

async function saveVersion(final: boolean) {
  const boxId = selectedId.value
  if (!boxId) return
  if (final) {
    const ok = await confirmDialog({
      title: '최종 제출할까요?',
      message: '지금 코드가 팀의 최종 결과로 저장됩니다. 최종 제출하면 팀 단계가 끝날 수 있습니다.',
      confirmLabel: '최종 제출',
    })
    if (!ok) return
  }
  busy.value = true
  error.value = ''
  sendTeamDraft.cancel()
  try {
    const v = await participantApi.saveVersion(boxId, teamFiles.value[boxId] ?? {}, final)
    toast(final ? `버전 ${v.version_no}을 최종 제출했습니다.` : `버전 ${v.version_no}을 저장했습니다.`)
    await load()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : '저장하지 못했습니다.'
  } finally {
    busy.value = false
  }
}

const download = async (file: StoredFile) => {
  try {
    await participantApi.download(file.id, file.filename)
  } catch (e) {
    toast(e instanceof ApiError ? e.message : '파일을 받지 못했습니다.', 'error')
  }
}

// ---------------------------------------------------------------- 문제 · 코드 나눔선
const body = ref<HTMLElement>()
const split = ref(Number(localStorage.getItem(SPLIT_KEY)) || 44)
const dragging = ref(false)

function onSplitDown(event: PointerEvent) {
  dragging.value = true
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
}

function onSplitMove(event: PointerEvent) {
  if (!dragging.value || !body.value) return
  const rect = body.value.getBoundingClientRect()
  const percent = ((event.clientX - rect.left) / rect.width) * 100
  split.value = Math.round(Math.min(SPLIT_MAX, Math.max(SPLIT_MIN, percent)))
}

function onSplitUp() {
  dragging.value = false
  localStorage.setItem(SPLIT_KEY, String(split.value))
}

function onSplitKey(event: KeyboardEvent) {
  const step = event.key === 'ArrowLeft' ? -2 : event.key === 'ArrowRight' ? 2 : 0
  if (!step) return
  event.preventDefault()
  split.value = Math.min(SPLIT_MAX, Math.max(SPLIT_MIN, split.value + step))
  localStorage.setItem(SPLIT_KEY, String(split.value))
}

let unmounted = false

onMounted(async () => {
  if (!socket) {
    await router.push('/')
    return
  }
  const ok = await load().catch(() => {
    error.value = '화면을 불러오지 못했습니다.'
    return true
  })
  // 불러오는 중에 화면이 닫혔다면 소켓을 열지 않는다
  if (unmounted) return
  if (ok) socket.start()
})

onBeforeUnmount(() => {
  unmounted = true
  refreshSoon.cancel()
  sendTeamDraft.flush()
  socket?.stop()
})
</script>

<template>
  <main v-if="st" class="work-page">
    <header class="topbar">
      <h1>{{ st.run.name }}</h1>
      <nav v-if="st.run.status === 'running' && !isWaiting(st)" class="stages" aria-label="단계">
        <button
          v-for="b in st.boxes"
          :key="b.id"
          type="button"
          class="stage"
          :class="[`type-${b.type}`, `state-${b.state}`, { active: b.id === selectedId }]"
          :aria-current="b.id === selectedId ? 'step' : undefined"
          :title="`${BOX_TYPE_LABEL[b.type]} · ${BOX_STATE_LABEL[b.state]}`"
          @click="selectedId = b.id"
        >
          <span class="stage-mark">
            <AppIcon v-if="b.state === 'locked'" name="lock" />
            <AppIcon v-else-if="b.state === 'closed'" name="check" />
            <span v-else class="live-dot" />
          </span>
          {{ b.title }}
        </button>
      </nav>
      <span v-else class="grow" />
      <div class="me">
        <span class="dot" :class="{ on: connected }" :title="connected ? '실시간 연결됨' : '연결 끊김'" />
        {{ st.me.name }}
        <span v-if="st.me.is_leader" class="tag leader"><AppIcon name="crown" />팀장</span>
      </div>
    </header>
    <p v-if="connected === false" class="banner offline" role="status">
      <AppIcon name="alert" />서버와 연결이 끊겼습니다. 다시 연결하는 중입니다. 작성한 코드는 화면에 그대로 있습니다.
    </p>

    <div v-if="st.run.status === 'finished'" class="work-center">
      <section class="card wide">
        <h2>수고하셨습니다</h2>
        <p class="muted">회차가 끝났습니다. 팀이 최종 제출한 코드입니다.</p>
        <template v-for="(files, boxId) in st.result ?? {}" :key="boxId">
          <FileTabs :files="files" readonly />
        </template>
        <p v-if="!st.result || Object.keys(st.result).length === 0" class="muted">최종 제출된 코드가 없습니다.</p>
        <button type="button" @click="leave">다른 회차 입장</button>
      </section>
    </div>

    <div v-else-if="isWaiting(st)" class="work-center">
      <section class="card" role="status">
        <div class="waiting-mark" aria-hidden="true"><i /><i /><i /></div>
        <h2>곧 시작합니다</h2>
        <p class="muted">관리자가 파트를 배정하고 회차를 시작하면 이 화면에 문제가 열립니다. 창을 닫지 말고 기다려 주세요.</p>
        <button type="button" class="quiet" @click="leaveWaiting">대기실에서 나가기</button>
      </section>
    </div>

    <div
      v-else-if="selected"
      ref="body"
      class="work-body"
      :class="{ single: !hasCode }"
      :style="{ '--split': `${split}%` }"
    >
      <section class="pane problem" aria-label="문제">
        <div class="problem-inner">
          <div class="problem-title">
            <span class="type-chip" :class="`type-${selected.type}`">{{ BOX_TYPE_LABEL[selected.type] }}</span>
            <h2>{{ selected.title }}</h2>
          </div>

          <div v-if="selected.state === 'locked'" class="empty-state">
            <h2>아직 열리지 않은 단계입니다</h2>
            <p>앞 단계가 끝나고 관리자가 열면 문제가 보입니다.</p>
          </div>
          <template v-else>
            <MarkdownView v-if="selected.markdown" :source="selected.markdown" />
            <p v-else-if="selected.type !== 'result'" class="muted">문제 설명이 없습니다.</p>
            <ul v-if="selected.attachments?.length" class="attachments">
              <li v-for="f in selected.attachments" :key="f.id">
                <button type="button" class="small" @click="download(f)"><AppIcon name="download" />{{ f.filename }}</button>
              </li>
            </ul>
          </template>
        </div>
      </section>

      <template v-if="hasCode">
        <div
          class="splitter"
          :class="{ dragging }"
          role="separator"
          aria-orientation="vertical"
          aria-label="문제와 코드 영역 너비 조절"
          :aria-valuenow="split"
          :aria-valuemin="SPLIT_MIN"
          :aria-valuemax="SPLIT_MAX"
          tabindex="0"
          @pointerdown="onSplitDown"
          @pointermove="onSplitMove"
          @pointerup="onSplitUp"
          @keydown="onSplitKey"
        />

        <section v-if="isMine" class="pane code" aria-label="내 코드">
          <FileTabs
            fill
            :files="personalFiles"
            :readonly="selected.state !== 'open'"
            @update:files="onPersonalChange"
          />
          <div class="action-bar">
            <p v-if="error" class="error" role="alert">{{ error }}</p>
            <div class="status">
              <template v-if="selected.state === 'closed'">
                <AppIcon name="lock" />이 단계는 닫혔습니다.
                <span v-if="st.my_submission">{{ time(st.my_submission.submitted_at) }} 제출본이 넘어갔습니다.</span>
              </template>
              <template v-else-if="st.my_submission">
                <span v-if="changedSinceSubmit" class="tag warn">제출 뒤 고친 내용이 있습니다</span>
                <span v-else class="tag ok"><AppIcon name="check" />제출됨</span>
                마지막 제출 {{ time(st.my_submission.submitted_at) }}
              </template>
              <template v-else>아직 제출하지 않았습니다. 단계가 닫히기 전까지 여러 번 제출할 수 있습니다.</template>
            </div>
            <button
              v-if="selected.state === 'open'"
              class="primary"
              type="button"
              :disabled="busy"
              @click="submitPersonal"
            >
              {{ st.my_submission ? '다시 제출' : '제출' }}
            </button>
          </div>
        </section>

        <section v-else class="pane code" aria-label="팀 코드">
          <p v-if="!canEditTeam && selected.state === 'open'" class="code-note">
            <span class="tag live"><span class="live-dot" />실시간</span>
            팀장이 편집하는 코드가 그대로 보입니다.
          </p>
          <FileTabs fill :files="teamFiles[selected.id] ?? {}" :readonly="!canEditTeam" @update:files="onTeamChange" />
          <div v-if="canEditTeam || st.team[selected.id]?.final || error" class="action-bar">
            <p v-if="error" class="error" role="alert">{{ error }}</p>
            <div class="status">
              <span v-if="st.team[selected.id]?.final" class="tag ok">
                <AppIcon name="check" />버전 {{ st.team[selected.id]?.final?.version_no }} 최종 제출됨
              </span>
              <template v-else-if="canEditTeam">입력한 내용은 팀원 화면에 바로 보입니다.</template>
            </div>
            <template v-if="canEditTeam">
              <button type="button" :disabled="busy" @click="saveVersion(false)">버전 저장</button>
              <button class="primary" type="button" :disabled="busy" @click="saveVersion(true)">최종 제출</button>
            </template>
          </div>
        </section>
      </template>
    </div>
  </main>
  <p v-else-if="error" class="banner error" role="alert">{{ error }}</p>
</template>
