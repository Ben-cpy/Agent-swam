import axios from 'axios';
import {
  ApiMessage,
  LogEntry,
  ModelsListResponse,
  NextTaskNumber,
  Task,
  TaskCreateInput,
  TaskStatus,
  UsageStats,
  Workspace,
  WorkspaceCreateInput,
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
  list: (status?: TaskStatus) =>
    apiClient.get<Task[]>('/tasks', { params: status ? { status } : {} }),

  get: (id: number) =>
    apiClient.get<Task>(`/tasks/${id}`),

  create: (data: TaskCreateInput) =>
    apiClient.post<Task>('/tasks', data),

  cancel: (id: number) =>
    apiClient.post<ApiMessage>(`/tasks/${id}/cancel`),

  retry: (id: number) =>
    apiClient.post<Task>(`/tasks/${id}/retry`),

  delete: (id: number) =>
    apiClient.delete<ApiMessage>(`/tasks/${id}`),

  nextNumber: (workspaceId: number) =>
    apiClient.get<NextTaskNumber>('/tasks/next-number', { params: { workspace_id: workspaceId } }),
};

// Workspace APIs
export const workspaceAPI = {
  list: () => apiClient.get<Workspace[]>('/workspaces'),
  create: (data: WorkspaceCreateInput) => apiClient.post<Workspace>('/workspaces', data),
  delete: (id: number) => apiClient.delete(`/workspaces/${id}`),
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
