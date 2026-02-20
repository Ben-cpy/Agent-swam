'use client';

import useSWR from 'swr';
import { workspaceAPI } from '@/lib/api';
import { GpuInfo, MemoryInfo } from '@/lib/types';

interface Props {
  workspaceId: number;
}

function ProgressBar({ pct }: { pct: number }) {
  return (
    <div className="h-1.5 w-full bg-slate-200 rounded-full overflow-hidden">
      <div
        className="h-full bg-blue-500 rounded-full transition-all"
        style={{ width: `${Math.min(pct, 100)}%` }}
      />
    </div>
  );
}

function GpuRow({ gpu }: { gpu: GpuInfo }) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted-foreground truncate max-w-[160px]" title={gpu.name}>
          {gpu.name}
        </span>
        <span className="font-mono text-xs">
          {gpu.memory_used_mb} / {gpu.memory_total_mb} MB &bull; {gpu.utilization_pct}%
        </span>
      </div>
      <ProgressBar pct={gpu.utilization_pct} />
    </div>
  );
}

function MemoryPanel({ memory }: { memory: MemoryInfo }) {
  const totalGb = (memory.total_mb / 1024).toFixed(1);
  const usedGb = (memory.used_mb / 1024).toFixed(1);
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted-foreground">RAM</span>
        <span className="font-mono text-xs">
          {usedGb} / {totalGb} GB &bull; {memory.used_pct}%
        </span>
      </div>
      <ProgressBar pct={memory.used_pct} />
    </div>
  );
}

export default function WorkspaceResources({ workspaceId }: Props) {
  const { data, error } = useSWR(
    `/workspaces/${workspaceId}/resources`,
    () => workspaceAPI.resources(workspaceId),
    { refreshInterval: 10000, revalidateOnFocus: false }
  );

  if (error || !data) return null;

  const resources = data.data;
  const hasGpu = resources.gpu_available && resources.gpu && resources.gpu.length > 0;
  const hasMemory = resources.memory !== null;

  if (!hasGpu && !hasMemory) return null;

  return (
    <div className="flex flex-wrap gap-4 px-4 py-2 bg-slate-50 border rounded-lg text-sm">
      {/* GPU section */}
      <div className="flex-1 min-w-[220px] space-y-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">GPU</p>
        {resources.gpu_available && resources.gpu ? (
          resources.gpu.map((g, i) => <GpuRow key={i} gpu={g} />)
        ) : (
          <p className="text-xs text-muted-foreground">Not available</p>
        )}
      </div>

      {/* Memory section */}
      {hasMemory && resources.memory && (
        <div className="flex-1 min-w-[220px] space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Memory</p>
          <MemoryPanel memory={resources.memory} />
        </div>
      )}
    </div>
  );
}
