'use client';

import { useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import useSWR from 'swr';
import axios from 'axios';
import { taskAPI } from '@/lib/api';
import { ApiErrorBody, BackendType, TaskStatus } from '@/lib/types';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import LogStream from '@/components/LogStream';
import { formatDistanceToNow } from 'date-fns';

function getErrorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError<ApiErrorBody>(error)) {
    return error.response?.data?.detail || error.message || fallback;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return fallback;
}

export default function TaskDetailPage() {
  const params = useParams();
  const router = useRouter();
  const taskId = parseInt(params.id as string, 10);
  const [actionLoading, setActionLoading] = useState(false);

  // Fetch task with auto-refresh every 3 seconds
  const { data, error, isLoading, mutate } = useSWR(
    `/tasks/${taskId}`,
    () => taskAPI.get(taskId),
    {
      refreshInterval: 3000,
      revalidateOnFocus: true,
    }
  );
  const task = data?.data ?? null;

  const handleCancel = async () => {
    if (!confirm('Are you sure you want to cancel this task?')) {
      return;
    }

    setActionLoading(true);
    try {
      await taskAPI.cancel(taskId);
      mutate(); // Refresh task data
    } catch (error: unknown) {
      alert(`Failed to cancel task: ${getErrorMessage(error, 'Unknown error')}`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleRetry = async () => {
    setActionLoading(true);
    try {
      const response = await taskAPI.retry(taskId);
      const newTaskId = response.data.id;
      // Redirect to the new task
      router.push(`/tasks/${newTaskId}`);
    } catch (error: unknown) {
      alert(`Failed to retry task: ${getErrorMessage(error, 'Unknown error')}`);
      setActionLoading(false);
    }
  };

  const getStatusBadge = (status: TaskStatus) => {
    const classNames: Record<TaskStatus, string> = {
      [TaskStatus.TODO]: 'bg-slate-100 text-slate-800',
      [TaskStatus.RUNNING]: 'bg-blue-500 text-white',
      [TaskStatus.DONE]: 'bg-green-500 text-white',
      [TaskStatus.FAILED]: 'bg-red-500 text-white',
      [TaskStatus.CANCELLED]: 'bg-gray-400 text-white',
    };
    return <Badge className={classNames[status]}>{status}</Badge>;
  };

  const getBackendLabel = (backend: BackendType) => {
    return backend === BackendType.CLAUDE_CODE ? 'Claude Code' : 'Codex CLI';
  };

  if (error) {
    return (
      <div className="text-center py-12">
        <h2 className="text-2xl font-bold text-red-600 mb-4">Error Loading Task</h2>
        <p className="text-muted-foreground mb-4">{error.message}</p>
        <Button onClick={() => router.push('/')}>Back to Board</Button>
      </div>
    );
  }

  if (isLoading || !task) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">Loading task...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <h1 className="text-3xl font-bold">{task.title}</h1>
            {getStatusBadge(task.status)}
          </div>
          <p className="text-muted-foreground">
            Task #{task.id} - Created{' '}
            {formatDistanceToNow(new Date(task.created_at), { addSuffix: true })}
          </p>
        </div>
        <div className="flex gap-2">
          {task.status === TaskStatus.RUNNING && (
            <Button
              variant="destructive"
              onClick={handleCancel}
              disabled={actionLoading}
            >
              Cancel Task
            </Button>
          )}
          {task.status === TaskStatus.FAILED && (
            <Button onClick={handleRetry} disabled={actionLoading}>
              Retry Task
            </Button>
          )}
          <Button variant="outline" onClick={() => router.push('/')}>
            Back to Board
          </Button>
        </div>
      </div>

      {/* Task Details */}
      <Card>
        <CardHeader>
          <CardTitle>Task Details</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="text-sm font-medium text-muted-foreground">
              Backend
            </label>
            <p className="mt-1">{getBackendLabel(task.backend)}</p>
          </div>
          <div>
            <label className="text-sm font-medium text-muted-foreground">
              Workspace ID
            </label>
            <p className="mt-1">{task.workspace_id}</p>
          </div>
          <div>
            <label className="text-sm font-medium text-muted-foreground">
              Prompt
            </label>
            <div className="mt-1 bg-slate-50 p-4 rounded-lg whitespace-pre-wrap font-mono text-sm">
              {task.prompt}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium text-muted-foreground">
                Created At
              </label>
              <p className="mt-1 text-sm">
                {new Date(task.created_at).toLocaleString()}
              </p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">
                Updated At
              </label>
              <p className="mt-1 text-sm">
                {new Date(task.updated_at).toLocaleString()}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Logs */}
      {task.run_id && <LogStream runId={task.run_id} />}
      {!task.run_id && task.status === TaskStatus.TODO && (
        <Card>
          <CardContent className="py-12 text-center">
            <p className="text-muted-foreground">
              Task is waiting to be executed. Logs will appear here once execution starts.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
