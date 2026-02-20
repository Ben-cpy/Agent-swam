'use client';

import { useEffect, useState, useRef } from 'react';
import { logAPI } from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

interface LogStreamProps {
  runId: number;
  initialLogs?: string;
}

/**
 * Filter a raw log line to extract human-readable content.
 * Claude Code emits structured JSON events mixed with plain text.
 * We keep only what's meaningful for the user.
 */
function filterLogLine(line: string): string | null {
  const trimmed = line.trim();
  if (!trimmed) return null;

  // Try to parse as JSON
  try {
    const obj = JSON.parse(trimmed);

    // Claude Code SDK JSON event types — extract useful content
    const type: string = obj.type ?? '';

    // Skip purely internal/bookkeeping events
    if (
      type === 'system' ||
      type === 'debug' ||
      type === 'ping' ||
      type === 'rate_limit_event'
    ) {
      return null;
    }

    // Assistant text message
    if (type === 'assistant' && obj.message?.content) {
      const parts: string[] = [];
      for (const block of obj.message.content) {
        if (block.type === 'text' && block.text) {
          parts.push(block.text);
        } else if (block.type === 'tool_use') {
          parts.push(`[Tool: ${block.name}]`);
        }
      }
      return parts.length ? parts.join('\n') : null;
    }

    // Tool result / user message
    if (type === 'user' && obj.message?.content) {
      const parts: string[] = [];
      for (const block of obj.message.content) {
        if (block.type === 'tool_result') {
          const content = Array.isArray(block.content)
            ? block.content
                .filter((c: { type: string; text?: string }) => c.type === 'text')
                .map((c: { type: string; text?: string }) => c.text)
                .join('\n')
            : typeof block.content === 'string'
            ? block.content
            : null;
          if (content) parts.push(content);
        }
      }
      return parts.length ? parts.join('\n') : null;
    }

    // Result / summary event
    if (type === 'result') {
      const lines: string[] = [];
      if (obj.subtype) lines.push(`[${obj.subtype}]`);
      if (obj.result) lines.push(obj.result);
      if (obj.error) lines.push(`Error: ${obj.error}`);
      return lines.length ? lines.join(' ') : null;
    }

    // For any other JSON events, suppress them (internal SDK bookkeeping)
    return null;
  } catch {
    // Not JSON — plain text line, keep as-is
    return trimmed;
  }
}

function processRawLogs(raw: string): string[] {
  return raw.split('\n').flatMap((line) => {
    const filtered = filterLogLine(line);
    if (!filtered) return [];
    return filtered.split('\n').filter(Boolean);
  });
}

export default function LogStream({ runId, initialLogs = '' }: LogStreamProps) {
  const [logs, setLogs] = useState<string[]>(
    initialLogs ? processRawLogs(initialLogs) : []
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
          const filtered = filterLogLine(data.content);
          if (filtered) {
            const lines = filtered.split('\n').filter(Boolean);
            setLogs((prev) => [...prev, ...lines]);
          }
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
            setLogs(processRawLogs(res.data.log_blob));
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
