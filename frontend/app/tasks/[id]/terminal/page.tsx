'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import useSWR from 'swr';
import { taskAPI } from '@/lib/api';
import { Button } from '@/components/ui/button';

// Dynamically import xterm to avoid SSR issues
let Terminal: typeof import('@xterm/xterm').Terminal | undefined;
let FitAddon: typeof import('@xterm/addon-fit').FitAddon | undefined;

export default function TaskTerminalPage() {
  const params = useParams();
  const router = useRouter();
  const taskId = parseInt(params.id as string, 10);

  const terminalContainerRef = useRef<HTMLDivElement>(null);
  const terminalInstanceRef = useRef<import('@xterm/xterm').Terminal | null>(null);
  const fitAddonRef = useRef<import('@xterm/addon-fit').FitAddon | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [xtermReady, setXtermReady] = useState(false);

  // Fetch task info
  const { data, error: taskError } = useSWR(
    `/tasks/${taskId}`,
    () => taskAPI.get(taskId),
    { revalidateOnFocus: false }
  );
  const task = data?.data ?? null;

  // Dynamically load xterm modules (client-side only)
  useEffect(() => {
    let cancelled = false;
    Promise.all([
      import('@xterm/xterm'),
      import('@xterm/addon-fit'),
    ]).then(([xtermModule, fitModule]) => {
      if (cancelled) return;
      Terminal = xtermModule.Terminal;
      FitAddon = fitModule.FitAddon;
      setXtermReady(true);
    });
    return () => { cancelled = true; };
  }, []);

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setConnected(false);
  }, []);

  // Initialize terminal and WebSocket once xterm is ready and task is loaded
  useEffect(() => {
    if (!xtermReady || !Terminal || !FitAddon) return;
    if (!task) return;
    if (!terminalContainerRef.current) return;

    // Clean up previous instance
    if (terminalInstanceRef.current) {
      terminalInstanceRef.current.dispose();
      terminalInstanceRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    // Create terminal
    const term = new Terminal({
      cursorBlink: true,
      fontSize: 14,
      fontFamily: '"Cascadia Code", "Fira Code", "Source Code Pro", monospace',
      theme: {
        background: '#1a1a2e',
        foreground: '#e0e0e0',
        cursor: '#ffffff',
      },
      convertEol: true,
    });

    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);
    term.open(terminalContainerRef.current);
    fitAddon.fit();

    terminalInstanceRef.current = term;
    fitAddonRef.current = fitAddon;

    // Connect WebSocket
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//127.0.0.1:8000/api/tasks/${taskId}/terminal`;
    const ws = new WebSocket(wsUrl);
    ws.binaryType = 'arraybuffer';
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      setError(null);
      term.writeln('\x1b[32mConnected to terminal.\x1b[0m');
    };

    ws.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) {
        term.write(new Uint8Array(event.data));
      } else if (typeof event.data === 'string') {
        term.write(event.data);
      }
    };

    ws.onerror = () => {
      setError('WebSocket connection error. Check that the backend is running and the task uses an SSH workspace.');
      setConnected(false);
    };

    ws.onclose = (event) => {
      setConnected(false);
      if (!event.wasClean) {
        term.writeln('\r\n\x1b[31mConnection closed.\x1b[0m');
      }
    };

    // Send keystrokes to WebSocket
    term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(data);
      }
    });

    // Handle terminal resize
    const resizeObserver = new ResizeObserver(() => {
      if (fitAddonRef.current && terminalInstanceRef.current) {
        fitAddonRef.current.fit();
        const dims = fitAddonRef.current.proposeDimensions();
        if (dims && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'resize', cols: dims.cols, rows: dims.rows }));
        }
      }
    });

    if (terminalContainerRef.current) {
      resizeObserver.observe(terminalContainerRef.current);
    }

    return () => {
      resizeObserver.disconnect();
      ws.close();
      term.dispose();
      terminalInstanceRef.current = null;
      fitAddonRef.current = null;
      wsRef.current = null;
    };
  }, [xtermReady, task, taskId]);

  if (taskError) {
    return (
      <div className="text-center py-12">
        <h2 className="text-2xl font-bold text-red-600 mb-4">Error Loading Task</h2>
        <p className="text-muted-foreground mb-4">{taskError.message}</p>
        <Button onClick={() => router.push('/')}>Back to Board</Button>
      </div>
    );
  }

  const tmuxSession = task ? `aitask-${task.id}` : '';

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] gap-2">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-2 py-2 bg-slate-800 rounded-lg">
        <div className="flex items-center gap-4">
          <Button
            variant="outline"
            size="sm"
            onClick={() => router.push(`/tasks/${taskId}`)}
            className="text-slate-200 border-slate-600 hover:bg-slate-700"
          >
            Back to Task
          </Button>
          <div className="text-slate-200 text-sm">
            <span className="font-semibold">{task?.title ?? `Task #${taskId}`}</span>
            {tmuxSession && (
              <span className="ml-3 text-slate-400 font-mono text-xs">
                tmux: {tmuxSession}
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-3">
          <span
            className={`inline-block w-2 h-2 rounded-full ${
              connected ? 'bg-green-400' : 'bg-red-400'
            }`}
          />
          <span className="text-xs text-slate-400">
            {connected ? 'Connected' : 'Disconnected'}
          </span>
          {connected && (
            <Button
              variant="destructive"
              size="sm"
              onClick={disconnect}
            >
              Disconnect
            </Button>
          )}
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="bg-red-900 text-red-200 text-sm px-4 py-2 rounded-lg">
          {error}
        </div>
      )}

      {/* Terminal container */}
      <div
        ref={terminalContainerRef}
        className="flex-1 rounded-lg overflow-hidden"
        style={{ background: '#1a1a2e', minHeight: 0 }}
      />
    </div>
  );
}
