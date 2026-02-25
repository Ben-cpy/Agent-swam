'use client';

import { useParams, useRouter } from 'next/navigation';
import useSWR from 'swr';
import { taskAPI, workspaceAPI } from '@/lib/api';
import TaskBoard from '@/components/TaskBoard';
import WorkspaceResources from '@/components/WorkspaceResources';
import WorkspaceHealthBadge from '@/components/WorkspaceHealthBadge';
import WorkspaceNotes from '@/components/WorkspaceNotes';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { WorkspaceType } from '@/lib/types';

const typeLabel: Record<WorkspaceType, string> = {
  [WorkspaceType.LOCAL]: 'Local',
  [WorkspaceType.SSH]: 'SSH',
  [WorkspaceType.SSH_CONTAINER]: 'SSH+Container',
};

export default function WorkspaceBoardPage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = parseInt(params.id as string, 10);

  const { data: wsData, mutate: mutateWorkspace } = useSWR(
    '/workspaces',
    () => workspaceAPI.list(),
    { revalidateOnFocus: false }
  );
  const workspace = wsData?.data.find((w) => w.workspace_id === workspaceId) ?? null;

  const handleGpuIndicesChange = async (indices: string) => {
    try {
      await workspaceAPI.update(workspaceId, { gpu_indices: indices });
      await mutateWorkspace();
    } catch {
      // silently ignore - the UI will revert on next load
    }
  };

  const { data, error, isLoading, mutate } = useSWR(
    `/tasks?workspace_id=${workspaceId}`,
    () => taskAPI.list({ workspaceId }),
    { refreshInterval: 2000, revalidateOnFocus: true }
  );
  const tasks = data?.data ?? [];

  if (error) {
    return (
      <div className="text-center py-12">
        <h2 className="text-2xl font-bold text-red-600 mb-4">Error Loading Tasks</h2>
        <p className="text-muted-foreground mb-4">{error.message}</p>
        <Button onClick={() => router.push('/')}>Back to Workspaces</Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
            <button
              onClick={() => router.push('/')}
              className="hover:text-foreground transition-colors"
            >
              Workspaces
            </button>
            <span>/</span>
            <span className="flex items-center gap-1.5 text-foreground font-medium">
              {workspace && (
                <WorkspaceHealthBadge
                  workspaceId={workspace.workspace_id}
                  workspaceType={workspace.workspace_type}
                  refreshInterval={30000}
                />
              )}
              {workspace?.display_name ?? `Workspace ${workspaceId}`}
            </span>
            {workspace && (
              <Badge variant="outline" className="text-xs">
                {typeLabel[workspace.workspace_type]}
              </Badge>
            )}
          </div>
          {workspace && (
            <p className="text-xs text-muted-foreground font-mono">{workspace.path}</p>
          )}
        </div>
        <Link href={`/workspaces/${workspaceId}/tasks/new`}>
          <Button size="lg">+ New Task</Button>
        </Link>
      </div>

      <WorkspaceResources
        workspaceId={workspaceId}
        gpuIndices={workspace?.gpu_indices}
        onGpuIndicesChange={handleGpuIndicesChange}
      />

      <WorkspaceNotes workspaceId={workspaceId} initialNotes={workspace?.notes ?? null} />

      {isLoading && tasks.length === 0 && (
        <div className="text-center py-12">
          <p className="text-muted-foreground">Loading tasks...</p>
        </div>
      )}

      {!isLoading && tasks.length === 0 && (
        <div className="text-center py-12 bg-slate-50 rounded-lg border-2 border-dashed">
          <h3 className="text-lg font-semibold mb-2">No tasks yet</h3>
          <p className="text-muted-foreground mb-4">
            Create the first task for this workspace
          </p>
          <Link href={`/workspaces/${workspaceId}/tasks/new`}>
            <Button>Create Task</Button>
          </Link>
        </div>
      )}

      {tasks.length > 0 && (
        <TaskBoard
          tasks={tasks}
          workspaceId={workspaceId}
          workspaceConcurrencyLimit={workspace?.concurrency_limit}
          onTaskDeleted={mutate}
        />
      )}
    </div>
  );
}
