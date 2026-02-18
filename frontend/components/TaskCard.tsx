'use client';

import Link from 'next/link';
import { Task, BackendType } from '@/lib/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { formatDistanceToNow } from 'date-fns';
import { parseUTCDate } from '@/lib/utils';

interface TaskCardProps {
  task: Task;
}

export default function TaskCard({ task }: TaskCardProps) {
  const getBackendIcon = (backend: BackendType) => {
    switch (backend) {
      case BackendType.CLAUDE_CODE:
        return '🤖';
      case BackendType.CODEX_CLI:
        return '⚡';
      default:
        return '🔧';
    }
  };

  const getBackendLabel = (backend: BackendType) => {
    switch (backend) {
      case BackendType.CLAUDE_CODE:
        return 'Claude Code';
      case BackendType.CODEX_CLI:
        return 'Codex CLI';
      default:
        return backend;
    }
  };

  return (
    <Link href={`/tasks/${task.id}`}>
      <Card className="hover:shadow-md transition-shadow cursor-pointer">
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-2">
            <CardTitle className="text-sm font-medium line-clamp-2">
              {task.title}
            </CardTitle>
            <span className="text-lg flex-shrink-0">
              {getBackendIcon(task.backend)}
            </span>
          </div>
        </CardHeader>
        <CardContent className="space-y-2">
          <Badge variant="outline" className="text-xs">
            {getBackendLabel(task.backend)}
          </Badge>
          <p className="text-xs text-muted-foreground">
            {formatDistanceToNow(parseUTCDate(task.created_at), { addSuffix: true })}
          </p>
        </CardContent>
      </Card>
    </Link>
  );
}
