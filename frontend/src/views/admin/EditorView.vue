<script setup lang="ts">
// 시험장 에디터: 왼쪽 박스 팔레트, 가운데 캔버스, 오른쪽 속성 패널.
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
import { type Ref, computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import BoxNode from '../../components/BoxNode.vue'
import CodeEditor from '../../components/CodeEditor.vue'
import { ApiError, adminApi } from '../../lib/api'
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
import type { BoxData, BoxType, EdgeMode, Issue, StoredFile } from '../../lib/types'

const PALETTE: BoxType[] = ['common', 'personal', 'team', 'result']
const DRAG_TYPE = 'application/x-box-type'

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
const message = ref('')
const error = ref('')

const { screenToFlowCoordinate, onConnect } = useVueFlow()

const selectedBox = computed<BoxData | null>(
  () => nodes.value.find((n) => n.id === selectedNodeId.value)?.data?.box ?? null,
)
const selectedEdge = computed(() => edges.value.find((e) => e.id === selectedEdgeId.value) ?? null)
const selectedAttachments = computed(() => attachments.value.filter((f) => f.box_id === selectedNodeId.value))

function markDirty() {
  dirty.value = true
  message.value = ''
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
  if (!box || !fileName || box.config.editor.files.some((f) => f.name === fileName)) return
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
    message.value = t.valid ? '저장했습니다. 회차를 열 수 있습니다.' : '저장했습니다. 아래 문제를 고쳐야 회차를 열 수 있습니다.'
  })

const openRun = () =>
  guard(async () => {
    const runName = window.prompt('회차 이름', `${new Date().toLocaleDateString('ko-KR')} 회차`)
    if (!runName) return
    const run = await adminApi.createRun(templateId, runName)
    await router.push(`/admin/runs/${run.id}`)
  })

onMounted(() => guard(load))
</script>

<template>
  <main class="editor-page">
    <header class="page-head">
      <RouterLink to="/admin">← 시험장 목록</RouterLink>
      <input v-model="name" class="title-input" aria-label="시험장 이름" @input="markDirty" />
      <span v-if="dirty" class="tag warn">저장하지 않은 변경</span>
      <button class="primary" type="button" @click="save">저장</button>
      <button type="button" :disabled="!valid || dirty" @click="openRun">새 회차 열기</button>
    </header>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="message" class="notice" role="status">{{ message }}</p>
    <ul v-if="issues.length" class="issues">
      <li v-for="(issue, i) in issues" :key="i">
        {{ issue.message }}
        <span v-if="issue.box_ids.length" class="muted">({{ issue.box_ids.join(', ') }})</span>
      </li>
    </ul>

    <div class="editor-grid">
      <aside class="palette" aria-label="박스 종류">
        <p class="muted">끌어다 놓거나 눌러서 추가</p>
        <button
          v-for="type in PALETTE"
          :key="type"
          type="button"
          draggable="true"
          :class="`palette-item type-${type}`"
          @dragstart="onDragStart($event, type)"
          @click="addBox(type)"
        >
          {{ BOX_TYPE_LABEL[type] }}
        </button>
        <label class="desc">
          설명
          <textarea v-model="description" rows="4" @input="markDirty" />
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
          <Background />
          <Controls />
        </VueFlow>
      </div>

      <aside class="props" aria-label="속성">
        <template v-if="selectedBox">
          <h2>{{ BOX_TYPE_LABEL[selectedBox.type] }} 박스</h2>
          <label>제목<input v-model="selectedBox.title" @input="markDirty" /></label>
          <template v-if="selectedBox.type !== 'result'">
            <label>
              문제 (마크다운)
              <textarea v-model="selectedBox.config.markdown" rows="8" @input="markDirty" />
            </label>
            <label class="check">
              <input v-model="selectedBox.config.attachments_enabled" type="checkbox" @change="markDirty" />
              첨부 파일 사용
            </label>
          </template>

          <section v-if="hasEditor(selectedBox.type)">
            <h3>코드 파일</h3>
            <div v-for="(file, i) in selectedBox.config.editor.files" :key="file.name" class="editor-file">
              <div class="row spread">
                <strong>{{ file.name }}</strong>
                <button type="button" class="danger small" @click="removeEditorFile(i)">빼기</button>
              </div>
              <CodeEditor v-model="file.starter" :label="`${file.name} 시작 코드`" @update:model-value="markDirty" />
            </div>
            <form class="row" @submit.prevent="addEditorFile">
              <input v-model="newFileName" placeholder="a_entry.py" aria-label="새 파일 이름" />
              <button type="submit">파일 추가</button>
            </form>
          </section>

          <section v-if="selectedBox.config.attachments_enabled && selectedBox.type !== 'result'">
            <h3>첨부 파일</h3>
            <ul>
              <li v-for="f in selectedAttachments" :key="f.id" class="row spread">
                <a :href="adminApi.templateFileUrl(templateId, f.id)">{{ f.filename }}</a>
                <button type="button" class="danger small" @click="removeAttachment(f)">삭제</button>
              </li>
            </ul>
            <input type="file" aria-label="첨부 파일 올리기" @change="upload" />
          </section>

          <button type="button" class="danger" @click="removeSelected">박스 삭제</button>
        </template>

        <template v-else-if="selectedEdge">
          <h2>연결선</h2>
          <fieldset class="row">
            <legend>다음 박스를 여는 방식</legend>
            <label class="check">
              <input type="radio" :checked="selectedEdge.data?.mode === 'auto'" @change="setEdgeMode('auto')" />
              자동 (앞 박스가 끝나면 바로)
            </label>
            <label class="check">
              <input type="radio" :checked="selectedEdge.data?.mode === 'approval'" @change="setEdgeMode('approval')" />
              관리자 승인
            </label>
          </fieldset>
          <button type="button" class="danger" @click="removeSelected">연결선 삭제</button>
        </template>

        <p v-else class="muted">박스나 연결선을 선택하면 여기서 설정합니다. 박스 오른쪽 점을 끌어 다른 박스에 놓으면 연결됩니다.</p>
      </aside>
    </div>
  </main>
</template>
