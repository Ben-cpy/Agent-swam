export enum TaskStatus {
  TODO = 'TODO',
  RUNNING = 'RUNNING',
  DONE = 'DONE',
  FAILED = 'FAILED',
  FAILED_QUOTA = 'FAILED_QUOTA',
  CANCELLED = 'CANCELLED',
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
  workspace_type: WorkspaceType;
  host?: string | null;
  port?: number | null;
  ssh_user?: string | null;
  container_name?: string | null;
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
  workspace_type: WorkspaceType;
  host?: string;
  port?: number;
  ssh_user?: string;
  container_name?: string;
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

export interface QuotaState {
  id: number;
  provider: string;
  account_label: string;
  state: 'OK' | 'QUOTA_EXHAUSTED' | 'UNKNOWN';
  last_event_at?: string;
  note?: string;
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

export interface UsageWindow {
  task_count: number;
  total_cost_usd?: number;
  total_tokens?: number;
  window_start: string;
  window_end: string;
}

export interface ProviderUsage {
  '5h': UsageWindow;
  weekly: UsageWindow;
  quota_state: 'OK' | 'QUOTA_EXHAUSTED' | 'UNKNOWN';
  last_quota_error: string | null;
}

export interface UsageData {
  claude: ProviderUsage;
  openai: ProviderUsage;
}
