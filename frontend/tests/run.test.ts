import { describe, expect, it } from 'vitest'
import { assignmentWarnings, boxBadges, boxStates, isTyping, pendingGates, teamsWithoutFinal } from '../src/lib/run'
import type { ParticipantInfo } from '../src/lib/types'
import { adminState } from './fixtures'

function person(id: number, name: string, box: string | null, leader = false): ParticipantInfo {
  return {
    id,
    name,
    assigned_box_id: box,
    is_leader: leader,
    online: true,
    typing: false,
    last_active_at: null,
    rejoin_requested: false,
  }
}

describe('pendingGates', () => {
  it('열린 개인 박스에서 잠긴 팀 박스로 가는 승인 선을 묶는다', () => {
    const gates = pendingGates(adminState({ submissions: { a: { participant_id: 1, submitted_at: 'x' } } }))
    expect(gates).toEqual([{ target: 'team', targetTitle: '통합', edgeIds: ['a-team', 'b-team'], unsubmitted: ['b'] }])
  })

  it('이미 승인했거나 출발 박스가 잠겨 있으면 빠진다', () => {
    const state = adminState({ approved_edges: ['a-team'] })
    state.boxes.b!.state = 'locked'
    expect(pendingGates(state)).toEqual([])
  })

  it('도착 박스가 이미 열렸으면 승인할 것이 없다', () => {
    const state = adminState()
    state.boxes.team!.state = 'open'
    expect(pendingGates(state)).toEqual([])
  })
})

describe('assignmentWarnings', () => {
  it('빈 개인 박스와 팀장 미지정을 알려 준다', () => {
    const warnings = assignmentWarnings(adminState({ participants: [person(1, '가', 'a')] }))
    expect(warnings).toEqual(['아직 맡은 사람이 없는 개인 박스가 1개 있습니다.', '팀장이 지정되지 않았습니다.'])
  })

  it('개인 박스보다 사람이 많으면 알려 준다', () => {
    const people = [person(1, '가', 'a', true), person(2, '나', 'b'), person(3, '다', null)]
    expect(assignmentWarnings(adminState({ participants: people }))).toEqual([
      '배정할 개인 박스가 없는 참가자가 1명 있습니다.',
    ])
  })
})

describe('boxBadges / boxStates', () => {
  it('개인 박스는 담당자와 제출 여부, 팀 박스는 버전 수를 보여 준다', () => {
    const state = adminState({
      participants: [person(1, '가', 'a')],
      submissions: { a: { participant_id: 1, submitted_at: 'x' } },
      team_versions: { team: [{ id: 1, box_id: 'team', version_no: 1, saved_at: 'x', is_final: false }] },
    })
    expect(boxBadges(state)).toEqual({ a: '가 · 제출', b: '미배정 · 미제출', team: '버전 1개' })
    expect(boxStates(state).a).toBe('open')
  })
})

describe('teamsWithoutFinal', () => {
  it('최종 제출이 없는 팀 박스에서 나가는 승인이면 그 제목을 돌려준다', () => {
    const state = adminState()
    const gate = { target: 'result', targetTitle: '결과', edgeIds: ['team-result'], unsubmitted: [] }
    expect(teamsWithoutFinal(state, gate)).toEqual(['통합'])
    state.team_versions.team = [{ id: 1, box_id: 'team', version_no: 1, saved_at: 'x', is_final: true }]
    expect(teamsWithoutFinal(state, gate)).toEqual([])
  })
})

describe('isTyping', () => {
  it('최근 60초 안에 입력 신호가 있었을 때만 참이다', () => {
    const now = Date.parse('2026-11-10T03:00:00Z')
    expect(isTyping({ last_active_at: '2026-11-10T02:59:30Z' }, now)).toBe(true)
    expect(isTyping({ last_active_at: '2026-11-10T02:58:00Z' }, now)).toBe(false)
    expect(isTyping({ last_active_at: null }, now)).toBe(false)
  })
})
