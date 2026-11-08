import { beforeEach, describe, expect, it } from 'vitest'
import type { ParticipantBox, ParticipantState } from '../src/lib/types'
import { defaultBoxId, initialFiles, isWaiting, loadDraft, saveDraft } from '../src/lib/workspace'

function pbox(id: string, type: ParticipantBox['type'], state: ParticipantBox['state']): ParticipantBox {
  return { id, type, title: id, state, editor_files: [{ name: `${id}.py`, starter: 'S' }] }
}

function pstate(overrides: Partial<ParticipantState> = {}): ParticipantState {
  return {
    run: { id: 1, name: '1기', status: 'running' },
    me: { id: 1, name: '가', assigned_box_id: 'a', is_leader: false },
    boxes: [pbox('story', 'common', 'closed'), pbox('a', 'personal', 'open'), pbox('team', 'team', 'locked')],
    my_submission: null,
    team: {},
    result: null,
    ...overrides,
  }
}

describe('workspace', () => {
  beforeEach(() => localStorage.clear())

  it('편집기 처음 내용은 임시본 > 제출본 > 시작 코드 순서', () => {
    const box = pbox('a', 'personal', 'open')
    expect(initialFiles(box, null, null)).toEqual({ 'a.py': 'S' })
    expect(initialFiles(box, { 'a.py': 'SUB' }, null)).toEqual({ 'a.py': 'SUB' })
    expect(initialFiles(box, { 'a.py': 'SUB' }, { 'a.py': 'DRAFT', 'x.py': 'ignored' })).toEqual({
      'a.py': 'DRAFT',
    })
  })

  it('임시본은 회차와 박스별로 저장된다', () => {
    saveDraft(1, 'a', { 'a.py': 'x' })
    expect(loadDraft(1, 'a')).toEqual({ 'a.py': 'x' })
    expect(loadDraft(2, 'a')).toBeNull()
  })

  it('처음 열 박스는 열린 팀 > 내 개인 > 공통 순', () => {
    expect(defaultBoxId(pstate())).toBe('a')
    const teamOpen = pstate()
    teamOpen.boxes[2]!.state = 'open'
    expect(defaultBoxId(teamOpen)).toBe('team')
    expect(defaultBoxId(pstate({ boxes: [] }))).toBeNull()
  })

  it('대기실이거나 배정 전에 열린 박스가 없으면 기다린다', () => {
    expect(isWaiting(pstate({ run: { id: 1, name: '', status: 'lobby' } }))).toBe(true)
    const unassigned = pstate({
      me: { id: 1, name: '가', assigned_box_id: null, is_leader: false },
      boxes: [pbox('team', 'team', 'locked')],
    })
    expect(isWaiting(unassigned)).toBe(true)
    expect(isWaiting(pstate())).toBe(false)
  })
})
