'use client';

import { useEffect, useState, useRef } from 'react';
import { logAPI } from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

interface LogStreamProps {
  runId: number;
  initialLogs?: string;
}

export default function LogStream({ runId, initialLogs = '' }: LogStreamProps) {
  const [logs, setLogs] = useState<string[]>(
    initialLogs ? initialLogs.split('\n').filter(Boolean) : []
  );
  const [isComplete, setIsComplete] = useState(false);
  const [exitCode, setExitCode] = useState<number | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  // Setup SSE connection
  useEffect(() => {
    if (!runId || isComplete) return;

    const streamURL = logAPI.streamURL(runId);
    const eventSource = new EventSource(streamURL);

    eventSourceRef.current = eventSource;

    eventSource.onopen = () => {
      setIsConnected(true);
      console.log('SSE connection opened');
    };

    eventSource.addEventListener('log', (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.content) {
          setLogs((prev) => [...prev, data.content]);
        }
      } catch (err) {
        console.error('Failed to parse log event:', err);
      }
    });

    eventSource.addEventListener('complete', (e) => {
      try {
        const data = JSON.parse(e.data);
        setIsComplete(true);
        setExitCode(data.exit_code ?? null);
        console.log('Task completed with exit code:', data.exit_code);
        eventSource.close();
      } catch (err) {
        console.error('Failed to parse complete event:', err);
      }
    });

    eventSource.onerror = (err) => {
      console.error('SSE connection error:', err);
      setIsConnected(false);

      // Try to reconnect after 5 seconds if not complete
      if (!isComplete) {
        setTimeout(() => {
          if (eventSourceRef.current?.readyState === EventSource.CLOSED) {
            console.log('Attempting to reconnect...');
            // Component will re-mount or retry connection
          }
        }, 5000);
      }
    };

    return () => {
      eventSource.close();
    };
  }, [runId, isComplete]);

  // Fetch initial logs if available
  useEffect(() => {
    if (!initialLogs && runId) {
      logAPI.get(runId)
        .then((res) => {
          if (res.data.log_blob) {
            setLogs(res.data.log_blob.split('\n').filter(Boolean));
          }
          if (res.data.exit_code != null) {
            setIsComplete(true);
            setExitCode(res.data.exit_code ?? null);
          }
        })
        .catch((err) => {
          console.error('Failed to fetch initial logs:', err);
        });
    }
  }, [runId, initialLogs]);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>Execution Logs</CardTitle>
          <div className="flex items-center gap-2">
            {!isComplete && (
              <div className="flex items-center gap-2">
                <div
                  className={`w-2 h-2 rounded-full ${
                    isConnected ? 'bg-green-500' : 'bg-red-500'
                  }`}
                />
                <span className="text-xs text-muted-foreground">
                  {isConnected ? 'Streaming' : 'Disconnected'}
                </span>
              </div>
            )}
            {isComplete && (
              <span
                className={`text-xs font-medium px-2 py-1 rounded ${
                  exitCode === 0
                    ? 'bg-green-100 text-green-700'
                    : 'bg-red-100 text-red-700'
                }`}
              >
                Exit Code: {exitCode}
              </span>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="bg-slate-900 text-slate-50 p-4 rounded-lg font-mono text-sm h-[500px] overflow-y-auto">
          {logs.length === 0 && (
            <div className="text-slate-400">
              {isComplete ? 'No logs available' : 'Waiting for logs...'}
            </div>
          )}
          {logs.map((log, index) => (
            <div key={index} className="whitespace-pre-wrap break-words">
              {log}
            </div>
          ))}
          <div ref={logsEndRef} />
        </div>
      </CardContent>
    </Card>
  );
}
