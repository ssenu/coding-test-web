// 참가자 작업 화면용 계산과 개인 단계 임시 저장(localStorage). 화면과 무관한 순수 함수.
import type { Files, ParticipantBox, ParticipantState } from './types'

export function draftKey(runId: number, boxId: string): string {
  return `ctw.draft.${runId}.${boxId}`
}

export function loadDraft(runId: number, boxId: string): Files | null {
  const raw = localStorage.getItem(draftKey(runId, boxId))
  if (!raw) return null
  try {
    return JSON.parse(raw) as Files
  } catch {
    return null
  }
}

export function saveDraft(runId: number, boxId: string, files: Files): void {
  localStorage.setItem(draftKey(runId, boxId), JSON.stringify(files))
}

/** 개인 박스 편집기의 처음 내용: 브라우저 임시본 > 마지막 제출본 > 시작 코드. 파일 목록은 박스 설정을 따른다. */
export function initialFiles(box: ParticipantBox, submitted: Files | null, draft: Files | null): Files {
  const files: Files = {}
  for (const f of box.editor_files ?? []) {
    files[f.name] = draft?.[f.name] ?? submitted?.[f.name] ?? f.starter
  }
  return files
}

/** 처음 열어 줄 박스: 열린 팀 박스 > 내 열린 개인 박스 > 열린 공통 박스 > 첫 박스. */
export function defaultBoxId(state: ParticipantState): string | null {
  const open = (type: ParticipantBox['type']) => state.boxes.find((b) => b.type === type && b.state === 'open')
  return (open('team') ?? open('personal') ?? open('common') ?? state.boxes[0])?.id ?? null
}

export function isWaiting(state: ParticipantState): boolean {
  if (state.run.status === 'lobby') return true
  return !state.me.assigned_box_id && !state.boxes.some((b) => b.state !== 'locked')
}
