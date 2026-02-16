'use client';

import { useMemo, useState } from 'react';
import axios from 'axios';
import useSWR from 'swr';
import { runnerAPI, workspaceAPI } from '@/lib/api';
import { ApiErrorBody, Runner, Workspace, WorkspaceCreateInput, WorkspaceType } from '@/lib/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

type FormState = {
  display_name: string;
  workspace_type: WorkspaceType;
  path: string;
  runner_id: string;
  host: string;
  port: string;
  ssh_user: string;
  container_name: string;
};

const initialForm: FormState = {
  display_name: '',
  workspace_type: WorkspaceType.LOCAL,
  path: '',
  runner_id: '',
  host: '',
  port: '22',
  ssh_user: '',
  container_name: '',
};

function getWorkspaceTypeLabel(type: WorkspaceType): string {
  if (type === WorkspaceType.LOCAL) return 'Local';
  if (type === WorkspaceType.SSH) return 'SSH';
  return 'SSH + Container';
}

function getWorkspaceHint(type: WorkspaceType): string {
  if (type === WorkspaceType.LOCAL) {
    return 'Windows local path, e.g. D:\\WorkSpace\\MyProject';
  }
  if (type === WorkspaceType.SSH) {
    return 'Remote path on SSH host, e.g. /home/dev/my-project';
  }
  return 'Path inside container on SSH host, e.g. /app';
}

