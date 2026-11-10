<script setup lang="ts">
// 시험장 에디터: 왼쪽 박스 팔레트, 가운데 캔버스, 오른쪽 속성 패널(문제 · 코드 파일 · 첨부).
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import {
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
  VueFlow,
  useVueFlow,
} from '@vue-flow/core'
import { type Ref, computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import AppIcon from '../../components/AppIcon.vue'
import BoxNode from '../../components/BoxNode.vue'
import CodeEditor from '../../components/CodeEditor.vue'
import MarkdownView from '../../components/MarkdownView.vue'
import { ApiError, adminApi } from '../../lib/api'
import { confirmDialog, promptDialog } from '../../lib/dialog'
import {
  BOX_TYPE_LABEL,
  type BoxNodeData,
  autoLayout,
  fromFlow,
  hasEditor,
  needsLayout,
  newBox,
  newEdge,
  toFlowEdge,
  toFlowEdges,
  toFlowNodes,
} from '../../lib/graph'
import { toast } from '../../lib/toast'
import type { BoxData, BoxType, EdgeMode, Issue, StoredFile } from '../../lib/types'

const PALETTE: { type: BoxType; hint: string }[] = [
  { type: 'common', hint: '모두에게 보이는 안내' },
  { type: 'personal', hint: '한 사람이 맡아 제출하는 파트' },
  { type: 'team', hint: '팀장이 합쳐서 최종 제출' },
  { type: 'result', hint: '여기가 열리면 회차 종료' },
]
const DRAG_TYPE = 'application/x-box-type'
type PropsTab = 'problem' | 'code' | 'files'

const route = useRoute()
const router = useRouter()
const templateId = Number(route.params.id)

const name = ref('')
const description = ref('')
// Vue Flow 타입은 매우 깊어서 ref<T>의 UnwrapRef 추론이 터진다. Ref<T>로 직접 지정한다.
const nodes = ref([]) as Ref<Node<BoxNodeData>[]>
const edges = ref([]) as Ref<Edge[]>
const issues = ref<Issue[]>([])
const valid = ref(false)
const attachments = ref<StoredFile[]>([])
const selectedNodeId = ref<string | null>(null)
const selectedEdgeId = ref<string | null>(null)
const newFileName = ref('')
const dirty = ref(false)
const error = ref('')
const tab = ref<PropsTab>('problem')
const preview = ref(false)

const { screenToFlowCoordinate, onConnect } = useVueFlow()

const selectedBox = computed<BoxData | null>(
  () => nodes.value.find((n) => n.id === selectedNodeId.value)?.data?.box ?? null,
)
const selectedEdge = computed(() => edges.value.find((e) => e.id === selectedEdgeId.value) ?? null)
const selectedAttachments = computed(() => attachments.value.filter((f) => f.box_id === selectedNodeId.value))
const tabs = computed<{ id: PropsTab; label: string }[]>(() => {
  const box = selectedBox.value
  if (!box || box.type === 'result') return []
  const list: { id: PropsTab; label: string }[] = [{ id: 'problem', label: '문제' }]
  if (hasEditor(box.type)) list.push({ id: 'code', label: `코드 파일 ${box.config.editor.files.length}` })
  list.push({ id: 'files', label: `첨부 ${selectedAttachments.value.length}` })
  return list
})

function boxTitle(id: string): string {
  return nodes.value.find((n) => n.id === id)?.data?.box.title ?? id
}

function markDirty() {
  dirty.value = true
}

function showIssues(list: Issue[], isValid: boolean) {
  issues.value = list
  valid.value = isValid
  const bad = new Set(list.flatMap((i) => i.box_ids))
  for (const node of nodes.value) {
    if (node.data) node.data = { ...node.data, invalid: bad.has(node.id) }
  }
}

async function load() {
  const t = await adminApi.getTemplate(templateId)
  name.value = t.name
  description.value = t.description
  const graph = needsLayout(t.graph) ? autoLayout(t.graph) : t.graph
  nodes.value = toFlowNodes(graph)
  edges.value = toFlowEdges(graph)
  showIssues(t.issues, t.valid)
  attachments.value = await adminApi.listTemplateFiles(templateId)
  dirty.value = false
}

async function guard(action: () => Promise<unknown>) {
  error.value = ''
  try {
    await action()
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : '요청을 처리하지 못했습니다.'
  }
}

// ---------------------------------------------------------------- 박스와 선
function select(nodeId: string | null, edgeId: string | null = null) {
  if (nodeId !== selectedNodeId.value) {
    tab.value = 'problem'
    preview.value = false
  }
  selectedNodeId.value = nodeId
  selectedEdgeId.value = edgeId
}

function addBox(type: BoxType, position?: { x: number; y: number }) {
  const at = position ?? { x: 80 + nodes.value.length * 40, y: 80 + nodes.value.length * 30 }
  const box = newBox(type, nodes.value.map((n) => n.id), at)
  nodes.value = [...nodes.value, ...toFlowNodes({ boxes: [box], edges: [] })]
  select(box.id)
  markDirty()
}

function onDragStart(event: DragEvent, type: BoxType) {
  event.dataTransfer?.setData(DRAG_TYPE, type)
  if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move'
}

function onDrop(event: DragEvent) {
  const type = event.dataTransfer?.getData(DRAG_TYPE) as BoxType | undefined
  if (!type) return
  addBox(type, screenToFlowCoordinate({ x: event.clientX, y: event.clientY }))
}

onConnect((c: Connection) => {
  if (c.source === c.target) return
  if (edges.value.some((e) => e.source === c.source && e.target === c.target)) return
  const edge = newEdge(c.source, c.target, edges.value.map((e) => e.id))
  edges.value = [...edges.value, toFlowEdge(edge)]
  select(null, edge.id)
  markDirty()
})

function setEdgeMode(mode: EdgeMode) {
  const e = selectedEdge.value
  if (!e) return
  const updated = toFlowEdge({ id: e.id, source: e.source, target: e.target, mode })
  edges.value = edges.value.map((x) => (x.id === e.id ? updated : x))
  markDirty()
}

function removeSelected() {
  if (selectedNodeId.value) {
    const id = selectedNodeId.value
    nodes.value = nodes.value.filter((n) => n.id !== id)
    edges.value = edges.value.filter((e) => e.source !== id && e.target !== id)
  } else if (selectedEdgeId.value) {
    edges.value = edges.value.filter((e) => e.id !== selectedEdgeId.value)
  }
  select(null)
  markDirty()
}

function onNodesChange(changes: NodeChange[]) {
  if (changes.some((c) => c.type === 'remove')) markDirty()
}

function onEdgesChange(changes: EdgeChange[]) {
  if (changes.some((c) => c.type === 'remove')) markDirty()
}

// ---------------------------------------------------------------- 코드 파일
function addEditorFile() {
  const box = selectedBox.value
  const fileName = newFileName.value.trim()
  if (!box || !fileName) return
  if (box.config.editor.files.some((f) => f.name === fileName)) {
    toast(`${fileName} 파일이 이미 있습니다.`, 'error')
    return
  }
  box.config.editor.files.push({ name: fileName, starter: '' })
  newFileName.value = ''
  markDirty()
}

function removeEditorFile(index: number) {
  selectedBox.value?.config.editor.files.splice(index, 1)
  markDirty()
}

// ---------------------------------------------------------------- 첨부 파일
const upload = (event: Event) =>
  guard(async () => {
    const input = event.target as HTMLInputElement
    const file = input.files?.[0]
    if (!file || !selectedNodeId.value) return
    await adminApi.uploadTemplateFile(templateId, selectedNodeId.value, file)
    input.value = ''
    attachments.value = await adminApi.listTemplateFiles(templateId)
  })

const removeAttachment = (file: StoredFile) =>
  guard(async () => {
    await adminApi.deleteTemplateFile(templateId, file.id)
    attachments.value = await adminApi.listTemplateFiles(templateId)
  })

// ---------------------------------------------------------------- 저장과 회차
const save = () =>
  guard(async () => {
    const t = await adminApi.saveTemplate(templateId, {
      name: name.value,
      description: description.value,
      graph: fromFlow(nodes.value, edges.value),
    })
    showIssues(t.issues, t.valid)
    dirty.value = false
    if (t.valid) toast('저장했습니다. 회차를 열 수 있습니다.')
    else toast('저장했습니다. 위에 표시된 문제를 고쳐야 회차를 열 수 있습니다.', 'error')
  })

const openRun = () =>
  guard(async () => {
    const runName = await promptDialog({
      title: '새 회차 열기',
      message: '저장된 시험장을 그대로 복사해 회차를 만듭니다.',
      inputLabel: '회차 이름',
      value: `${new Date().toLocaleDateString('ko-KR')} 회차`,
      confirmLabel: '회차 열기',
    })
    if (!runName) return
    const run = await adminApi.createRun(templateId, runName)
    await router.push(`/admin/runs/${run.id}`)
  })

// ---------------------------------------------------------------- 저장하지 않고 나가기 방지, 단축키
function onKeydown(event: KeyboardEvent) {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
    event.preventDefault()
    save()
  }
}

