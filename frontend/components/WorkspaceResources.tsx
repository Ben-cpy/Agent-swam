'use client';

import { useState, useEffect } from 'react';
import useSWR from 'swr';
import { workspaceAPI } from '@/lib/api';
import { GpuInfo, MemoryInfo } from '@/lib/types';

interface Props {
  workspaceId: number;
  gpuIndices?: string | null;
  onGpuIndicesChange?: (indices: string) => void;
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

function GpuRow({
  gpu,
  index,
  selected,
  isMultiGpu,
  onToggle,
}: {
  gpu: GpuInfo;
  index: number;
  selected: boolean;
  isMultiGpu: boolean;
  onToggle: () => void;
}) {
  const memPct = gpu.memory_total_mb > 0
    ? Math.round((gpu.memory_used_mb / gpu.memory_total_mb) * 100)
    : 0;

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs gap-2">
        <div className="flex items-center gap-1.5 min-w-0">
          {isMultiGpu && (
            <button
              onClick={onToggle}
              title={`GPU ${index}: click to ${selected ? 'deselect' : 'select'}`}
              className={`
                flex-shrink-0 px-1.5 py-0.5 rounded text-xs font-mono font-semibold border transition-colors
                ${selected
                  ? 'bg-blue-600 text-white border-blue-600'
                  : 'bg-white text-slate-500 border-slate-300 hover:border-blue-400'}
              `}
            >
              GPU {index}
            </button>
          )}
          <span className="text-muted-foreground truncate max-w-[140px]" title={gpu.name}>
            {gpu.name}
          </span>
        </div>
        <span className="font-mono text-xs flex-shrink-0">
          {gpu.memory_used_mb} / {gpu.memory_total_mb} MB ({memPct}%)
          {' · '}compute {gpu.utilization_pct}%
        </span>
      </div>
      <ProgressBar pct={memPct} />
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

export default function WorkspaceResources({ workspaceId, gpuIndices, onGpuIndicesChange }: Props) {
  const { data, error } = useSWR(
    `/workspaces/${workspaceId}/resources`,
    () => workspaceAPI.resources(workspaceId),
    { refreshInterval: 10000, revalidateOnFocus: false }
  );

  // Parse the current gpu_indices into a Set of selected indices
  const [selectedGpus, setSelectedGpus] = useState<Set<number>>(() => {
    if (!gpuIndices) return new Set();
    return new Set(gpuIndices.split(',').map((s) => parseInt(s.trim(), 10)).filter((n) => !isNaN(n)));
  });

  // Sync external gpuIndices changes
  useEffect(() => {
    if (!gpuIndices) {
      setSelectedGpus(new Set());
    } else {
      setSelectedGpus(new Set(gpuIndices.split(',').map((s) => parseInt(s.trim(), 10)).filter((n) => !isNaN(n))));
    }
  }, [gpuIndices]);

  if (error || !data) return null;

  const resources = data.data;
  const hasGpu = resources.gpu_available && resources.gpu && resources.gpu.length > 0;
  const hasMemory = resources.memory !== null;
  const isMultiGpu = !!(hasGpu && resources.gpu!.length > 1);

  if (!hasGpu && !hasMemory) return null;

  const handleGpuToggle = (index: number) => {
    if (!isMultiGpu || !onGpuIndicesChange) return;
    const next = new Set(selectedGpus);
    if (next.has(index)) {
      next.delete(index);
    } else {
      next.add(index);
    }
    setSelectedGpus(next);
    // Sort indices for consistent ordering
    const indicesStr = Array.from(next).sort((a, b) => a - b).join(',');
    onGpuIndicesChange(indicesStr);
  };

  return (
    <div className="flex flex-wrap gap-4 px-4 py-2 bg-slate-50 border rounded-lg text-sm">
      {/* GPU section */}
      <div className="flex-1 min-w-[220px] space-y-2">
        <div className="flex items-center gap-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">GPU</p>
          {isMultiGpu && (
            <span className="text-xs text-muted-foreground">
              (click to select for tasks
              {selectedGpus.size > 0 ? `: CUDA_VISIBLE_DEVICES=${Array.from(selectedGpus).sort((a, b) => a - b).join(',')}` : ': all'}
              )
            </span>
          )}
        </div>
        {resources.gpu_available && resources.gpu ? (
          resources.gpu.map((g, i) => (
            <GpuRow
              key={i}
              gpu={g}
              index={i}
              selected={isMultiGpu ? selectedGpus.has(i) : false}
              isMultiGpu={isMultiGpu}
              onToggle={() => handleGpuToggle(i)}
            />
          ))
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
