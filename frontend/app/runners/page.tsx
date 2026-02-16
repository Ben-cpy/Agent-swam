'use client';

import { useEffect, useState } from 'react';
import useSWR from 'swr';
import { runnerAPI } from '@/lib/api';
import { Runner } from '@/lib/types';
import RunnerCard from '@/components/RunnerCard';

export default function RunnersPage() {
  const [runners, setRunners] = useState<Runner[]>([]);

  // Fetch runners with SWR auto-refresh every 10 seconds
  const { data, error, isLoading } = useSWR(
    '/runners',
    () => runnerAPI.list(),
    {
      refreshInterval: 10000,
      revalidateOnFocus: true,
    }
  );

  useEffect(() => {
    if (data?.data) {
      setRunners(data.data);
    }
  }, [data]);

  if (error) {
    return (
      <div className="text-center py-12">
        <h2 className="text-2xl font-bold text-red-600 mb-4">Error Loading Runners</h2>
        <p className="text-muted-foreground">{error.message}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold">Runners</h1>
        <p className="text-muted-foreground mt-1">
          Monitor the status and capabilities of task runners
        </p>
      </div>

      {/* Loading State */}
      {isLoading && runners.length === 0 && (
        <div className="text-center py-12">
          <p className="text-muted-foreground">Loading runners...</p>
        </div>
      )}

      {/* Empty State */}
      {!isLoading && runners.length === 0 && (
        <div className="text-center py-12 bg-slate-50 rounded-lg border-2 border-dashed">
          <h3 className="text-lg font-semibold mb-2">No runners available</h3>
          <p className="text-muted-foreground">
            No runners are currently registered in the system
          </p>
        </div>
      )}

      {/* Runners Grid */}
      {runners.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {runners.map((runner) => (
            <RunnerCard key={runner.runner_id} runner={runner} />
          ))}
        </div>
      )}
    </div>
  );
}
