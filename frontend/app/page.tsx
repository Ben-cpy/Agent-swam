'use client';

import useSWR from 'swr';
import { taskAPI, workspaceAPI } from '@/lib/api';
import { TaskStatus } from '@/lib/types';
import WorkspaceCard from '@/components/WorkspaceCard';
import UsageSummary from '@/components/UsageSummary';
import Link from 'next/link';
import { Button } from '@/components/ui/button';

export default function Home() {
  const { data: wsData, error: wsError } = useSWR(
    '/workspaces',
    () => workspaceAPI.list(),
    { refreshInterval: 10000, revalidateOnFocus: true }
  );
  const { data: taskData } = useSWR(
    '/tasks',
    () => taskAPI.list(),
    { refreshInterval: 2000, revalidateOnFocus: true }
  );

  const workspaces = wsData?.data ?? [];
  const tasks = taskData?.data ?? [];

  // Compute per-workspace task counts
  const countsByWorkspace = Object.fromEntries(
    workspaces.map((ws) => {
      const wsTasks = tasks.filter((t) => t.workspace_id === ws.workspace_id);
      return [
        ws.workspace_id,
        {
          [TaskStatus.TODO]: wsTasks.filter((t) => t.status === TaskStatus.TODO).length,
          [TaskStatus.RUNNING]: wsTasks.filter((t) => t.status === TaskStatus.RUNNING).length,
          [TaskStatus.DONE]: wsTasks.filter((t) => t.status === TaskStatus.DONE).length,
          [TaskStatus.FAILED]: wsTasks.filter((t) => t.status === TaskStatus.FAILED).length,
        },
      ];
    })
  );

  if (wsError) {
    return (
      <div className="text-center py-12">
        <h2 className="text-2xl font-bold text-red-600 mb-4">Error Loading Workspaces</h2>
        <p className="text-muted-foreground">{wsError.message}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <UsageSummary />

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Workspaces</h1>
          <p className="text-muted-foreground mt-1">
            Select a workspace to view its task board
          </p>
        </div>
        <Link href="/tasks/new">
          <Button size="lg">+ New Task</Button>
        </Link>
      </div>

      {!wsData && (
        <div className="text-center py-12">
          <p className="text-muted-foreground">Loading workspaces...</p>
        </div>
      )}

      {wsData && workspaces.length === 0 && (
        <div className="text-center py-12 bg-slate-50 rounded-lg border-2 border-dashed">
          <h3 className="text-lg font-semibold mb-2">No workspaces configured</h3>
          <p className="text-muted-foreground mb-4">
            Register a workspace to start creating tasks
          </p>
          <Link href="/workspaces">
            <Button>Set Up Workspaces</Button>
          </Link>
        </div>
      )}

      {workspaces.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {workspaces.map((ws) => (
            <WorkspaceCard
              key={ws.workspace_id}
              workspace={ws}
              taskCounts={
                countsByWorkspace[ws.workspace_id] ?? {
                  [TaskStatus.TODO]: 0,
                  [TaskStatus.RUNNING]: 0,
                  [TaskStatus.DONE]: 0,
                  [TaskStatus.FAILED]: 0,
                }
              }
            />
          ))}
        </div>
      )}
    </div>
  );
}
