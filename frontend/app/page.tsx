'use client';

import useSWR from 'swr';
import { taskAPI } from '@/lib/api';
import TaskBoard from '@/components/TaskBoard';
import UsageSummary from '@/components/UsageSummary';
import Link from 'next/link';
import { Button } from '@/components/ui/button';

export default function Home() {
  // Fetch tasks with SWR auto-refresh every 3 seconds
  const { data, error, isLoading, mutate } = useSWR(
    '/tasks',
    () => taskAPI.list(),
    {
      refreshInterval: 2000,
      revalidateOnFocus: true,
    }
  );
  const tasks = data?.data ?? [];

  if (error) {
    return (
      <div className="text-center py-12">
        <h2 className="text-2xl font-bold text-red-600 mb-4">Error Loading Tasks</h2>
        <p className="text-muted-foreground">{error.message}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Usage Summary */}
      <UsageSummary />

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Task Board</h1>
          <p className="text-muted-foreground mt-1">
            Manage and monitor your AI tasks
          </p>
        </div>
        <Link href="/tasks/new">
          <Button size="lg">+ New Task</Button>
        </Link>
      </div>

      {/* Loading State */}
      {isLoading && tasks.length === 0 && (
        <div className="text-center py-12">
          <p className="text-muted-foreground">Loading tasks...</p>
        </div>
      )}

      {/* Empty State */}
      {!isLoading && tasks.length === 0 && (
        <div className="text-center py-12 bg-slate-50 rounded-lg border-2 border-dashed">
          <h3 className="text-lg font-semibold mb-2">No tasks yet</h3>
          <p className="text-muted-foreground mb-4">
            Create your first task to get started
          </p>
          <Link href="/tasks/new">
            <Button>Create Task</Button>
          </Link>
        </div>
      )}

      {/* Task Board */}
      {tasks.length > 0 && <TaskBoard tasks={tasks} onTaskDeleted={mutate} />}
    </div>
  );
}
