// API 그래프(GraphData) <-> Vue Flow 노드/엣지 변환. 화면과 무관한 순수 함수.
import type { BoxData, BoxState, BoxType, EdgeData, EdgeMode, GraphData } from './types'

export const BOX_TYPE_LABEL: Record<BoxType, string> = {
  common: '공통',
  personal: '개인',
  team: '팀',
  result: '결과',
}

export const EDGE_MODE_LABEL: Record<EdgeMode, string> = {
  auto: '자동',
  approval: '승인',
}

export const BOX_STATE_LABEL: Record<BoxState, string> = {
  locked: '잠김',
  open: '진행 중',
  closed: '완료',
}

// 노드에 붙는 표시용 정보. 에디터와 진행 화면이 각자 필요한 것만 채운다.
export interface BoxNodeData {
  box: BoxData
  state?: BoxState
  invalid?: boolean
  badge?: string
}

export interface FlowNode {
  id: string
  type: 'box'
  position: { x: number; y: number }
  data: BoxNodeData
}

export interface FlowEdge {
  id: string
  source: string
  target: string
  label: string
  animated: boolean
  class: string
  data: { mode: EdgeMode }
}

export interface NodeDecor {
  states?: Record<string, BoxState>
  invalidIds?: Iterable<string>
  badges?: Record<string, string>
}

export function toFlowNodes(graph: GraphData, decor: NodeDecor = {}): FlowNode[] {
  const invalid = new Set(decor.invalidIds ?? [])
  return graph.boxes.map((box) => ({
    id: box.id,
    type: 'box',
    position: { ...box.position },
    data: {
      box,
      state: decor.states?.[box.id],
      invalid: invalid.has(box.id),
      badge: decor.badges?.[box.id],
    },
  }))
}

export function toFlowEdge(edge: EdgeData, approved: Iterable<string> = []): FlowEdge {
  const isApproved = new Set(approved).has(edge.id)
  return {
    id: edge.id,
    source: edge.source,
    target: edge.target,
    label: EDGE_MODE_LABEL[edge.mode] + (isApproved ? ' ✓' : ''),
    animated: edge.mode === 'auto',
    class: `edge-${edge.mode}${isApproved ? ' edge-approved' : ''}`,
    data: { mode: edge.mode },
  }
}

export function toFlowEdges(graph: GraphData, approved: Iterable<string> = []): FlowEdge[] {
  const set = new Set(approved)
  return graph.edges.map((e) => toFlowEdge(e, set))
}

interface NodeLike {
  id: string
  position: { x: number; y: number }
  data?: { box: BoxData }
}

interface EdgeLike {
  id: string
  source: string
  target: string
  data?: { mode?: EdgeMode }
}

export function fromFlow(nodes: NodeLike[], edges: EdgeLike[]): GraphData {
  const boxes: BoxData[] = []
  for (const n of nodes) {
    if (!n.data?.box) continue
    boxes.push({ ...n.data.box, id: n.id, position: { x: Math.round(n.position.x), y: Math.round(n.position.y) } })
  }
  return {
    boxes,
    edges: edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      mode: e.data?.mode ?? 'approval',
    })),
  }
}

export function uniqueId(prefix: string, taken: Iterable<string>): string {
  const used = new Set(taken)
  let n = 1
  while (used.has(`${prefix}-${n}`)) n += 1
  return `${prefix}-${n}`
}

export function newBox(type: BoxType, taken: Iterable<string>, position: { x: number; y: number }): BoxData {
  return {
    id: uniqueId(type, taken),
    type,
    title: `${BOX_TYPE_LABEL[type]} 박스`,
    position,
    config: { markdown: '', attachments_enabled: type !== 'result', editor: { files: [] } },
  }
}

export function newEdge(source: string, target: string, taken: Iterable<string>, mode: EdgeMode = 'auto'): EdgeData {
  return { id: uniqueId(`${source}-${target}`, taken), source, target, mode }
}

const LAYOUT_X = 260
const LAYOUT_Y = 120

/** 모든 박스가 같은 자리에 겹쳐 있으면(API로 만든 시험장 등) true. */
export function needsLayout(graph: GraphData): boolean {
  if (graph.boxes.length < 2) return false
  const first = graph.boxes[0]!.position
  return graph.boxes.every((b) => b.position.x === first.x && b.position.y === first.y)
}

/** 시작 박스에서의 가장 긴 거리(단계)로 열을, 같은 단계 안의 순서로 행을 정해 박스를 배치한다. */
export function autoLayout(graph: GraphData): GraphData {
  const depth = new Map<string, number>(graph.boxes.map((b) => [b.id, 0]))
  // 순환이 없으면 박스 수만큼 반복하면 충분하다. 순환이 있어도 끝나도록 횟수를 제한한다.
  for (let i = 0; i < graph.boxes.length; i += 1) {
    for (const e of graph.edges) {
      const next = (depth.get(e.source) ?? 0) + 1
      if (next > (depth.get(e.target) ?? 0) && next < graph.boxes.length) depth.set(e.target, next)
    }
  }
  const row = new Map<number, number>()
  const boxes = graph.boxes.map((b) => {
    const col = depth.get(b.id) ?? 0
    const r = row.get(col) ?? 0
    row.set(col, r + 1)
    return { ...b, position: { x: col * LAYOUT_X, y: r * LAYOUT_Y } }
  })
  return { ...graph, boxes }
}

export function hasEditor(type: BoxType): boolean {
  return type === 'personal' || type === 'team'
}
