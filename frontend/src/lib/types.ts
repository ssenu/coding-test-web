// 백엔드 API 응답 타입. backend/app/services/views.py, api/*.py 와 맞춘다.

export type BoxType = 'common' | 'personal' | 'team' | 'result'
export type EdgeMode = 'auto' | 'approval'
export type BoxState = 'locked' | 'open' | 'closed'
export type RunStatus = 'lobby' | 'running' | 'finished'
export type Files = Record<string, string>

export interface EditorFile {
  name: string
  starter: string
}

export interface BoxConfig {
  markdown: string
  attachments_enabled: boolean
  editor: { files: EditorFile[] }
}

export interface BoxData {
  id: string
  type: BoxType
  title: string
  position: { x: number; y: number }
  config: BoxConfig
}

export interface EdgeData {
  id: string
  source: string
  target: string
  mode: EdgeMode
}

export interface GraphData {
  boxes: BoxData[]
  edges: EdgeData[]
}

export interface Issue {
  message: string
  box_ids: string[]
}

export interface TemplateSummary {
  id: number
  name: string
  description: string
  valid: boolean
  updated_at: string
}

export interface Template extends TemplateSummary {
  graph: GraphData
  issues: Issue[]
}

export interface StoredFile {
  id: number
  box_id?: string
  filename: string
  size: number
}

export interface RunSummary {
  id: number
  template_id: number
  name: string
  entry_code: string
  status: RunStatus
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export interface ParticipantInfo {
  id: number
  name: string
  assigned_box_id: string | null
  is_leader: boolean
  online: boolean
  typing: boolean
  last_active_at: string | null
  rejoin_requested: boolean
}

export interface VersionSummary {
  id: number
  box_id: string
  version_no: number
  saved_at: string
  is_final: boolean
}

export interface AdminState {
  run: RunSummary
  graph: GraphData
  boxes: Record<string, { state: BoxState; opened_at: string | null; closed_at: string | null }>
  approved_edges: string[]
  participants: ParticipantInfo[]
  submissions: Record<string, { participant_id: number; submitted_at: string }>
  team_versions: Record<string, VersionSummary[]>
  files: Record<string, StoredFile[]>
}

export interface Submission {
  box_id: string
  participant_id?: number
  files: Files
  submitted_at: string
}

export interface ParticipantBox {
  id: string
  type: BoxType
  title: string
  state: BoxState
  markdown?: string
  editor_files?: EditorFile[]
  attachments?: StoredFile[]
}

export interface TeamView {
  files: Files
  updated_at: string | null
  final: VersionSummary | null
}

export interface ParticipantState {
  run: { id: number; name: string; status: RunStatus }
  me: { id: number; name: string; assigned_box_id: string | null; is_leader: boolean }
  boxes: ParticipantBox[]
  my_submission: Submission | null
  team: Record<string, TeamView>
  result: Record<string, Files> | null
}

export interface JoinResult {
  status: 'joined' | 'pending'
  token: string
  participant_id: number
  run_id: number
}
