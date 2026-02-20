'use client';

import { useEffect, useState, useRef } from 'react';
import { logAPI } from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

// ---------------------------------------------------------------------------
// Structured log entry types
// ---------------------------------------------------------------------------
type LogEntry =
  | { type: 'text'; content: string }
  | { type: 'tool_use'; name: string }
  | { type: 'tool_result'; content: string }
  | { type: 'result'; subtype: string; content: string; isError: boolean }
  | { type: 'plain'; content: string };

interface LogStreamProps {
  runId: number;
  initialLogs?: string;
  onComplete?: () => void;
}

// ---------------------------------------------------------------------------
// Parse a single raw log line into zero or more structured entries
// ---------------------------------------------------------------------------
function parseLine(line: string): LogEntry[] {
  const trimmed = line.trim();
  if (!trimmed) return [];

  try {
    const obj = JSON.parse(trimmed);
    const type: string = obj.type ?? '';

    // Skip internal bookkeeping events
    if (['system', 'debug', 'ping', 'rate_limit_event'].includes(type)) {
      return [];
    }

    // Assistant message — can contain text blocks and tool_use blocks
    if (type === 'assistant' && obj.message?.content) {
      const entries: LogEntry[] = [];
      for (const block of obj.message.content) {
        if (block.type === 'text' && block.text?.trim()) {
          entries.push({ type: 'text', content: block.text });
        } else if (block.type === 'tool_use') {
          entries.push({ type: 'tool_use', name: block.name });
        }
      }
      return entries;
    }

    // Tool result message
    if (type === 'user' && obj.message?.content) {
      const entries: LogEntry[] = [];
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
          if (content?.trim()) {
            entries.push({ type: 'tool_result', content });
          }
        }
      }
      return entries;
    }

    // Final result / summary event
    if (type === 'result') {
      const content = [obj.result, obj.error].filter(Boolean).join('\n');
      const isError = !!obj.error || obj.subtype === 'error';
      return [{ type: 'result', subtype: obj.subtype ?? '', content, isError }];
    }

    // All other JSON events — suppress
    return [];
  } catch {
    // Plain-text line (stdout, stderr, markers like "[Process exited…]")
    return [{ type: 'plain', content: trimmed }];
  }
}

function processRawLogs(raw: string): LogEntry[] {
  return raw.split('\n').flatMap((line) => parseLine(line));
}

