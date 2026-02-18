'use client';

import useSWR from 'swr';
import { usageAPI } from '@/lib/api';
import { ProviderUsage } from '@/lib/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

function UsageCard({ title, provider }: { title: string; provider: ProviderUsage }) {
  const quotaBadgeClass =
    provider.quota_state === 'OK'
      ? 'bg-green-500 text-white'
      : provider.quota_state === 'QUOTA_EXHAUSTED'
      ? 'bg-red-500 text-white'
      : 'bg-gray-400 text-white';

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>{title}</CardTitle>
          <Badge className={quotaBadgeClass}>{provider.quota_state}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* 5h Window */}
        <div>
          <h3 className="text-sm font-medium text-muted-foreground mb-2">Last 5 Hours</h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-2xl font-bold">{provider['5h'].task_count}</p>
              <p className="text-xs text-muted-foreground">Tasks</p>
            </div>
            {provider['5h'].total_cost_usd !== undefined && (
              <div>
                <p className="text-2xl font-bold">${provider['5h'].total_cost_usd.toFixed(2)}</p>
                <p className="text-xs text-muted-foreground">Cost (USD)</p>
              </div>
            )}
            {provider['5h'].total_tokens !== undefined && (
              <div>
                <p className="text-2xl font-bold">{provider['5h'].total_tokens.toLocaleString()}</p>
                <p className="text-xs text-muted-foreground">Tokens</p>
              </div>
            )}
          </div>
        </div>

        {/* Weekly Window */}
        <div>
          <h3 className="text-sm font-medium text-muted-foreground mb-2">Last 7 Days</h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-2xl font-bold">{provider.weekly.task_count}</p>
              <p className="text-xs text-muted-foreground">Tasks</p>
            </div>
            {provider.weekly.total_cost_usd !== undefined && (
              <div>
                <p className="text-2xl font-bold">${provider.weekly.total_cost_usd.toFixed(2)}</p>
                <p className="text-xs text-muted-foreground">Cost (USD)</p>
              </div>
            )}
            {provider.weekly.total_tokens !== undefined && (
              <div>
                <p className="text-2xl font-bold">{provider.weekly.total_tokens.toLocaleString()}</p>
                <p className="text-xs text-muted-foreground">Tokens</p>
              </div>
            )}
          </div>
        </div>

        {provider.last_quota_error && (
          <p className="text-xs text-muted-foreground">
            Last quota event: {new Date(provider.last_quota_error).toLocaleString()}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

export default function UsagePage() {
  const { data, error, isLoading } = useSWR(
    '/usage',
    () => usageAPI.get(),
    { refreshInterval: 10000 }
  );

  const usage = data?.data;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Usage</h1>
        <p className="text-muted-foreground mt-1">
          Resource consumption across providers
        </p>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
          Failed to load usage data
        </div>
      )}

      {isLoading && (
        <p className="text-muted-foreground text-center py-12">Loading usage data...</p>
      )}

      {usage && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <UsageCard title="Claude Code" provider={usage.claude} />
          <UsageCard title="Codex CLI (OpenAI)" provider={usage.openai} />
        </div>
      )}
    </div>
  );
}
