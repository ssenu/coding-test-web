// 관리자 진행 화면용 계산. 화면과 무관한 순수 함수.
import type { AdminState, BoxState } from './types'

export interface Gate {
  target: string
  targetTitle: string
  edgeIds: string[]
  unsubmitted: string[]
}

/** 지금 승인할 수 있는 연결선을 도착 박스별로 묶는다. 출발 박스가 열린 적 있고 도착 박스가 잠겨 있어야 한다. */
export function pendingGates(state: AdminState): Gate[] {
  const approved = new Set(state.approved_edges)
  const boxState = (id: string): BoxState => state.boxes[id]?.state ?? 'locked'
  const gates = new Map<string, Gate>()
  for (const edge of state.graph.edges) {
    if (edge.mode !== 'approval' || approved.has(edge.id)) continue
    if (boxState(edge.source) === 'locked' || boxState(edge.target) !== 'locked') continue
    const target = state.graph.boxes.find((b) => b.id === edge.target)
    const source = state.graph.boxes.find((b) => b.id === edge.source)
    let gate = gates.get(edge.target)
    if (!gate) {
      gate = { target: edge.target, targetTitle: target?.title ?? edge.target, edgeIds: [], unsubmitted: [] }
      gates.set(edge.target, gate)
    }
    gate.edgeIds.push(edge.id)
    if (source?.type === 'personal' && !state.submissions[edge.source]) gate.unsubmitted.push(edge.source)
  }
  return [...gates.values()]
}

/** 이 승인으로 넘어가는 팀 박스 중 아직 최종 제출이 없는 것의 제목. 서버는 이 경우를 따로 묻지 않으므로 화면에서 확인한다. */
export function teamsWithoutFinal(state: AdminState, gate: Gate): string[] {
  const titles: string[] = []
  for (const edge of state.graph.edges) {
    if (!gate.edgeIds.includes(edge.id)) continue
    const source = state.graph.boxes.find((b) => b.id === edge.source)
    if (source?.type !== 'team') continue
    if (!(state.team_versions[source.id] ?? []).some((v) => v.is_final)) titles.push(source.title)
  }
  return titles
}

/** 관리자에게 보여 줄 배정 관련 경고. */
export function assignmentWarnings(state: AdminState): string[] {
  const personal = state.graph.boxes.filter((b) => b.type === 'personal')
  const assigned = new Set(state.participants.map((p) => p.assigned_box_id).filter(Boolean))
  const warnings: string[] = []
  const unassignedPeople = state.participants.filter((p) => !p.assigned_box_id).length
  const freeBoxes = personal.filter((b) => !assigned.has(b.id)).length
  if (unassignedPeople > 0 && freeBoxes === 0) {
    warnings.push(`배정할 개인 박스가 없는 참가자가 ${unassignedPeople}명 있습니다.`)
  }
  if (freeBoxes > 0 && state.run.status !== 'finished') {
    warnings.push(`아직 맡은 사람이 없는 개인 박스가 ${freeBoxes}개 있습니다.`)
  }
  if (state.participants.length > 0 && !state.participants.some((p) => p.is_leader)) {
    if (state.graph.boxes.some((b) => b.type === 'team')) warnings.push('팀장이 지정되지 않았습니다.')
  }
  return warnings
}

/** 진행 흐름도 노드에 붙일 짧은 표시(담당자, 제출 여부, 버전 수). */
export function boxBadges(state: AdminState): Record<string, string> {
  const badges: Record<string, string> = {}
  for (const box of state.graph.boxes) {
    if (box.type === 'personal') {
      const owner = state.participants.find((p) => p.assigned_box_id === box.id)
      const done = state.submissions[box.id] ? '제출' : '미제출'
      badges[box.id] = `${owner?.name ?? '미배정'} · ${done}`
    } else if (box.type === 'team') {
      const versions = state.team_versions[box.id] ?? []
      const final = versions.some((v) => v.is_final)
      badges[box.id] = final ? '최종 제출' : `버전 ${versions.length}개`
    }
  }
  return badges
}

export const TYPING_WINDOW_MS = 60_000

/** 최근 입력 신호가 있었는지. 서버가 준 typing 값은 이벤트 시점 기준이라 화면의 시계로 다시 계산한다. */
export function isTyping(p: { last_active_at: string | null }, now: number): boolean {
  if (!p.last_active_at) return false
  return now - new Date(p.last_active_at).getTime() < TYPING_WINDOW_MS
}

/** 개인 박스 중 제출된 수와 전체 수. */
export function submitProgress(state: AdminState): { done: number; total: number } {
  const personal = state.graph.boxes.filter((b) => b.type === 'personal')
  return { done: personal.filter((b) => state.submissions[b.id]).length, total: personal.length }
}

export function boxStates(state: AdminState): Record<string, BoxState> {
  return Object.fromEntries(Object.entries(state.boxes).map(([id, b]) => [id, b.state]))
}
