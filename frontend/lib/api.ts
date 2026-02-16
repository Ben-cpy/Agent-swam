import axios from 'axios';
import {
  ApiMessage,
  LogEntry,
  Runner,
  Task,
  TaskCreateInput,
  TaskStatus,
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
};

// Workspace APIs
export const workspaceAPI = {
  list: () => apiClient.get<Workspace[]>('/workspaces'),
  create: (data: WorkspaceCreateInput) => apiClient.post<Workspace>('/workspaces', data),
};

// Runner APIs
export const runnerAPI = {
  list: () => apiClient.get<Runner[]>('/runners'),
};

// Log APIs
export const logAPI = {
  get: (runId: number) =>
    apiClient.get<LogEntry>(`/logs/${runId}`),

  streamURL: (runId: number) =>
    `${NORMALIZED_API_BASE}/logs/${runId}/stream`,
};
