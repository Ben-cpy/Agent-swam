import axios from 'axios';
import {
  ApiMessage,
  AppSettings,
  AppSettingsUpdateInput,
  LogEntry,
  ModelsListResponse,
  NextTaskNumber,
  Task,
  TaskCreateInput,
  TaskStatus,
  UsageStats,
  Workspace,
  WorkspaceCreateInput,
  WorkspaceResources,
} from './types';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000/api';
const NORMALIZED_API_BASE = API_BASE_URL.replace(/\/+$/, '');

export const apiClient = axios.create({
  baseURL: NORMALIZED_API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Task APIs
export const taskAPI = {
  list: (params?: { status?: TaskStatus; workspaceId?: number }) =>
    apiClient.get<Task[]>('/tasks', {
      params: {
        ...(params?.status ? { status: params.status } : {}),
        ...(params?.workspaceId ? { workspace_id: params.workspaceId } : {}),
      },
    }),

  get: (id: number) =>
    apiClient.get<Task>(`/tasks/${id}`),

  create: (data: TaskCreateInput) =>
    apiClient.post<Task>('/tasks', data),

  cancel: (id: number) =>
    apiClient.post<ApiMessage>(`/tasks/${id}/cancel`),

  retry: (id: number) =>
    apiClient.post<Task>(`/tasks/${id}/retry`),

  continue: (id: number, data: { prompt: string; model?: string }) =>
    apiClient.post<Task>(`/tasks/${id}/continue`, data),

  merge: (id: number) =>
    apiClient.post<Task>(`/tasks/${id}/merge`),

  markDone: (id: number) =>
    apiClient.post<Task>(`/tasks/${id}/mark-done`),

  delete: (id: number) =>
    apiClient.delete<ApiMessage>(`/tasks/${id}`),

  updateTitle: async (id: number, title: string) => {
    try {
      return await apiClient.post<Task>(`/tasks/${id}/rename`, { title });
    } catch (error: unknown) {
      if (axios.isAxiosError(error) && error.response?.status === 404) {
        return apiClient.patch<Task>(`/tasks/${id}`, { title });
      }
      throw error;
    }
  },

  nextNumber: (workspaceId: number) =>
    apiClient.get<NextTaskNumber>('/tasks/next-number', { params: { workspace_id: workspaceId } }),
};

// Workspace APIs
export const workspaceAPI = {
  list: () => apiClient.get<Workspace[]>('/workspaces'),
  create: (data: WorkspaceCreateInput) => apiClient.post<Workspace>('/workspaces', data),
  delete: (id: number) => apiClient.delete(`/workspaces/${id}`),
  resources: (id: number) => apiClient.get<WorkspaceResources>(`/workspaces/${id}/resources`),
  /** Fuzzy-search files in a workspace or task worktree for @mention autocomplete. */
  listFiles: (id: number, query: string, limit = 8, taskId?: number) =>
    apiClient.get<string[]>(`/workspaces/${id}/files`, {
      params: {
        query,
        limit,
        ...(taskId !== undefined ? { task_id: taskId } : {}),
      },
    }),
};

// Usage APIs
export const usageAPI = {
  get: () => apiClient.get<UsageStats>('/usage'),
};

// Log APIs
export const logAPI = {
  get: (runId: number) =>
    apiClient.get<LogEntry>(`/logs/${runId}`),

  streamURL: (runId: number) =>
    `${NORMALIZED_API_BASE}/logs/${runId}/stream`,
};

// Models APIs
export const modelsAPI = {
  list: (refresh?: boolean) =>
    apiClient.get<ModelsListResponse>('/models', { params: refresh ? { refresh: true } : {} }),
};

// Settings APIs
export const settingsAPI = {
  get: () => apiClient.get<AppSettings>('/settings'),
  update: (data: AppSettingsUpdateInput) => apiClient.put<AppSettings>('/settings', data),
};
