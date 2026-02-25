'use client';

import { useState, useRef, useCallback } from 'react';
import { workspaceAPI } from '@/lib/api';

interface Props {
  workspaceId: number;
  initialNotes: string | null;
}

type SaveState = 'idle' | 'saving' | 'saved' | 'error';

export default function WorkspaceNotes({ workspaceId, initialNotes }: Props) {
  const [notes, setNotes] = useState(initialNotes ?? '');
  const [saveState, setSaveState] = useState<SaveState>('idle');
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const saveNotes = useCallback(async (value: string) => {
    setSaveState('saving');
    try {
      await workspaceAPI.update(workspaceId, { notes: value });
      setSaveState('saved');
      setTimeout(() => setSaveState('idle'), 2000);
    } catch {
      setSaveState('error');
      setTimeout(() => setSaveState('idle'), 3000);
    }
  }, [workspaceId]);

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    setNotes(value);
    setSaveState('idle');
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => saveNotes(value), 800);
  };

  const handleBlur = () => {
    if (saveTimerRef.current) {
      clearTimeout(saveTimerRef.current);
      saveTimerRef.current = null;
    }
    saveNotes(notes);
  };

  const saveIndicator = saveState === 'saving'
    ? <span className="text-muted-foreground">Saving…</span>
    : saveState === 'saved'
    ? <span className="text-green-600">Saved</span>
    : saveState === 'error'
    ? <span className="text-red-500">Save failed</span>
    : null;

  return (
    <div className="w-1/2 min-w-[280px]">
      <div className="bg-slate-50 border rounded-lg px-4 py-2 space-y-1">
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Notes</p>
          <span className="text-xs">{saveIndicator}</span>
        </div>
        <textarea
          className="w-full resize-none bg-transparent text-sm text-foreground placeholder:text-muted-foreground outline-none font-mono leading-relaxed"
          rows={4}
          placeholder="Add notes, goals, or reminders for this workspace…"
          value={notes}
          onChange={handleChange}
          onBlur={handleBlur}
        />
      </div>
    </div>
  );
}
