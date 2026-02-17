'use client';

import { useState } from 'react';
import useSWR from 'swr';
import { quotaAPI } from '@/lib/api';
import type { QuotaState } from '@/lib/types';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

export default function QuotaPage() {
  const { data, error, isLoading, mutate } = useSWR(
    '/quota',
    () => quotaAPI.list(),
    { refreshInterval: 5000 }
  );
  const [resetting, setResetting] = useState<string | null>(null);

  const quotas: QuotaState[] = data?.data ?? [];

  const handleReset = async (provider: string) => {
    setResetting(provider);
    try {
      await quotaAPI.reset(provider);
      mutate();
    } catch {
      alert(`Failed to reset ${provider} quota`);
    } finally {
      setResetting(null);
    }
  };

  const getStateBadgeClass = (state: string) => {
    switch (state) {
      case 'OK':
        return 'bg-green-500 text-white';
      case 'QUOTA_EXHAUSTED':
        return 'bg-red-500 text-white';
      default:
        return 'bg-gray-400 text-white';
    }
  };

  const getProviderLabel = (provider: string) => {
    switch (provider) {
      case 'claude':
        return 'Claude (Anthropic)';
      case 'openai':
        return 'OpenAI (Codex)';
      default:
        return provider;
    }
  };

  if (error) {
    return (
      <div className="text-center py-12">
        <h2 className="text-2xl font-bold text-red-600 mb-4">Error Loading Quota</h2>
        <p className="text-muted-foreground">{error.message}</p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">Loading quota states...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Quota Management</h1>
        <p className="text-muted-foreground mt-1">
          Monitor API quota status. When a provider is exhausted, tasks using that backend are paused.
        </p>
      </div>

      {quotas.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <p className="text-muted-foreground">No quota states configured.</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {quotas.map((q) => (
            <Card key={q.id}>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-xl">
                    {getProviderLabel(q.provider)}
                  </CardTitle>
                  <Badge className={getStateBadgeClass(q.state)}>
                    {q.state === 'QUOTA_EXHAUSTED' ? 'EXHAUSTED' : q.state}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <div>
                  <label className="text-sm font-medium text-muted-foreground">Account</label>
                  <p className="text-sm">{q.account_label}</p>
                </div>
                {q.note && (
                  <div>
                    <label className="text-sm font-medium text-muted-foreground">Note</label>
                    <p className="text-sm">{q.note}</p>
                  </div>
                )}
                {q.last_event_at && (
                  <div>
                    <label className="text-sm font-medium text-muted-foreground">Last Event</label>
                    <p className="text-sm">{new Date(q.last_event_at).toLocaleString()}</p>
                  </div>
                )}
                {q.state === 'QUOTA_EXHAUSTED' && (
                  <Button
                    className="mt-4 w-full"
                    onClick={() => handleReset(q.provider)}
                    disabled={resetting === q.provider}
                  >
                    {resetting === q.provider ? 'Resetting...' : 'Reset to OK'}
                  </Button>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
