'use client';

import { useEffect, useState } from 'react';
import axios from 'axios';
import { settingsAPI } from '@/lib/api';
import { ApiErrorBody } from '@/lib/types';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  getTaskCompletionNotificationEnabled,
  setTaskCompletionNotificationEnabled,
} from '@/lib/reviewNotificationSettings';

function getErrorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError<ApiErrorBody>(error)) {
    return error.response?.data?.detail || error.message || fallback;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return fallback;
}

export default function SettingsPage() {
  const [workspaceMaxParallel, setWorkspaceMaxParallel] = useState('3');
  const [taskCompletionNotificationsEnabled, setTaskCompletionNotificationsEnabled] = useState(true);
  const [notificationsReady, setNotificationsReady] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    settingsAPI
      .get()
      .then((res) => {
        setWorkspaceMaxParallel(String(res.data.workspace_max_parallel));
      })
      .catch((err: unknown) => {
        setError(getErrorMessage(err, 'Failed to load settings'));
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    setTaskCompletionNotificationsEnabled(getTaskCompletionNotificationEnabled());
    setNotificationsReady(true);
  }, []);

  const handleSave = async () => {
    const parsed = Number(workspaceMaxParallel);
    if (!Number.isInteger(parsed) || parsed < 1 || parsed > 20) {
      setError('Workspace max parallel must be an integer between 1 and 20');
      setMessage(null);
      return;
    }

    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const res = await settingsAPI.update({ workspace_max_parallel: parsed });
      setWorkspaceMaxParallel(String(res.data.workspace_max_parallel));
      setMessage('Saved. New parallel limit is now applied to all workspaces.');
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Failed to save settings'));
    } finally {
      setSaving(false);
    }
  };

  const handleTaskCompletionNotificationsToggle = (enabled: boolean) => {
    setTaskCompletionNotificationsEnabled(enabled);
    setTaskCompletionNotificationEnabled(enabled);
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Settings</h1>
        <p className="text-muted-foreground mt-1">
          Configure global execution behavior.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Execution</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
              {error}
            </div>
          )}
          {message && (
            <div className="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded">
              {message}
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="workspace-max-parallel">Workspace Max Parallel</Label>
            <Input
              id="workspace-max-parallel"
              type="number"
              min={1}
              max={20}
              value={workspaceMaxParallel}
              onChange={(e) => setWorkspaceMaxParallel(e.target.value)}
              disabled={loading || saving}
            />
            <p className="text-xs text-muted-foreground">
              Applies immediately to all workspaces and runners after save.
            </p>
          </div>

          <Button onClick={handleSave} disabled={loading || saving}>
            {saving ? 'Saving...' : 'Save'}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Notifications</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-start gap-3">
            <input
              id="review-notification-enabled"
              type="checkbox"
              className="h-4 w-4 rounded border-gray-300 mt-1"
              checked={taskCompletionNotificationsEnabled}
              onChange={(e) => handleTaskCompletionNotificationsToggle(e.target.checked)}
              disabled={!notificationsReady}
            />
            <div className="space-y-1">
              <Label htmlFor="review-notification-enabled">
                Notify when task run completes
              </Label>
              <p className="text-xs text-muted-foreground">
                Browser popup notification when task becomes TO_BE_REVIEW, DONE, or FAILED.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
