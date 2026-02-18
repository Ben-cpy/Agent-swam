'use client';

import useSWR from 'swr';
import { usageAPI } from '@/lib/api';
import { UsageStats } from '@/lib/types';

function SkeletonBox({ className }: { className?: string }) {
  return (
    <div className={`animate-pulse bg-slate-200 rounded ${className ?? ''}`} />
  );
}

export default function UsageSummary() {
  const { data, error, isLoading } = useSWR<UsageStats>(
    '/usage',
    () => usageAPI.get().then((r) => r.data),
    { refreshInterval: 30000, revalidateOnFocus: true }
  );

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-600">
        Failed to load usage data.
      </div>
    );
  }

  if (isLoading || !data) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="rounded-lg border bg-white p-4 space-y-2">
            <SkeletonBox className="h-4 w-24" />
            <SkeletonBox className="h-6 w-16" />
          </div>
        ))}
      </div>
    );
  }

  if (data.runs_count === 0) {
    return (
      <div className="rounded-lg border border-dashed bg-slate-50 p-6 text-center text-sm text-muted-foreground">
        No usage data yet
      </div>
    );
  }

  const claude = data.by_backend?.claude_code;
  const codex = data.by_backend?.codex_cli;

  return (
    <div className="space-y-3">
      <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
        Usage Summary
      </h2>

      {/* Top-level stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Total Runs" value={String(data.runs_count)} />
        <StatCard
          label="Total Cost"
          value={`$${data.total_cost_usd.toFixed(4)}`}
        />
        <StatCard
          label="Total Tokens"
          value={data.total_tokens.toLocaleString()}
        />
        <StatCard
          label="Input / Output"
          value={`${data.total_input_tokens.toLocaleString()} / ${data.total_output_tokens.toLocaleString()}`}
        />
      </div>

      {/* Per-backend breakdown */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {claude && (
          <BackendCard
            name="Claude Code"
            runs={claude.runs}
            cost={claude.cost_usd}
            tokens={claude.tokens}
            accentClass="border-l-purple-400"
          />
        )}
        {codex && (
          <BackendCard
            name="Codex CLI"
            runs={codex.runs}
            cost={codex.cost_usd}
            tokens={codex.tokens}
            accentClass="border-l-green-400"
          />
        )}
      </div>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border bg-white p-4">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-xl font-semibold">{value}</p>
    </div>
  );
}

function BackendCard({
  name,
  runs,
  cost,
  tokens,
  accentClass,
}: {
  name: string;
  runs: number;
  cost: number;
  tokens: number;
  accentClass: string;
}) {
  return (
    <div className={`rounded-lg border-l-4 border bg-white p-4 ${accentClass}`}>
      <p className="font-medium text-sm">{name}</p>
      <div className="mt-2 grid grid-cols-3 gap-2 text-xs text-muted-foreground">
        <div>
          <p>Runs</p>
          <p className="text-base font-semibold text-foreground">{runs}</p>
        </div>
        <div>
          <p>Cost (USD)</p>
          <p className="text-base font-semibold text-foreground">
            ${cost.toFixed(4)}
          </p>
        </div>
        <div>
          <p>Tokens</p>
          <p className="text-base font-semibold text-foreground">
            {tokens.toLocaleString()}
          </p>
        </div>
      </div>
    </div>
  );
}