export default function WorkspaceManager() {
  const [form, setForm] = useState<FormState>(initialForm);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const {
    data: wsData,
    error: wsError,
    mutate: mutateWorkspaces,
    isLoading: wsLoading,
  } = useSWR('/workspaces', () => workspaceAPI.list(), {
    refreshInterval: 5000,
    revalidateOnFocus: true,
  });

  const {
    data: runnerData,
    error: runnerError,
    isLoading: runnerLoading,
  } = useSWR('/runners', () => runnerAPI.list(), {
    refreshInterval: 10000,
    revalidateOnFocus: true,
  });

  const workspaces: Workspace[] = wsData?.data ?? [];
  const runners: Runner[] = runnerData?.data ?? [];

  const canSubmit = useMemo(() => {
    if (!form.display_name.trim() || !form.path.trim() || !form.runner_id) return false;
    if (form.workspace_type === WorkspaceType.LOCAL) return true;
    if (!form.host.trim()) return false;
    if (form.workspace_type === WorkspaceType.SSH_CONTAINER && !form.container_name.trim()) return false;
    return true;
  }, [form]);

  const handleTypeChange = (workspaceType: WorkspaceType) => {
    setForm((prev) => ({
      ...prev,
      workspace_type: workspaceType,
      host: workspaceType === WorkspaceType.LOCAL ? '' : prev.host,
      ssh_user: workspaceType === WorkspaceType.LOCAL ? '' : prev.ssh_user,
      container_name: workspaceType === WorkspaceType.SSH_CONTAINER ? prev.container_name : '',
      port: workspaceType === WorkspaceType.LOCAL ? '22' : prev.port || '22',
    }));
  };

  const handleCreateWorkspace = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!canSubmit) {
      setError('Please fill in all required fields');
      return;
    }

    const payload: WorkspaceCreateInput = {
      display_name: form.display_name.trim(),
      workspace_type: form.workspace_type,
      path: form.path.trim(),
      runner_id: parseInt(form.runner_id, 10),
      port: parseInt(form.port || '22', 10),
    };

    if (form.workspace_type !== WorkspaceType.LOCAL) {
      payload.host = form.host.trim();
      if (form.ssh_user.trim()) {
        payload.ssh_user = form.ssh_user.trim();
      }
      if (form.workspace_type === WorkspaceType.SSH_CONTAINER) {
        payload.container_name = form.container_name.trim();
      }
    }

    setSubmitting(true);
    try {
      await workspaceAPI.create(payload);
      await mutateWorkspaces();
      setForm((prev) => ({
        ...initialForm,
        runner_id: prev.runner_id || (runners[0]?.runner_id?.toString() ?? ''),
      }));
    } catch (err: unknown) {
      if (axios.isAxiosError<ApiErrorBody>(err)) {
        setError(err.response?.data?.detail || err.message || 'Failed to create workspace');
      } else if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('Failed to create workspace');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Add Workspace</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={handleCreateWorkspace}>
            {error && (
              <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
                {error}
              </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Display Name</Label>
                <Input
                  value={form.display_name}
                  onChange={(e) => setForm((prev) => ({ ...prev, display_name: e.target.value }))}
                  placeholder="e.g. Local AI Workspace"
                />
              </div>

              <div className="space-y-2">
                <Label>Runner</Label>
                <Select
                  value={form.runner_id}
                  onValueChange={(v) => setForm((prev) => ({ ...prev, runner_id: v }))}
                  disabled={runnerLoading || runners.length === 0}
                >
                  <SelectTrigger>
                    <SelectValue placeholder={runnerLoading ? 'Loading runners...' : 'Select runner'} />
                  </SelectTrigger>
                  <SelectContent>
                    {runners.map((runner) => (
                      <SelectItem key={runner.runner_id} value={runner.runner_id.toString()}>
                        Runner #{runner.runner_id} ({runner.env})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-2">
              <Label>Workspace Type</Label>
              <Select
                value={form.workspace_type}
                onValueChange={(v) => handleTypeChange(v as WorkspaceType)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={WorkspaceType.LOCAL}>Local (Windows)</SelectItem>
                  <SelectItem value={WorkspaceType.SSH}>SSH Remote</SelectItem>
                  <SelectItem value={WorkspaceType.SSH_CONTAINER}>SSH + Container</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Path</Label>
              <Input
                value={form.path}
                onChange={(e) => setForm((prev) => ({ ...prev, path: e.target.value }))}
                placeholder={getWorkspaceHint(form.workspace_type)}
              />
            </div>

            {form.workspace_type !== WorkspaceType.LOCAL && (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="space-y-2">
                  <Label>Host</Label>
                  <Input
                    value={form.host}
                    onChange={(e) => setForm((prev) => ({ ...prev, host: e.target.value }))}
                    placeholder="192.168.1.10 or my-host"
                  />
                </div>

                <div className="space-y-2">
                  <Label>Port</Label>
                  <Input
                    value={form.port}
                    onChange={(e) => setForm((prev) => ({ ...prev, port: e.target.value }))}
                    placeholder="22"
                  />
                </div>

                <div className="space-y-2">
                  <Label>SSH User (Optional)</Label>
                  <Input
                    value={form.ssh_user}
                    onChange={(e) => setForm((prev) => ({ ...prev, ssh_user: e.target.value }))}
                    placeholder="root / ubuntu / dev"
                  />
                </div>
              </div>
            )}

            {form.workspace_type === WorkspaceType.SSH_CONTAINER && (
              <div className="space-y-2">
                <Label>Container Name</Label>
                <Input
                  value={form.container_name}
                  onChange={(e) => setForm((prev) => ({ ...prev, container_name: e.target.value }))}
                  placeholder="my-container"
                />
              </div>
            )}

            <div className="flex gap-3">
              <Button type="submit" disabled={!canSubmit || submitting || runners.length === 0}>
                {submitting ? 'Creating...' : 'Add Workspace'}
              </Button>
              {runners.length === 0 && (
                <p className="text-sm text-muted-foreground self-center">
                  No runner available. Start backend first.
                </p>
              )}
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Registered Workspaces</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {(wsError || runnerError) && (
            <div className="text-sm text-red-600">
              Failed to load workspace data.
            </div>
          )}

          {wsLoading && workspaces.length === 0 && (
            <div className="text-sm text-muted-foreground">Loading workspaces...</div>
          )}

          {!wsLoading && workspaces.length === 0 && (
            <div className="text-sm text-muted-foreground">No workspace registered yet.</div>
          )}

          {workspaces.map((ws) => (
            <div key={ws.workspace_id} className="border rounded-lg p-4 space-y-2">
              <div className="flex items-center justify-between">
                <div className="font-medium">{ws.display_name}</div>
                <div className="flex gap-2">
                  <Badge variant="outline">{getWorkspaceTypeLabel(ws.workspace_type)}</Badge>
                  <Badge variant="outline">Runner #{ws.runner_id}</Badge>
                </div>
              </div>
              <div className="text-sm text-muted-foreground break-all">
                {ws.path}
              </div>
              {ws.workspace_type !== WorkspaceType.LOCAL && (
                <div className="text-xs text-muted-foreground">
                  Host: {ws.host} | Port: {ws.port ?? 22}
                  {ws.ssh_user ? ` | User: ${ws.ssh_user}` : ''}
                  {ws.container_name ? ` | Container: ${ws.container_name}` : ''}
                </div>
              )}
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
