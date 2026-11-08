// 백엔드 REST 호출. 관리자는 쿠키(같은 출처), 참가자는 X-Participant-Token 헤더.
import type {
  AdminState,
  Files,
  GraphData,
  JoinResult,
  ParticipantInfo,
  ParticipantState,
  RunSummary,
  StoredFile,
  Submission,
  Template,
  TemplateSummary,
  VersionSummary,
} from './types'

export class ApiError extends Error {
  readonly status: number
  readonly detail: unknown

  constructor(status: number, detail: unknown) {
    super(errorMessage(status, detail))
    this.status = status
    this.detail = detail
  }
}

function errorMessage(status: number, detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object' && 'message' in detail) {
    return String((detail as { message: unknown }).message)
  }
  if (Array.isArray(detail)) return '입력값을 확인하세요.'
  return `요청이 실패했습니다 (${status})`
}

// ---------------------------------------------------------------- 참가자 토큰 보관
const PARTICIPANT_KEY = 'ctw.participant'

export interface StoredParticipant {
  token: string
  runId: number
  participantId: number
}

export function saveParticipant(p: StoredParticipant): void {
  localStorage.setItem(PARTICIPANT_KEY, JSON.stringify(p))
}

export function loadParticipant(): StoredParticipant | null {
  const raw = localStorage.getItem(PARTICIPANT_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as StoredParticipant
  } catch {
    return null
  }
}

export function clearParticipant(): void {
  localStorage.removeItem(PARTICIPANT_KEY)
}

// ---------------------------------------------------------------- 공통 요청
interface RequestOptions {
  body?: unknown
  form?: FormData
  participant?: boolean
}

async function request<T>(method: string, path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {}
  let body: BodyInit | undefined
  if (options.form) {
    body = options.form
  } else if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(options.body)
  }
  if (options.participant) {
    const p = loadParticipant()
    if (p) headers['X-Participant-Token'] = p.token
  }
  const res = await fetch(path, { method, headers, body, credentials: 'same-origin' })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new ApiError(res.status, (data as { detail?: unknown }).detail ?? res.statusText)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

const get = <T>(path: string, participant = false) => request<T>('GET', path, { participant })
const post = <T>(path: string, body?: unknown, participant = false) =>
  request<T>('POST', path, { body, participant })
const put = <T>(path: string, body: unknown, participant = false) =>
  request<T>('PUT', path, { body, participant })
const patch = <T>(path: string, body: unknown) => request<T>('PATCH', path, { body })
const del = (path: string) => request<void>('DELETE', path)

// ---------------------------------------------------------------- 관리자
export const adminApi = {
  login: (password: string) => post<{ ok: boolean }>('/api/admin/login', { password }),
  logout: () => post<{ ok: boolean }>('/api/admin/logout'),
  me: () => get<{ admin: boolean }>('/api/admin/me'),

  listTemplates: () => get<TemplateSummary[]>('/api/templates'),
  createTemplate: (name: string) => post<Template>('/api/templates', { name }),
  getTemplate: (id: number) => get<Template>(`/api/templates/${id}`),
  saveTemplate: (id: number, data: { name: string; description: string; graph: GraphData }) =>
    put<Template>(`/api/templates/${id}`, data),
  deleteTemplate: (id: number) => del(`/api/templates/${id}`),
  duplicateTemplate: (id: number) => post<Template>(`/api/templates/${id}/duplicate`),
  listTemplateFiles: (id: number) => get<StoredFile[]>(`/api/templates/${id}/files`),
  uploadTemplateFile: (id: number, boxId: string, file: File) => {
    const form = new FormData()
    form.append('box_id', boxId)
    form.append('file', file)
    return request<StoredFile>('POST', `/api/templates/${id}/files`, { form })
  },
  deleteTemplateFile: (id: number, fileId: number) => del(`/api/templates/${id}/files/${fileId}`),
  templateFileUrl: (id: number, fileId: number) => `/api/templates/${id}/files/${fileId}`,

  createRun: (templateId: number, name: string) =>
    post<RunSummary>(`/api/templates/${templateId}/runs`, { name }),
  listRuns: (templateId?: number) =>
    get<RunSummary[]>(templateId === undefined ? '/api/runs' : `/api/runs?template_id=${templateId}`),
  runState: (runId: number) => get<AdminState>(`/api/runs/${runId}/state`),
  startRun: (runId: number) => post<AdminState>(`/api/runs/${runId}/start`),
  finishRun: (runId: number) => post<AdminState>(`/api/runs/${runId}/finish`),
  patchParticipant: (
    runId: number,
    participantId: number,
    body: { assigned_box_id?: string | null; is_leader?: boolean },
  ) => patch<ParticipantInfo>(`/api/runs/${runId}/participants/${participantId}`, body),
  approveRejoin: (runId: number, participantId: number) =>
    post<ParticipantInfo>(`/api/runs/${runId}/participants/${participantId}/approve-rejoin`),
  removeParticipant: (runId: number, participantId: number) =>
    del(`/api/runs/${runId}/participants/${participantId}`),
  approve: (runId: number, edgeIds: string[], confirm: boolean) =>
    post<AdminState>(`/api/runs/${runId}/approvals`, { edge_ids: edgeIds, confirm }),
  patchBox: (runId: number, boxId: string, markdown: string) =>
    patch<{ box_id: string; markdown: string }>(`/api/runs/${runId}/boxes/${boxId}`, { markdown }),
  submission: (runId: number, boxId: string) =>
    get<Submission>(`/api/runs/${runId}/boxes/${boxId}/submission`),
  versions: (runId: number, boxId: string) =>
    get<VersionSummary[]>(`/api/runs/${runId}/boxes/${boxId}/versions`),
  version: (runId: number, versionId: number) =>
    get<VersionSummary & { files: Files }>(`/api/runs/${runId}/versions/${versionId}`),
  runFileUrl: (runId: number, fileId: number) => `/api/runs/${runId}/files/${fileId}`,
}

// ---------------------------------------------------------------- 참가자
export const participantApi = {
  join: (entryCode: string, name: string) =>
    post<JoinResult>('/api/p/join', { entry_code: entryCode, name }),
  state: () => get<ParticipantState>('/api/p/state', true),
  submit: (boxId: string, files: Files) =>
    post<{ box_id: string; submitted_at: string }>(`/api/p/boxes/${boxId}/submit`, { files }, true),
  saveDraft: (boxId: string, files: Files) =>
    put<{ box_id: string; files: Files; updated_at: string }>(`/api/p/boxes/${boxId}/draft`, { files }, true),
  saveVersion: (boxId: string, files: Files, final: boolean) =>
    post<VersionSummary>(`/api/p/boxes/${boxId}/versions`, { files, final }, true),
  async download(fileId: number, filename: string): Promise<void> {
    const p = loadParticipant()
    const res = await fetch(`/api/p/files/${fileId}`, {
      headers: p ? { 'X-Participant-Token': p.token } : {},
    })
    if (!res.ok) throw new ApiError(res.status, '파일을 받을 수 없습니다.')
    const url = URL.createObjectURL(await res.blob())
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  },
}
