'use client';

import { Task, TaskStatus } from '@/lib/types';
import TaskCard from './TaskCard';

interface TaskBoardProps {
  tasks: Task[];
}

const statusColumns = [
  { status: TaskStatus.TODO, label: 'Queuing', bgColor: 'bg-slate-100' },
  { status: TaskStatus.RUNNING, label: 'Running', bgColor: 'bg-blue-100' },
  { status: TaskStatus.DONE, label: 'Done', bgColor: 'bg-green-100' },
  { status: TaskStatus.FAILED, label: 'Failed', bgColor: 'bg-red-100' },
];

export default function TaskBoard({ tasks }: TaskBoardProps) {
  const groupTasksByStatus = (tasks: Task[]) => {
    const grouped: Record<TaskStatus, Task[]> = {
      [TaskStatus.TODO]: [],
      [TaskStatus.RUNNING]: [],
      [TaskStatus.DONE]: [],
      [TaskStatus.FAILED]: [],
    };

    tasks.forEach((task) => {
      if (grouped[task.status]) {
        grouped[task.status].push(task);
      } else {
        grouped[TaskStatus.FAILED].push(task);
      }
    });

    return grouped;
  };

  const groupedTasks = groupTasksByStatus(tasks);

  // Workspaces that currently have a RUNNING task — TODO tasks for these are "queued"
  const busyWorkspaceIds = new Set(
    groupedTasks[TaskStatus.RUNNING].map((t) => t.workspace_id)
  );

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      {statusColumns.map((column) => {
        const columnTasks = groupedTasks[column.status];
        return (
          <div key={column.status} className="flex flex-col">
            {/* Column Header */}
            <div className={`${column.bgColor} rounded-t-lg px-4 py-3 border-b`}>
              <h3 className="font-semibold text-sm flex items-center justify-between">
                <span>{column.label}</span>
                <span className="text-xs bg-white/70 px-2 py-1 rounded-full">
                  {columnTasks.length}
                </span>
              </h3>
            </div>

            {/* Column Content */}
            <div className="flex-1 bg-slate-50 rounded-b-lg p-3 space-y-3 min-h-[120px] max-h-[600px] overflow-y-auto">
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
                      busyWorkspaceIds.has(task.workspace_id)
                    }
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