// ---------------------------------------------------------------------------
// Render a single structured entry
// ---------------------------------------------------------------------------
function LogEntryView({ entry }: { entry: LogEntry }) {
  const [expanded, setExpanded] = useState(false);

  if (entry.type === 'tool_use') {
    return (
      <div className="flex items-center gap-2 mt-4 mb-1 select-none">
        <span className="text-slate-500 text-xs">▶</span>
        <span className="text-yellow-300 text-xs font-semibold tracking-widest uppercase bg-yellow-900/25 border border-yellow-700/40 px-2 py-0.5 rounded">
          {entry.name}
        </span>
        <span className="flex-1 h-px bg-slate-700" />
      </div>
    );
  }

  if (entry.type === 'tool_result') {
    const lines = entry.content.split('\n');
    const COLLAPSE_THRESHOLD = 20;
    const isLong = lines.length > COLLAPSE_THRESHOLD;
    const displayed =
      isLong && !expanded
        ? lines.slice(0, COLLAPSE_THRESHOLD).join('\n')
        : entry.content;

    return (
      <div className="pl-3 border-l-2 border-slate-700 mb-2">
        <pre className="text-slate-400 text-xs whitespace-pre-wrap break-words leading-relaxed font-mono">
          {displayed}
        </pre>
        {isLong && (
          <button
            onClick={() => setExpanded((v) => !v)}
            className="text-xs text-slate-500 hover:text-slate-200 mt-1 transition-colors"
          >
            {expanded
              ? '▲ collapse'
              : `▼ ${lines.length - COLLAPSE_THRESHOLD} more lines`}
          </button>
        )}
      </div>
    );
  }

  if (entry.type === 'text') {
    return (
      <div className="text-slate-50 text-sm mt-3 mb-1 whitespace-pre-wrap break-words leading-relaxed">
        {entry.content}
      </div>
    );
  }

  if (entry.type === 'result') {
    const borderColor = entry.isError ? 'border-red-700' : 'border-green-700';
    const bgColor = entry.isError ? 'bg-red-950/60' : 'bg-green-950/60';
    const labelColor = entry.isError ? 'text-red-400' : 'text-green-400';
    const textColor = entry.isError ? 'text-red-200' : 'text-green-200';

    return (
      <div className={`mt-4 p-3 rounded-md border ${borderColor} ${bgColor}`}>
        {entry.subtype && (
          <div className={`text-xs font-bold uppercase tracking-widest mb-1 ${labelColor}`}>
            {entry.subtype}
          </div>
        )}
        {entry.content && (
          <pre className={`text-sm whitespace-pre-wrap break-words leading-relaxed font-mono ${textColor}`}>
            {entry.content}
          </pre>
        )}
      </div>
    );
  }

  // Plain text (process markers, stderr, etc.)
  const isProcessMarker =
    entry.content.startsWith('[Process') || entry.content.startsWith('[success]');
  return (
    <div
      className={`text-xs whitespace-pre-wrap break-words leading-relaxed font-mono ${
        isProcessMarker ? 'text-slate-500 italic mt-2' : 'text-slate-300'
      }`}
    >
      {entry.content}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
export default function LogStream({ runId, initialLogs = '', onComplete }: LogStreamProps) {
  const [logs, setLogs] = useState<LogEntry[]>(
    initialLogs ? processRawLogs(initialLogs) : []
  );
  const [isComplete, setIsComplete] = useState(false);
  const [exitCode, setExitCode] = useState<number | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [reconnectAttempt, setReconnectAttempt] = useState(0);
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
    };

    eventSource.addEventListener('log', (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.content) {
          const entries = parseLine(data.content);
          if (entries.length) {
            setLogs((prev) => [...prev, ...entries]);
          }
        }
      } catch (err) {
        console.error('Failed to parse log event:', err);
      }
    });

    eventSource.addEventListener('complete', (e) => {
      try {
        const data = JSON.parse(e.data);
        setExitCode(data.exit_code ?? null);
        eventSource.close();

        // Re-fetch the full log to ensure final content (e.g. API usage) is shown
        logAPI
          .get(runId)
          .then((res) => {
            if (res.data.log_blob) {
              setLogs(processRawLogs(res.data.log_blob));
            }
          })
          .catch((err) => {
            console.error('Failed to fetch final logs:', err);
          })
          .finally(() => {
            setIsComplete(true);
            onComplete?.();
          });
      } catch (err) {
        console.error('Failed to parse complete event:', err);
      }
    });

    eventSource.onerror = (err) => {
      console.error('SSE connection error:', err);
      setIsConnected(false);
      eventSource.close();
      setTimeout(() => {
        setReconnectAttempt((c) => c + 1);
      }, 3000);
    };

    return () => {
      eventSource.close();
    };
  }, [runId, isComplete, reconnectAttempt]);

  // Fetch initial logs if not provided inline
  useEffect(() => {
    if (!initialLogs && runId) {
      logAPI
        .get(runId)
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
                  {isConnected ? 'Streaming' : 'Reconnecting...'}
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
                Exit {exitCode}
              </span>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="bg-slate-900 text-slate-50 p-4 rounded-lg font-mono text-sm h-[600px] overflow-y-auto">
          {logs.length === 0 && (
            <div className="text-slate-400 text-sm">
              {isComplete ? 'No logs available.' : 'Waiting for logs…'}
            </div>
          )}
          {logs.map((entry, index) => (
            <LogEntryView key={index} entry={entry} />
          ))}
          <div ref={logsEndRef} />
        </div>
      </CardContent>
    </Card>
  );
}
