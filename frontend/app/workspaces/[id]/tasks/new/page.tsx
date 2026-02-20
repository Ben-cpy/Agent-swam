'use client';

import { useParams, useRouter } from 'next/navigation';
import useSWR from 'swr';
import { workspaceAPI } from '@/lib/api';
import TaskForm from '@/components/TaskForm';

export default function WorkspaceNewTaskPage() {
  const params = useParams();
  const router = useRouter();
  const workspaceId = parseInt(params.id as string, 10);

  const { data: wsData } = useSWR(
    '/workspaces',
    () => workspaceAPI.list(),
    { revalidateOnFocus: false }
  );
  const workspace = wsData?.data.find((w) => w.workspace_id === workspaceId) ?? null;

  return (
    <div className="max-w-2xl mx-auto">
      <div className="mb-6">
        <div className="flex items-center gap-2 text-sm text-muted-foreground mb-3">
          <button
            onClick={() => router.push('/')}
            className="hover:text-foreground transition-colors"
          >
            Workspaces
          </button>
          <span>/</span>
          <button
            onClick={() => router.push(`/workspaces/${workspaceId}/board`)}
            className="hover:text-foreground transition-colors"
          >
            {workspace?.display_name ?? `Workspace ${workspaceId}`}
          </button>
          <span>/</span>
          <span className="text-foreground font-medium">New Task</span>
        </div>
        <h1 className="text-3xl font-bold">New Task</h1>
        <p className="text-muted-foreground mt-1">Create a new AI task to execute</p>
      </div>
      <TaskForm lockedWorkspaceId={workspaceId} />
    </div>
  );
}
