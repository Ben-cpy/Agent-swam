'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { Task, BackendType, TaskStatus } from '@/lib/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { formatDistanceToNow } from 'date-fns';
import { parseUTCDate } from '@/lib/utils';

interface TaskCardProps {
  task: Task;
  isQueued?: boolean;
}

function formatElapsed(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) {
    return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  }
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export default function TaskCard({ task, isQueued = false }: TaskCardProps) {
  const [elapsed, setElapsed] = useState<number | null>(null);

  useEffect(() => {
    if (task.status !== TaskStatus.RUNNING) {
      setElapsed(null);
      return;
    }

    const startMs = task.run_started_at
      ? parseUTCDate(task.run_started_at).getTime()
      : parseUTCDate(task.updated_at).getTime();

    const tick = () => setElapsed(Math.floor((Date.now() - startMs) / 1000));
    tick();
    const interval = setInterval(tick, 1000);
    return () => clearInterval(interval);
  }, [task.status, task.run_started_at, task.updated_at]);

  const getBackendIcon = (backend: BackendType) => {
    switch (backend) {
      case BackendType.CLAUDE_CODE:
        return <img src="/Claude_AI_symbol.svg" alt="Claude" className="w-5 h-5" />;
      case BackendType.CODEX_CLI:
        return <img src="/ChatGPT_logo.svg" alt="Codex" className="w-5 h-5" />;
      default:
        return <span className="text-xs font-semibold">AI</span>;
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
      <Card className="py-3 hover:shadow-md transition-shadow cursor-pointer">
        <CardHeader className="pb-2">
          <div className="flex items-start justify-between gap-2">
            <CardTitle className="text-sm font-medium line-clamp-2">
              {task.title}
            </CardTitle>
            <span className="flex-shrink-0 flex items-center justify-center w-7 h-7">
              {getBackendIcon(task.backend)}
            </span>
          </div>
        </CardHeader>
        <CardContent className="pt-0 space-y-1">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant="outline" className="text-xs">
              {getBackendLabel(task.backend)}
            </Badge>
            {isQueued && (
              <Badge variant="secondary" className="text-xs bg-gray-200 text-gray-600">
                Queued
              </Badge>
            )}
            {task.status === TaskStatus.RUNNING && elapsed !== null && (
              <span className="text-xs font-mono text-blue-600">
                {formatElapsed(elapsed)}
              </span>
            )}
          </div>
          <p className="text-xs text-muted-foreground">
            {formatDistanceToNow(parseUTCDate(task.created_at), { addSuffix: true })}
          </p>
        </CardContent>
      </Card>
    </Link>
  );
}