function onBeforeUnload(event: BeforeUnloadEvent) {
  if (dirty.value) event.preventDefault()
}

onBeforeRouteLeave(async () => {
  if (!dirty.value) return true
  return confirmDialog({
    title: '저장하지 않고 나갈까요?',
    message: '저장하지 않은 변경은 사라집니다.',
    confirmLabel: '저장하지 않고 나가기',
    danger: true,
  })
})

onMounted(() => {
  guard(load)
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('beforeunload', onBeforeUnload)
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('beforeunload', onBeforeUnload)
})
</script>

<template>
  <main class="editor-page">
    <header class="topbar">
      <RouterLink to="/admin" class="button quiet back" aria-label="시험장 목록으로"><AppIcon name="arrow-left" /></RouterLink>
      <input v-model="name" class="title-input" aria-label="시험장 이름" maxlength="100" @input="markDirty" />
      <span v-if="dirty" class="tag warn">저장하지 않은 변경</span>
      <span v-else-if="valid" class="tag ok"><AppIcon name="check" />회차를 열 수 있음</span>
      <span class="grow" />
      <button
        type="button"
        :disabled="!valid || dirty"
        :title="dirty ? '먼저 저장하세요' : valid ? '' : '검사를 통과해야 회차를 열 수 있습니다'"
        @click="openRun"
      >
        <AppIcon name="play" />새 회차 열기
      </button>
      <button class="primary" type="button" title="Ctrl+S" @click="save">저장</button>
    </header>
    <p v-if="error" class="banner error" role="alert"><AppIcon name="alert" />{{ error }}</p>
    <ul v-if="issues.length" class="issues" aria-label="고쳐야 할 문제">
      <li v-for="(issue, i) in issues" :key="i">
        <AppIcon name="alert" />
        {{ issue.message }}
        <button v-for="id in issue.box_ids" :key="id" type="button" @click="select(id)">{{ boxTitle(id) }}</button>
      </li>
    </ul>

    <div class="editor-grid">
      <aside class="palette" aria-label="박스 종류">
        <h2>박스 추가</h2>
        <button
          v-for="item in PALETTE"
          :key="item.type"
          type="button"
          draggable="true"
          :class="`palette-item type-${item.type}`"
          @dragstart="onDragStart($event, item.type)"
          @click="addBox(item.type)"
        >
          <strong>{{ BOX_TYPE_LABEL[item.type] }}</strong>
          <span>{{ item.hint }}</span>
        </button>
        <p class="hint">누르거나 캔버스로 끌어다 놓으세요.</p>
        <label class="desc">
          시험장 설명
          <textarea v-model="description" rows="4" maxlength="1000" @input="markDirty" />
        </label>
      </aside>

      <div class="canvas" @drop.prevent="onDrop" @dragover.prevent>
        <VueFlow
          v-model:nodes="nodes"
          v-model:edges="edges"
          :default-edge-options="{ type: 'smoothstep' }"
          fit-view-on-init
          @node-click="({ node }) => select(node.id)"
          @edge-click="({ edge }) => select(null, edge.id)"
          @pane-click="select(null)"
          @node-drag-stop="markDirty"
          @nodes-change="onNodesChange"
          @edges-change="onEdgesChange"
        >
          <template #node-box="props">
            <BoxNode :data="props.data" :selected="props.id === selectedNodeId" />
          </template>
          <Background :gap="22" pattern-color="#d5d9e0" />
          <Controls :show-interactive="false" />
        </VueFlow>
      </div>

      <aside class="props" aria-label="속성">
        <template v-if="selectedBox">
          <div class="props-head">
            <div class="row spread">
              <span class="type-chip" :class="`type-${selectedBox.type}`">{{ BOX_TYPE_LABEL[selectedBox.type] }} 박스</span>
              <button type="button" class="icon-button danger" aria-label="박스 삭제" title="박스 삭제" @click="removeSelected">
                <AppIcon name="trash" />
              </button>
            </div>
            <input v-model="selectedBox.title" aria-label="박스 제목" placeholder="박스 제목" @input="markDirty" />
            <div v-if="tabs.length" class="segmented" role="tablist" style="margin-top: 0.75rem">
              <button
                v-for="t in tabs"
                :key="t.id"
                type="button"
                role="tab"
                :aria-selected="tab === t.id"
                :class="{ active: tab === t.id }"
                @click="tab = t.id"
              >
                {{ t.label }}
              </button>
            </div>
          </div>

          <div class="props-body">
            <p v-if="selectedBox.type === 'result'" class="muted">
              결과 박스에는 설정할 내용이 없습니다. 이 박스가 열리면 회차가 끝나고 팀의 최종 코드를 보여 줍니다.
            </p>

            <template v-else-if="tab === 'problem'">
              <div class="row spread" style="margin-bottom: 0.6rem">
                <span class="muted" style="font-size: 0.85rem">마크다운으로 씁니다</span>
                <div class="segmented">
                  <button type="button" :class="{ active: !preview }" @click="preview = false">편집</button>
                  <button type="button" :class="{ active: preview }" @click="preview = true">미리보기</button>
                </div>
              </div>
              <div v-if="preview" class="markdown-preview">
                <MarkdownView v-if="selectedBox.config.markdown" :source="selectedBox.config.markdown" />
                <p v-else class="muted">아직 쓴 내용이 없습니다.</p>
              </div>
              <textarea
                v-else
                v-model="selectedBox.config.markdown"
                class="markdown-input"
                aria-label="문제 (마크다운)"
                rows="18"
                spellcheck="false"
                placeholder="## 문제&#10;&#10;무엇을 만들어야 하는지 적어 주세요."
                @input="markDirty"
              />
            </template>

            <template v-else-if="tab === 'code'">
              <p class="muted" style="font-size: 0.85rem">
                참가자가 편집할 파일과 처음에 보이는 시작 코드입니다.
                <template v-if="selectedBox.type === 'team'">앞 개인 박스의 제출 파일은 자동으로 함께 들어옵니다.</template>
              </p>
              <div v-for="(file, i) in selectedBox.config.editor.files" :key="file.name" class="editor-file">
                <div class="editor-file-head">
                  {{ file.name }}
                  <button
                    type="button"
                    class="icon-button danger"
                    :aria-label="`${file.name} 빼기`"
                    title="파일 빼기"
                    @click="removeEditorFile(i)"
                  >
                    <AppIcon name="x" />
                  </button>
                </div>
                <CodeEditor v-model="file.starter" :label="`${file.name} 시작 코드`" @update:model-value="markDirty" />
              </div>
              <form class="row" @submit.prevent="addEditorFile">
                <input v-model="newFileName" class="mono" placeholder="a_entry.py" aria-label="새 파일 이름" />
                <button type="submit"><AppIcon name="plus" />파일 추가</button>
              </form>
            </template>

            <template v-else>
              <label class="check">
                <input v-model="selectedBox.config.attachments_enabled" type="checkbox" @change="markDirty" />
                참가자에게 첨부 파일 보여 주기
              </label>
              <template v-if="selectedBox.config.attachments_enabled">
                <ul class="attachment-list">
                  <li v-for="f in selectedAttachments" :key="f.id">
                    <a :href="adminApi.templateFileUrl(templateId, f.id)">{{ f.filename }}</a>
                    <button
                      type="button"
                      class="icon-button danger"
                      :aria-label="`${f.filename} 삭제`"
                      title="삭제"
                      @click="removeAttachment(f)"
                    >
                      <AppIcon name="trash" />
                    </button>
                  </li>
                </ul>
                <input type="file" aria-label="첨부 파일 올리기" @change="upload" />
                <p class="muted" style="font-size: 0.82rem; margin-top: 0.5rem">파일 하나에 10MB까지. 올리면 바로 저장됩니다.</p>
              </template>
            </template>
          </div>
        </template>

        <template v-else-if="selectedEdge">
          <div class="props-head">
            <div class="row spread" style="margin: 0">
              <h2 style="margin: 0">연결선</h2>
              <button type="button" class="icon-button danger" aria-label="연결선 삭제" title="연결선 삭제" @click="removeSelected">
                <AppIcon name="trash" />
              </button>
            </div>
            <p class="muted" style="margin: 0.25rem 0 0; font-size: 0.87rem">
              {{ boxTitle(selectedEdge.source) }} → {{ boxTitle(selectedEdge.target) }}
            </p>
          </div>
          <div class="props-body">
            <fieldset>
              <legend>다음 박스를 여는 방식</legend>
              <label class="choice">
                <input type="radio" name="edge-mode" :checked="selectedEdge.data?.mode === 'auto'" @change="setEdgeMode('auto')" />
                <span>
                  <strong>자동</strong>
                  <small>앞 박스가 끝나면(제출되면) 바로 열립니다.</small>
                </span>
              </label>
              <label class="choice">
                <input
                  type="radio"
                  name="edge-mode"
                  :checked="selectedEdge.data?.mode === 'approval'"
                  @change="setEdgeMode('approval')"
                />
                <span>
                  <strong>관리자 승인</strong>
                  <small>관리자가 진행 화면에서 승인해야 열립니다. 제출 전에도 승인할 수 있습니다.</small>
                </span>
              </label>
            </fieldset>
          </div>
        </template>

        <div v-else class="props-empty">
          <strong>박스나 연결선을 선택하세요</strong>
          <ol>
            <li>왼쪽에서 박스를 추가합니다.</li>
            <li>박스 오른쪽 점을 끌어 다음 박스에 놓으면 연결됩니다.</li>
            <li>박스를 누르면 여기서 문제와 코드 파일을 넣습니다.</li>
          </ol>
        </div>
      </aside>
    </div>
  </main>
</template>
