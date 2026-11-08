// 테스트용 데이터. 주차장 과제 구조: 스토리 → 개인 a~d(자동) → 팀(승인) → 결과(자동)
import type { AdminState, BoxData, BoxType, GraphData } from '../src/lib/types'

export function box(id: string, type: BoxType, title: string, files: string[] = []): BoxData {
  return {
    id,
    type,
    title,
    position: { x: 0, y: 0 },
    config: {
      markdown: `${title} 문제`,
      attachments_enabled: false,
      editor: { files: files.map((name) => ({ name, starter: `# ${name}\n` })) },
    },
  }
}

export function parkingGraph(): GraphData {
  const boxes = [
    box('story', 'common', '스토리'),
    box('a', 'personal', '입차', ['a_entry.py']),
    box('b', 'personal', '출차', ['b_exit.py']),
    box('team', 'team', '통합', ['e_main.py']),
    box('result', 'result', '결과'),
  ]
  const edges = [
    { id: 's-a', source: 'story', target: 'a', mode: 'auto' as const },
    { id: 's-b', source: 'story', target: 'b', mode: 'auto' as const },
    { id: 'a-team', source: 'a', target: 'team', mode: 'approval' as const },
    { id: 'b-team', source: 'b', target: 'team', mode: 'approval' as const },
    { id: 'team-result', source: 'team', target: 'result', mode: 'auto' as const },
  ]
  return { boxes, edges }
}

export function adminState(overrides: Partial<AdminState> = {}): AdminState {
  return {
    run: {
      id: 1,
      template_id: 1,
      name: '1기',
      entry_code: 'ABC234',
      status: 'running',
      created_at: '2026-11-08T00:00:00Z',
      started_at: '2026-11-08T00:00:00Z',
      finished_at: null,
    },
    graph: parkingGraph(),
    boxes: {
      story: { state: 'closed', opened_at: null, closed_at: null },
      a: { state: 'open', opened_at: null, closed_at: null },
      b: { state: 'open', opened_at: null, closed_at: null },
      team: { state: 'locked', opened_at: null, closed_at: null },
      result: { state: 'locked', opened_at: null, closed_at: null },
    },
    approved_edges: [],
    participants: [],
    submissions: {},
    team_versions: {},
    files: {},
    ...overrides,
  }
}
