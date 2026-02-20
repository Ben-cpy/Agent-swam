'use client';

import { useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import useSWR from 'swr';
import axios from 'axios';
import { taskAPI, workspaceAPI } from '@/lib/api';
import { ApiErrorBody, BackendType, TaskStatus, WorkspaceType } from '@/lib/types';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import LogStream from '@/components/LogStream';
import { formatDistanceToNow } from 'date-fns';
import { parseUTCDate } from '@/lib/utils';
import { ArrowLeft, GitMerge } from 'lucide-react';

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
  const [continuePrompt, setContinuePrompt] = useState('');
  const [continueLoading, setContinueLoading] = useState(false);
  const [mergeLoading, setMergeLoading] = useState(false);

  // Fetch task with auto-refresh every 2 seconds
  const { data, error, isLoading, mutate } = useSWR(
    `/tasks/${taskId}`,
    () => taskAPI.get(taskId),
    {
      refreshInterval: 2000,
      revalidateOnFocus: true,
    }
  );
  const task = data?.data ?? null;

  // Fetch all workspaces to determine workspace type for the current task
  const { data: workspacesData } = useSWR(
    '/workspaces',
    () => workspaceAPI.list(),
    { revalidateOnFocus: false }
  );
  const workspaces = workspacesData?.data ?? [];
  const taskWorkspace = task ? workspaces.find((w) => w.workspace_id === task.workspace_id) : null;
  const isSSHWorkspace =
    taskWorkspace?.workspace_type === WorkspaceType.SSH ||
    taskWorkspace?.workspace_type === WorkspaceType.SSH_CONTAINER;

  const handleCancel = async () => {
    if (!confirm('Are you sure you want to cancel this task?')) {
      return;
    }

    setActionLoading(true);
    try {
      await taskAPI.cancel(taskId);
      mutate();
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
      router.push(`/tasks/${newTaskId}`);
    } catch (error: unknown) {
      alert(`Failed to retry task: ${getErrorMessage(error, 'Unknown error')}`);
      setActionLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm('Are you sure you want to delete this task?')) {
      return;
    }

    setActionLoading(true);
    try {
      await taskAPI.delete(taskId);
      router.push(task ? `/workspaces/${task.workspace_id}/board` : '/');
    } catch (error: unknown) {
      alert(`Failed to delete task: ${getErrorMessage(error, 'Unknown error')}`);
      setActionLoading(false);
    }
  };

  const handleContinue = async () => {
    if (!continuePrompt.trim()) return;
    setContinueLoading(true);
    try {
      await taskAPI.continue(taskId, { prompt: continuePrompt });
      setContinuePrompt('');
      mutate();
    } catch (error: unknown) {
      alert(`Failed to continue task: ${getErrorMessage(error, 'Unknown error')}`);
    } finally {
      setContinueLoading(false);
    }
  };

  const handleMerge = async () => {
    if (!confirm('Merge this task branch into base branch and mark task as DONE?')) {
      return;
    }

    setMergeLoading(true);
    try {
      await taskAPI.merge(taskId);
      mutate();
    } catch (error: unknown) {
      alert(`Failed to merge task: ${getErrorMessage(error, 'Unknown error')}`);
    } finally {
      setMergeLoading(false);
    }
  };

  const getStatusBadge = (status: TaskStatus) => {
    const classNames: Record<TaskStatus, string> = {
      [TaskStatus.TODO]: 'bg-slate-100 text-slate-800',
      [TaskStatus.RUNNING]: 'bg-blue-500 text-white',
      [TaskStatus.TO_BE_REVIEW]: 'bg-amber-500 text-white',
      [TaskStatus.DONE]: 'bg-green-500 text-white',
      [TaskStatus.FAILED]: 'bg-red-500 text-white',
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
        <Button onClick={() => router.push('/')}>Back to Workspaces</Button>
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

  const canMerge = task.status === TaskStatus.TO_BE_REVIEW && !!task.worktree_path;
  const canContinue =
    task.status === TaskStatus.TO_BE_REVIEW ||
    task.status === TaskStatus.DONE ||
    task.status === TaskStatus.FAILED;
  const goToWorkspaceBoard = () => {
    router.push(`/workspaces/${task.workspace_id}/board`);
  };

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
            {formatDistanceToNow(parseUTCDate(task.created_at), { addSuffix: true })}
          </p>
        </div>
        <div className="flex gap-2 flex-wrap justify-end">
          {isSSHWorkspace && (
            <Button
              variant="outline"
              onClick={() => router.push(`/tasks/${taskId}/terminal`)}
            >
              Open Terminal
            </Button>
          )}
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
          {task.status !== TaskStatus.RUNNING && (
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={actionLoading}
            >
              Delete Task
            </Button>
          )}
          {canMerge && (
            <Button
              onClick={handleMerge}
              disabled={mergeLoading}
              className="bg-[#2da44e] hover:bg-[#2c974b] text-white"
            >
              <GitMerge className="w-4 h-4 mr-1.5" />
              {mergeLoading ? 'Merging...' : 'Merge'}
            </Button>
          )}
          <Button
            variant="secondary"
            className="bg-slate-100 text-slate-600 hover:bg-slate-200 hover:text-slate-700"
            onClick={goToWorkspaceBoard}
          >
            <ArrowLeft className="w-4 h-4 mr-1.5" />
            Back to Workspace
          </Button>
        </div>
      </div>

      {/* Task Details */}
      <Card>
        <CardHeader>
          <CardTitle>Task Details</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Row 1: Backend | Base Branch */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium text-muted-foreground">Backend</label>
              <p className="mt-1">{getBackendLabel(task.backend)}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Base Branch</label>
              <p className="mt-1">{task.branch_name || '-'}</p>
            </div>
          </div>

          {/* Row 2: Workspace */}
          <div>
            <label className="text-sm font-medium text-muted-foreground">Workspace</label>
            <p className="mt-1">
              {taskWorkspace ? (
                <>
                  {taskWorkspace.display_name}{' '}
                  <span className="text-muted-foreground text-xs">#{task.workspace_id}</span>
                </>
              ) : (
                task.workspace_id
              )}
            </p>
          </div>

          {/* Row 3: Worktree Path */}
          <div>
            <label className="text-sm font-medium text-muted-foreground">Worktree Path</label>
            <p className="mt-1 break-all font-mono text-sm">{task.worktree_path || '-'}</p>
          </div>

          {/* Row 4: Created At | Updated At */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium text-muted-foreground">Created At</label>
              <p className="mt-1 text-sm">{parseUTCDate(task.created_at).toLocaleString()}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground">Updated At</label>
              <p className="mt-1 text-sm">{parseUTCDate(task.updated_at).toLocaleString()}</p>
            </div>
          </div>

          {/* Row 5: Prompt */}
          <div>
            <label className="text-sm font-medium text-muted-foreground">Prompt</label>
            <div className="mt-1 bg-slate-50 p-4 rounded-lg whitespace-pre-wrap font-mono text-sm">
              {task.prompt}
            </div>
          </div>

          {/* Row 6: API Usage (conditional) */}
          {task.usage_json && (
            task.status === TaskStatus.TO_BE_REVIEW ||
            task.status === TaskStatus.DONE ||
            task.status === TaskStatus.FAILED
          ) && (() => {
            try {
              const usage = JSON.parse(task.usage_json);
              const isClaudeCode = 'cost_usd' in usage || 'total_cost_usd' in usage || 'num_turns' in usage;
              return (
                <div>
                  <label className="text-sm font-medium text-muted-foreground">
                    API Usage
                  </label>
                  <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-sm">
                    {isClaudeCode ? (
                      <>
                        {(usage.cost_usd != null || usage.total_cost_usd != null) && (
                          <span>
                            Cost:{' '}
                            <span className="font-medium">
                              ${((usage.total_cost_usd ?? usage.cost_usd) as number).toFixed(4)}
                            </span>
                          </span>
                        )}
                        {usage.num_turns != null && (
                          <span>
                            Turns: <span className="font-medium">{usage.num_turns}</span>
                          </span>
                        )}
                        {usage.duration_ms != null && (
                          <span>
                            Duration:{' '}
                            <span className="font-medium">
                              {((usage.duration_ms as number) / 1000).toFixed(1)}s
                            </span>
                          </span>
                        )}
                      </>
                    ) : (
                      <>
                        {usage.input_tokens != null && (
                          <span>
                            Input: <span className="font-medium">{(usage.input_tokens as number).toLocaleString()} tokens</span>
                          </span>
                        )}
                        {usage.output_tokens != null && (
                          <span>
                            Output: <span className="font-medium">{(usage.output_tokens as number).toLocaleString()} tokens</span>
                          </span>
                        )}
                        {usage.total_tokens != null && (
                          <span>
                            Total: <span className="font-medium">{(usage.total_tokens as number).toLocaleString()} tokens</span>
                          </span>
                        )}
                      </>
                    )}
                  </div>
                </div>
              );
            } catch {
              return null;
            }
          })()}
        </CardContent>
      </Card>

      {/* Logs */}
      {task.run_id && (
        <LogStream
          runId={task.run_id}
          onComplete={() => mutate()}
          headerActions={(
            <div className="flex items-center gap-2">
              {canMerge && (
                <Button
                  size="sm"
                  onClick={handleMerge}
                  disabled={mergeLoading}
                  className="bg-[#2da44e] hover:bg-[#2c974b] text-white"
                >
                  <GitMerge className="w-4 h-4 mr-1.5" />
                  {mergeLoading ? 'Merging...' : 'Merge'}
                </Button>
              )}
              <Button
                size="sm"
                variant="secondary"
                className="bg-slate-100 text-slate-600 hover:bg-slate-200 hover:text-slate-700"
                onClick={goToWorkspaceBoard}
              >
                <ArrowLeft className="w-4 h-4 mr-1.5" />
                Back to Workspace
              </Button>
            </div>
          )}
        />
      )}
      {!task.run_id && task.status === TaskStatus.TODO && (
        <Card>
          <CardContent className="py-12 text-center">
            <p className="text-muted-foreground">
              Task is waiting to be executed. Logs will appear here once execution starts.
            </p>
          </CardContent>
        </Card>
      )}

      {/* Continue / Additional Instructions */}
      {canContinue && (
        <Card>
          <CardHeader>
            <CardTitle>Continue / Additional Instructions</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Send new instructions to continue work in the same worktree. The task will be re-queued and executed with the new prompt.
            </p>
            <div className="space-y-2">
              <Label htmlFor="continue-prompt">New Instructions</Label>
              <Textarea
                id="continue-prompt"
                value={continuePrompt}
                onChange={(e) => setContinuePrompt(e.target.value)}
                placeholder="Describe what else should be done or corrected..."
                rows={4}
              />
            </div>
            <Button
              onClick={handleContinue}
              disabled={continueLoading || !continuePrompt.trim()}
            >
              {continueLoading ? 'Sending...' : 'Send Instructions'}
            </Button>
          </CardContent>
        </Card>
      )}

      <div className="flex justify-end">
        <Button
          variant="secondary"
          className="bg-slate-100 text-slate-600 hover:bg-slate-200 hover:text-slate-700"
          onClick={goToWorkspaceBoard}
        >
          <ArrowLeft className="w-4 h-4 mr-1.5" />
          Back to Workspace
        </Button>
      </div>
    </div>
  );
}
