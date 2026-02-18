export enum TaskStatus {
  TODO = 'TODO',
  RUNNING = 'RUNNING',
  DONE = 'DONE',
  FAILED = 'FAILED',
}

export enum BackendType {
  CLAUDE_CODE = 'claude_code',
  CODEX_CLI = 'codex_cli',
}

export enum WorkspaceType {
  LOCAL = 'local',
  SSH = 'ssh',
  SSH_CONTAINER = 'ssh_container',
}

export interface Task {
  id: number;
  title: string;
  prompt: string;
  workspace_id: number;
  backend: BackendType;
  status: TaskStatus;
  created_at: string;
  updated_at: string;
  run_id?: number;
  branch_name?: string | null;
  worktree_path?: string | null;
  model?: string | null;
}

export interface TaskCreateInput {
  title: string;
  prompt: string;
  workspace_id: number;
  backend: BackendType;
  branch_name?: string;
  model?: string;
}

export interface BackendModelInfo {
  backend: string;
  models: string[];
  default: string;
  reasoning_efforts?: string[];
}

export interface ModelsListResponse {
  results: BackendModelInfo[];
}

export interface Workspace {
  workspace_id: number;
  path: string;
  display_name: string;
  workspace_type: WorkspaceType;
  host?: string | null;
  port?: number | null;
  ssh_user?: string | null;
  container_name?: string | null;
  runner_id: number;
  concurrency_limit: number;
}

export interface WorkspaceCreateInput {
  path: string;
  display_name: string;
  workspace_type: WorkspaceType;
  host?: string;
  port?: number;
  ssh_user?: string;
  container_name?: string;
  runner_id?: number;
}

export interface Run {
  run_id: number;
  task_id: number;
  runner_id: number;
  backend: string;
  started_at: string;
  ended_at?: string;
  exit_code?: number;
  error_class?: string;
  usage_json?: string;
}

export interface LogEntry {
  run_id: number;
  task_id: number;
  started_at: string;
  ended_at?: string;
  exit_code?: number;
  log_blob: string;
  usage_json?: string;
}

export interface ApiMessage {
  message: string;
}

export interface ApiErrorBody {
  detail?: string;
}

export interface NextTaskNumber {
  next_number: number;
  suggested_title: string;
}
