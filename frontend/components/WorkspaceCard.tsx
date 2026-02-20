'use client';

import Link from 'next/link';
import { Workspace, TaskStatus, WorkspaceType } from '@/lib/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

interface WorkspaceCardProps {
  workspace: Workspace;
  taskCounts: Record<TaskStatus, number>;
}

const typeLabel: Record<WorkspaceType, string> = {
  [WorkspaceType.LOCAL]: 'Local',
  [WorkspaceType.SSH]: 'SSH',
  [WorkspaceType.SSH_CONTAINER]: 'SSH+Container',
};

export default function WorkspaceCard({ workspace, taskCounts }: WorkspaceCardProps) {
  const total = Object.values(taskCounts).reduce((a, b) => a + b, 0);

  return (
    <Link href={`/workspaces/${workspace.workspace_id}/board`}>
      <Card className="hover:shadow-md transition-shadow cursor-pointer h-full">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between gap-2">
            <CardTitle className="text-base truncate">{workspace.display_name}</CardTitle>
            <Badge variant="outline" className="text-xs shrink-0">
              {typeLabel[workspace.workspace_type]}
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground font-mono truncate">{workspace.path}</p>
        </CardHeader>
        <CardContent className="pt-0">
          {total === 0 ? (
            <p className="text-xs text-muted-foreground">No tasks yet</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {taskCounts[TaskStatus.TODO] > 0 && (
                <span className="text-xs bg-slate-100 text-slate-700 px-2 py-1 rounded-full">
                  Queuing: {taskCounts[TaskStatus.TODO]}
                </span>
              )}
              {taskCounts[TaskStatus.RUNNING] > 0 && (
                <span className="text-xs bg-blue-100 text-blue-700 px-2 py-1 rounded-full">
                  Running: {taskCounts[TaskStatus.RUNNING]}
                </span>
              )}
              {taskCounts[TaskStatus.TO_BE_REVIEW] > 0 && (
                <span className="text-xs bg-amber-100 text-amber-700 px-2 py-1 rounded-full">
                  To be Review: {taskCounts[TaskStatus.TO_BE_REVIEW]}
                </span>
              )}
              {taskCounts[TaskStatus.DONE] > 0 && (
                <span className="text-xs bg-green-100 text-green-700 px-2 py-1 rounded-full">
                  Done: {taskCounts[TaskStatus.DONE]}
                </span>
              )}
              {taskCounts[TaskStatus.FAILED] > 0 && (
                <span className="text-xs bg-red-100 text-red-700 px-2 py-1 rounded-full">
                  Failed: {taskCounts[TaskStatus.FAILED]}
                </span>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </Link>
  );
}
