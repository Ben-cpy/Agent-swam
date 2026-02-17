'use client';

import useSWR from 'swr';
import { quotaAPI } from '@/lib/api';
import type { QuotaState } from '@/lib/types';
import Link from 'next/link';

export default function QuotaAlert() {
  const { data } = useSWR('/quota', () => quotaAPI.list(), {
    refreshInterval: 10000,
  });

  const quotas: QuotaState[] = data?.data ?? [];
  const exhausted = quotas.filter((q) => q.state === 'QUOTA_EXHAUSTED');

  if (exhausted.length === 0) return null;

  return (
    <div className="bg-red-600 text-white px-4 py-3 text-center text-sm font-medium">
      Quota exhausted for: {exhausted.map((q) => q.provider).join(', ')}.
      Tasks using these providers are paused.
      <Link href="/quota" className="underline ml-2">
        Manage Quota
      </Link>
    </div>
  );
}
