<script setup lang="ts">
// 참가자 작업 화면: 대기실, 개인 문제 풀이와 제출, 팀 단계(팀장 편집 / 팀원 실시간 보기), 종료.
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import FileTabs from '../../components/FileTabs.vue'
import MarkdownView from '../../components/MarkdownView.vue'
import { ApiError, clearParticipant, loadParticipant, participantApi } from '../../lib/api'
import { BOX_STATE_LABEL, BOX_TYPE_LABEL } from '../../lib/graph'
import { RunSocket, type ServerEvent, runSocketUrl } from '../../lib/socket'
import { debounce, throttle } from '../../lib/timing'
import type { Files, ParticipantState, StoredFile } from '../../lib/types'
import { defaultBoxId, initialFiles, isWaiting, loadDraft, saveDraft } from '../../lib/workspace'

const TYPING_INTERVAL_MS = 5000
const TEAM_DRAFT_DELAY_MS = 500

const router = useRouter()
const stored = loadParticipant()

const st = ref<ParticipantState | null>(null)
const selectedId = ref<string | null>(null)
// 기본 박스가 바뀌면(시작, 팀 단계 열림 등) 그쪽으로 옮겨 준다. 그 외에는 참가자가 고른 박스를 유지한다.
let lastDefaultId: string | null = null
const personalFiles = ref<Files>({})
const personalBoxLoaded = ref<string | null>(null)
const teamFiles = ref<Record<string, Files>>({})
const notice = ref('')
const error = ref('')
const busy = ref(false)

const selected = computed(() => st.value?.boxes.find((b) => b.id === selectedId.value) ?? null)
const isMine = computed(() => selected.value?.type === 'personal' && selected.value.id === st.value?.me.assigned_box_id)
const canEditTeam = computed(
  () => selected.value?.type === 'team' && selected.value.state === 'open' && !!st.value?.me.is_leader,
)

// 다른 박스로 옮기면 이전 박스의 안내와 오류는 지운다
watch(selectedId, () => {
  notice.value = ''
  error.value = ''
})

function leave() {
  clearParticipant()
  router.push('/')
}

async function load() {
  try {
    const next = await participantApi.state()
    st.value = next
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 409)) {
      if (e.status === 401) clearParticipant()
      await router.push('/')
      return
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
    })
  : null

const sendTyping = throttle(() => socket?.send({ type: 'typing' }), TYPING_INTERVAL_MS)
const sendTeamDraft = debounce((boxId: string, files: Files) => {
  socket?.send({ type: 'team_draft', box_id: boxId, files })
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
    const res = await participantApi.submit(selectedId.value, personalFiles.value)
    notice.value = `${new Date(res.submitted_at).toLocaleTimeString('ko-KR')}에 제출했습니다. 이 단계가 닫히기 전까지 다시 제출할 수 있습니다.`
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
  if (final && !window.confirm('최종 제출할까요? 최종 제출하면 팀 단계가 끝날 수 있습니다.')) return
  busy.value = true
  error.value = ''
  sendTeamDraft.cancel()
  try {
    const v = await participantApi.saveVersion(boxId, teamFiles.value[boxId] ?? {}, final)
    notice.value = final ? `버전 ${v.version_no}을 최종 제출했습니다.` : `버전 ${v.version_no}을 저장했습니다.`
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
    error.value = e instanceof ApiError ? e.message : '파일을 받지 못했습니다.'
  }
}

onMounted(async () => {
  if (!socket) {
    await router.push('/')
    return
  }
  await load().catch(() => (error.value = '화면을 불러오지 못했습니다.'))
  socket.start()
})

onBeforeUnmount(() => {
  socket?.stop()
  refreshSoon.cancel()
  sendTeamDraft.flush()
})
</script>

<template>
  <main v-if="st" class="work-page">
    <header class="page-head">
      <h1>{{ st.run.name }}</h1>
      <span class="muted">{{ st.me.name }}<template v-if="st.me.is_leader"> · 팀장</template></span>
    </header>

    <section v-if="st.run.status === 'finished'" class="card">
      <h2>수고하셨습니다</h2>
      <p>회차가 끝났습니다. 팀이 최종 제출한 코드입니다.</p>
      <template v-for="(files, boxId) in st.result ?? {}" :key="boxId">
        <FileTabs :files="files" readonly />
      </template>
      <p v-if="!st.result || Object.keys(st.result).length === 0" class="muted">최종 제출된 코드가 없습니다.</p>
    </section>

    <section v-else-if="isWaiting(st)" class="card" role="status">
      <h2>잠시 기다려 주세요</h2>
      <p>관리자가 파트를 배정하고 회차를 시작하면 문제가 열립니다.</p>
    </section>

    <div v-else class="work-grid">
      <nav class="box-list" aria-label="내 박스">
        <button
          v-for="b in st.boxes"
          :key="b.id"
          type="button"
          :class="[`state-${b.state}`, { active: b.id === selectedId }]"
          @click="selectedId = b.id"
        >
          <span class="box-type">{{ BOX_TYPE_LABEL[b.type] }}</span>
          {{ b.title }}
          <span class="box-state">{{ BOX_STATE_LABEL[b.state] }}</span>
        </button>
      </nav>

      <section v-if="selected" class="box-detail">
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <p v-if="notice" class="notice" role="status">{{ notice }}</p>

        <template v-if="selected.state === 'locked'">
          <h2>{{ selected.title }}</h2>
          <p class="muted">아직 열리지 않은 단계입니다.</p>
        </template>

        <template v-else>
          <h2>{{ selected.title }}</h2>
          <MarkdownView v-if="selected.markdown" :source="selected.markdown" />
          <ul v-if="selected.attachments?.length" class="attachments">
            <li v-for="f in selected.attachments" :key="f.id">
              <button type="button" class="link" @click="download(f)">{{ f.filename }} 내려받기</button>
            </li>
          </ul>

          <template v-if="isMine">
            <FileTabs
              :files="personalFiles"
              :readonly="selected.state !== 'open'"
              @update:files="onPersonalChange"
            />
            <div class="row">
              <button
                v-if="selected.state === 'open'"
                class="primary"
                type="button"
                :disabled="busy"
                @click="submitPersonal"
              >
                제출
              </button>
              <span v-if="st.my_submission" class="muted">
                마지막 제출 {{ new Date(st.my_submission.submitted_at).toLocaleTimeString('ko-KR') }}
              </span>
              <span v-if="selected.state === 'closed'" class="muted">이 단계는 닫혔습니다.</span>
            </div>
          </template>

          <template v-if="selected.type === 'team'">
            <p v-if="!canEditTeam && selected.state === 'open'" class="muted">
              팀장이 편집하는 코드가 실시간으로 보입니다.
            </p>
            <FileTabs
              :files="teamFiles[selected.id] ?? {}"
              :readonly="!canEditTeam"
              @update:files="onTeamChange"
            />
            <div v-if="canEditTeam" class="row">
              <button type="button" :disabled="busy" @click="saveVersion(false)">버전 저장</button>
              <button class="primary" type="button" :disabled="busy" @click="saveVersion(true)">최종 제출</button>
              <span v-if="st.team[selected.id]?.final" class="muted">
                최종 제출: 버전 {{ st.team[selected.id]?.final?.version_no }}
              </span>
            </div>
          </template>
        </template>
      </section>
    </div>
  </main>
  <p v-else-if="error" class="error page" role="alert">{{ error }}</p>
</template>
