'use client';

import { Task, TaskStatus } from '@/lib/types';
import TaskCard from './TaskCard';

interface TaskBoardProps {
  tasks: Task[];
  workspaceId?: number;
  workspaceConcurrencyLimit?: number;
  onTaskDeleted?: () => void;
}

const statusColumns = [
  { status: TaskStatus.TODO, label: 'Queuing', bgColor: 'bg-slate-100' },
  { status: TaskStatus.RUNNING, label: 'Running', bgColor: 'bg-blue-100' },
  { status: TaskStatus.TO_BE_REVIEW, label: 'To be Review', bgColor: 'bg-amber-100' },
  { status: TaskStatus.DONE, label: 'Done', bgColor: 'bg-green-100' },
  { status: TaskStatus.FAILED, label: 'Failed', bgColor: 'bg-red-100' },
];

export default function TaskBoard({
  tasks,
  workspaceId,
  workspaceConcurrencyLimit,
  onTaskDeleted,
}: TaskBoardProps) {
  const displayTasks = workspaceId
    ? tasks.filter((t) => t.workspace_id === workspaceId)
    : tasks;

  const groupTasksByStatus = (items: Task[]) => {
    const grouped: Record<TaskStatus, Task[]> = {
      [TaskStatus.TODO]: [],
      [TaskStatus.RUNNING]: [],
      [TaskStatus.TO_BE_REVIEW]: [],
      [TaskStatus.DONE]: [],
      [TaskStatus.FAILED]: [],
    };

    items.forEach((task) => {
      if (grouped[task.status]) {
        grouped[task.status].push(task);
      } else {
        grouped[TaskStatus.FAILED].push(task);
      }
    });

    return grouped;
  };

  const groupedTasks = groupTasksByStatus(displayTasks);
  const runningCountByWorkspace = new Map<number, number>();
  groupedTasks[TaskStatus.RUNNING].forEach((task) => {
    runningCountByWorkspace.set(
      task.workspace_id,
      (runningCountByWorkspace.get(task.workspace_id) ?? 0) + 1,
    );
  });
  const effectiveLimit = Math.max(1, workspaceConcurrencyLimit ?? 1);

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-4">
      {statusColumns.map((column) => {
        const columnTasks = groupedTasks[column.status];
        return (
          <div key={column.status} className="flex flex-col">
            <div className={`${column.bgColor} rounded-t-lg px-4 py-3 border-b`}>
              <h3 className="font-semibold text-sm flex items-center justify-between">
                <span>{column.label}</span>
                <span className="text-xs bg-white/70 px-2 py-1 rounded-full">
                  {columnTasks.length}
                </span>
              </h3>
            </div>

            <div className="flex-1 bg-slate-50 rounded-b-lg p-3 flex flex-col gap-3 min-h-[120px] max-h-[600px] overflow-y-auto">
              {columnTasks.length === 0 ? (
                <div className="text-center text-sm text-muted-foreground py-8">
                  No tasks
                </div>
              ) : (
                columnTasks.map((task) => (
                  <TaskCard
                    key={task.id}
                    task={task}
                    isQueued={
                      column.status === TaskStatus.TODO &&
                      (runningCountByWorkspace.get(task.workspace_id) ?? 0) >= effectiveLimit
                    }
                    onDeleted={onTaskDeleted}
                  />
                ))
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
