'use client';

import { Runner } from '@/lib/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { formatDistanceToNow } from 'date-fns';
import { parseUTCDate } from '@/lib/utils';

interface RunnerCardProps {
  runner: Runner;
}

export default function RunnerCard({ runner }: RunnerCardProps) {
  const isOnline = runner.status === 'ONLINE';

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <span>Runner #{runner.runner_id}</span>
            <div
              className={`w-3 h-3 rounded-full ${
                isOnline ? 'bg-green-500' : 'bg-red-500'
              }`}
              title={isOnline ? 'Online' : 'Offline'}
            />
          </CardTitle>
          <Badge variant={isOnline ? 'default' : 'secondary'} className={isOnline ? 'bg-green-500' : ''}>
            {runner.status}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <label className="text-sm font-medium text-muted-foreground">
            Environment
          </label>
          <p className="mt-1 font-mono text-sm">{runner.env}</p>
        </div>

        <div>
          <label className="text-sm font-medium text-muted-foreground">
            Capabilities
          </label>
          <div className="mt-2 flex flex-wrap gap-2">
            {runner.capabilities.map((cap, index) => (
              <Badge key={index} variant="outline">
                {cap}
              </Badge>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-sm font-medium text-muted-foreground">
              Max Parallel
            </label>
            <p className="mt-1 text-sm">{runner.max_parallel}</p>
          </div>
          <div>
            <label className="text-sm font-medium text-muted-foreground">
              Last Heartbeat
            </label>
            <p className="mt-1 text-sm">
              {formatDistanceToNow(parseUTCDate(runner.heartbeat_at), {
                addSuffix: true,
              })}
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
