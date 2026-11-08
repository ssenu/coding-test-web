import { describe, expect, it } from 'vitest'
import {
  autoLayout,
  fromFlow,
  needsLayout,
  newBox,
  newEdge,
  toFlowEdge,
  toFlowEdges,
  toFlowNodes,
  uniqueId,
} from '../src/lib/graph'
import { parkingGraph } from './fixtures'

describe('graph 변환', () => {
  it('노드와 엣지로 바꿨다가 되돌리면 같은 그래프가 된다', () => {
    const graph = parkingGraph()
    expect(fromFlow(toFlowNodes(graph), toFlowEdges(graph))).toEqual(graph)
  })

  it('노드에 상태, 오류 표시, 배지를 붙인다', () => {
    const nodes = toFlowNodes(parkingGraph(), {
      states: { a: 'open' },
      invalidIds: ['b'],
      badges: { a: '가 · 제출' },
    })
    const a = nodes.find((n) => n.id === 'a')!
    const b = nodes.find((n) => n.id === 'b')!
    expect(a.type).toBe('box')
    expect(a.data).toMatchObject({ state: 'open', invalid: false, badge: '가 · 제출' })
    expect(b.data.invalid).toBe(true)
  })

  it('엣지 라벨과 클래스는 방식과 승인 여부를 따른다', () => {
    const auto = toFlowEdge({ id: 'e', source: 'x', target: 'y', mode: 'auto' })
    expect(auto).toMatchObject({ label: '자동', animated: true, class: 'edge-auto', data: { mode: 'auto' } })
    const approved = toFlowEdge({ id: 'g', source: 'x', target: 'y', mode: 'approval' }, ['g'])
    expect(approved).toMatchObject({ label: '승인 ✓', animated: false, class: 'edge-approval edge-approved' })
  })

  it('fromFlow는 위치를 정수로 맞추고 데이터 없는 노드는 버린다', () => {
    const graph = parkingGraph()
    const nodes = [
      ...toFlowNodes(graph).map((n) => ({ ...n, position: { x: 10.6, y: -3.2 } })),
      { id: 'ghost', position: { x: 0, y: 0 } },
    ]
    const back = fromFlow(nodes, [])
    expect(back.boxes).toHaveLength(graph.boxes.length)
    expect(back.boxes[0]!.position).toEqual({ x: 11, y: -3 })
  })

  it('새 박스와 새 엣지는 겹치지 않는 id를 받는다', () => {
    expect(uniqueId('personal', ['personal-1', 'personal-2'])).toBe('personal-3')
    const b = newBox('team', ['team-1'], { x: 5, y: 6 })
    expect(b).toMatchObject({ id: 'team-2', type: 'team', title: '팀 박스', position: { x: 5, y: 6 } })
    expect(b.config.editor.files).toEqual([])
    expect(newBox('result', [], { x: 0, y: 0 }).config.attachments_enabled).toBe(false)
    expect(newEdge('a', 'b', ['a-b-1'])).toEqual({ id: 'a-b-2', source: 'a', target: 'b', mode: 'auto' })
  })

  it('박스가 모두 한 자리에 겹쳐 있을 때만 자동 배치가 필요하다', () => {
    const graph = parkingGraph()
    expect(needsLayout(graph)).toBe(true)
    graph.boxes[0]!.position = { x: 5, y: 5 }
    expect(needsLayout(graph)).toBe(false)
    expect(needsLayout({ boxes: [], edges: [] })).toBe(false)
  })

  it('자동 배치는 단계별로 열을, 단계 안 순서로 행을 정한다', () => {
    const pos = Object.fromEntries(autoLayout(parkingGraph()).boxes.map((b) => [b.id, b.position]))
    expect(pos).toEqual({
      story: { x: 0, y: 0 },
      a: { x: 260, y: 0 },
      b: { x: 260, y: 120 },
      team: { x: 520, y: 0 },
      result: { x: 780, y: 0 },
    })
  })
})
