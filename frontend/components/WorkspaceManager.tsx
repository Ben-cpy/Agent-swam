'use client';

import { useMemo, useState } from 'react';
import axios from 'axios';
import useSWR from 'swr';
import { Trash2, Pencil, Check, X } from 'lucide-react';
import { workspaceAPI } from '@/lib/api';
import { ApiErrorBody, Workspace, WorkspaceCreateInput, WorkspaceType } from '@/lib/types';
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
import WorkspaceHealthBadge from '@/components/WorkspaceHealthBadge';

type FormState = {
  display_name: string;
  workspace_type: WorkspaceType;
  path: string;
  host: string;
  port: string;
  ssh_user: string;
  container_name: string;
  login_shell: string;
};

const initialForm: FormState = {
  display_name: '',
  workspace_type: WorkspaceType.LOCAL,
  path: '',
  host: '',
  port: '22',
  ssh_user: '',
  container_name: '',
  login_shell: 'bash',
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
  const [renamingId, setRenamingId] = useState<number | null>(null);
  const [renameValue, setRenameValue] = useState('');

  const {
    data: wsData,
    error: wsError,
    mutate: mutateWorkspaces,
    isLoading: wsLoading,
  } = useSWR('/workspaces', () => workspaceAPI.list(), {
    refreshInterval: 5000,
    revalidateOnFocus: true,
  });

  const workspaces: Workspace[] = wsData?.data ?? [];

  const canSubmit = useMemo(() => {
    if (!form.display_name.trim() || !form.path.trim()) return false;
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

  const startRename = (ws: Workspace) => {
    setRenamingId(ws.workspace_id);
    setRenameValue(ws.display_name);
  };

  const cancelRename = () => {
    setRenamingId(null);
    setRenameValue('');
  };

  const confirmRename = async (workspaceId: number) => {
    const name = renameValue.trim();
    if (!name) return;
    try {
      await workspaceAPI.update(workspaceId, { display_name: name });
      await mutateWorkspaces();
    } catch {
      alert('Failed to rename workspace');
    } finally {
      cancelRename();
    }
  };

  const handleDeleteWorkspace = async (workspaceId: number, name: string) => {
    if (!window.confirm(`Delete workspace "${name}"? This will also delete all its tasks and run history.`)) return;
    try {
      await workspaceAPI.delete(workspaceId);
      await mutateWorkspaces();
    } catch (err: unknown) {
      if (axios.isAxiosError<ApiErrorBody>(err)) {
        alert(err.response?.data?.detail || err.message || 'Failed to delete workspace');
      } else {
        alert('Failed to delete workspace');
      }
    }
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
      payload.login_shell = form.login_shell || 'bash';
    }

    setSubmitting(true);
    try {
      await workspaceAPI.create(payload);
      await mutateWorkspaces();
      setForm(initialForm);
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

            <div className="space-y-2">
              <Label>Display Name</Label>
              <Input
                value={form.display_name}
                onChange={(e) => setForm((prev) => ({ ...prev, display_name: e.target.value }))}
                placeholder="e.g. Local AI Workspace"
              />
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

            {form.workspace_type !== WorkspaceType.LOCAL && (
              <div className="space-y-2">
                <Label>Login Shell</Label>
                <Select
                  value={form.login_shell}
                  onValueChange={(v) => setForm((prev) => ({ ...prev, login_shell: v }))}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="bash">bash</SelectItem>
                    <SelectItem value="zsh">zsh</SelectItem>
                    <SelectItem value="sh">sh</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  Shell used to run AI tasks on the remote host. Choose zsh if your proxy settings are configured in ~/.zshrc.
                </p>
              </div>
            )}

            <div className="flex gap-3">
              <Button type="submit" disabled={!canSubmit || submitting}>
                {submitting ? 'Creating...' : 'Add Workspace'}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Registered Workspaces</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {wsError && (
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
                <div className="flex items-center gap-2 min-w-0 flex-1">
                  <WorkspaceHealthBadge
                    workspaceId={ws.workspace_id}
                    workspaceType={ws.workspace_type}
                  />
                  {renamingId === ws.workspace_id ? (
                    <div className="flex items-center gap-1 flex-1">
                      <Input
                        className="h-7 text-sm flex-1"
                        value={renameValue}
                        onChange={(e) => setRenameValue(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') confirmRename(ws.workspace_id);
                          if (e.key === 'Escape') cancelRename();
                        }}
                        autoFocus
                      />
                      <Button variant="ghost" size="icon" className="h-7 w-7 text-green-600" onClick={() => confirmRename(ws.workspace_id)}>
                        <Check className="w-4 h-4" />
                      </Button>
                      <Button variant="ghost" size="icon" className="h-7 w-7" onClick={cancelRename}>
                        <X className="w-4 h-4" />
                      </Button>
                    </div>
                  ) : (
                    <span className="font-medium truncate">{ws.display_name}</span>
                  )}
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <Badge variant="outline">{getWorkspaceTypeLabel(ws.workspace_type)}</Badge>
                  {renamingId !== ws.workspace_id && (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7"
                      onClick={() => startRename(ws)}
                      title="Rename workspace"
                    >
                      <Pencil className="w-4 h-4" />
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="icon"
                    className="text-destructive hover:text-destructive h-7 w-7"
                    onClick={() => handleDeleteWorkspace(ws.workspace_id, ws.display_name)}
                    title="Delete workspace"
                  >
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </div>
              </div>
              <div className="text-sm text-muted-foreground break-all">
                {ws.path}
              </div>
              {ws.workspace_type !== WorkspaceType.LOCAL && (
                <div className="text-xs text-muted-foreground space-y-1">
                  <div>
                    Host: {ws.host} | Port: {ws.port ?? 22}
                    {ws.ssh_user ? ` | User: ${ws.ssh_user}` : ''}
                    {ws.container_name ? ` | Container: ${ws.container_name}` : ''}
                  </div>
                  <div className="flex items-center gap-2">
                    <span>Shell:</span>
                    <Select
                      value={ws.login_shell || 'bash'}
                      onValueChange={async (v) => {
                        try {
                          await workspaceAPI.update(ws.workspace_id, { login_shell: v });
                          await mutateWorkspaces();
                        } catch {
                          alert('Failed to update shell');
                        }
                      }}
                    >
                      <SelectTrigger className="h-6 text-xs w-20">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="bash">bash</SelectItem>
                        <SelectItem value="zsh">zsh</SelectItem>
                        <SelectItem value="sh">sh</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              )}
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
