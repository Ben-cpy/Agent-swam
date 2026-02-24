'use client';

import useSWR from 'swr';
import { workspaceAPI } from '@/lib/api';
import { WorkspaceType } from '@/lib/types';
import { CheckCircle2, XCircle, AlertCircle, Loader2 } from 'lucide-react';

interface WorkspaceHealthBadgeProps {
  workspaceId: number;
  workspaceType: WorkspaceType;
  /** Refresh interval in ms. Default: 30 000 (30 s). */
  refreshInterval?: number;
  /** Extra CSS classes for the wrapper span. */
  className?: string;
}

export default function WorkspaceHealthBadge({
  workspaceId,
  workspaceType,
  refreshInterval = 30000,
  className = '',
}: WorkspaceHealthBadgeProps) {
  // Only poll for SSH workspaces by default; local workspaces rarely change.
  const effectiveInterval =
    workspaceType === WorkspaceType.LOCAL ? 60000 : refreshInterval;

  const { data, isLoading } = useSWR(
    `/workspaces/${workspaceId}/health`,
    () => workspaceAPI.health(workspaceId),
    {
      refreshInterval: effectiveInterval,
      revalidateOnFocus: false,
      // Don't block initial render
      suspense: false,
    },
  );

  if (isLoading || !data) {
    return (
      <span className={`inline-flex items-center ${className}`} title="Checking…">
        <Loader2 className="w-3.5 h-3.5 text-muted-foreground animate-spin" />
      </span>
    );
  }

  const health = data.data;

  if (!health.reachable) {
    return (
      <span
        className={`inline-flex items-center ${className}`}
        title={`Unreachable: ${health.message}`}
      >
        <XCircle className="w-3.5 h-3.5 text-red-500" />
      </span>
    );
  }

  if (!health.is_git) {
    return (
      <span
        className={`inline-flex items-center ${className}`}
        title={`Reachable but not a git repo: ${health.message}`}
      >
        <AlertCircle className="w-3.5 h-3.5 text-amber-500" />
      </span>
    );
  }

  return (
    <span
      className={`inline-flex items-center ${className}`}
      title={`Healthy: ${health.message}`}
    >
      <CheckCircle2 className="w-3.5 h-3.5 text-green-500" />
    </span>
  );
}
