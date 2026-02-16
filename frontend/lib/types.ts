export enum TaskStatus {
  TODO = 'TODO',
  RUNNING = 'RUNNING',
  DONE = 'DONE',
  FAILED = 'FAILED',
  CANCELLED = 'CANCELLED',
}

export enum BackendType {
  CLAUDE_CODE = 'claude_code',
  CODEX_CLI = 'codex_cli',
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
}

export interface TaskCreateInput {
  title: string;
  prompt: string;
  workspace_id: number;
  backend: BackendType;
}

export interface Workspace {
  workspace_id: number;
  path: string;
  display_name: string;
  runner_id: number;
  concurrency_limit: number;
}

export interface Runner {
  runner_id: number;
  env: string;
  capabilities: string[];
  heartbeat_at: string;
  status: 'ONLINE' | 'OFFLINE';
  max_parallel: number;
}

export interface WorkspaceCreateInput {
  path: string;
  display_name: string;
  runner_id: number;
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
}

export interface LogEntry {
  run_id: number;
  task_id: number;
  started_at: string;
  ended_at?: string;
  exit_code?: number;
  log_blob: string;
}

export interface ApiMessage {
  message: string;
}

export interface ApiErrorBody {
  detail?: string;
}
