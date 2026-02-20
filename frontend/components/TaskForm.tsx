'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import axios from 'axios';
import { taskAPI, workspaceAPI } from '@/lib/api';
import { ApiErrorBody, BackendType, Workspace } from '@/lib/types';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

interface TaskFormProps {
  defaultWorkspaceId?: string;
  /** When set, the workspace selector is hidden and this workspace is always used. */
  lockedWorkspaceId?: number;
}

export default function TaskForm({ defaultWorkspaceId, lockedWorkspaceId }: TaskFormProps) {
  const router = useRouter();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [titleManuallyEdited, setTitleManuallyEdited] = useState(false);

  const [formData, setFormData] = useState({
    title: '',
    prompt: '',
    workspace_id: '',
    backend: BackendType.CLAUDE_CODE,
  });

  const [errors, setErrors] = useState({
    title: '',
    prompt: '',
    workspace_id: '',
  });

  // Fetch suggested title when workspace changes
  const fetchSuggestedTitle = async (workspaceId: string) => {
    if (!workspaceId || titleManuallyEdited) return;
    try {
      const res = await taskAPI.nextNumber(parseInt(workspaceId));
      setFormData((prev) => ({ ...prev, title: res.data.suggested_title }));
    } catch {
      // Silently ignore - title can still be entered manually
    }
  };

  // Fetch workspaces on mount
  useEffect(() => {
    workspaceAPI.list()
      .then((res) => {
        setWorkspaces(res.data);
        if (res.data.length > 0) {
          let defaultId: string;
          if (lockedWorkspaceId !== undefined) {
            // Workspace is locked from URL — use it directly
            defaultId = lockedWorkspaceId.toString();
          } else {
            // Priority: URL param > localStorage > first workspace
            const lastId = typeof window !== 'undefined'
              ? localStorage.getItem('lastWorkspaceId')
              : null;
            const targetId = defaultWorkspaceId ?? lastId;
            const defaultWs = (targetId && res.data.find((w) => w.workspace_id.toString() === targetId))
              ?? res.data[0];
            defaultId = defaultWs.workspace_id.toString();
          }
          setFormData((prev) => ({
            ...prev,
            workspace_id: defaultId,
          }));
          fetchSuggestedTitle(defaultId);
        }
      })
      .catch((err) => {
        setError('Failed to load workspaces');
        console.error(err);
      });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const validate = () => {
    const newErrors = {
      title: '',
      prompt: '',
      workspace_id: '',
    };

    if (!formData.title.trim()) {
      newErrors.title = 'Title is required';
    } else if (formData.title.length > 500) {
      newErrors.title = 'Title must be less than 500 characters';
    }

    if (!formData.prompt.trim()) {
      newErrors.prompt = 'Prompt is required';
    }

    if (!formData.workspace_id) {
      newErrors.workspace_id = 'Workspace is required';
    }

    setErrors(newErrors);
    return !newErrors.title && !newErrors.prompt && !newErrors.workspace_id;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validate()) {
      return;
    }

    setLoading(true);
    setError(null);

    try {
      await taskAPI.create({
        title: formData.title,
        prompt: formData.prompt,
        workspace_id: parseInt(formData.workspace_id),
        backend: formData.backend,
      });

      // Redirect to workspace board
      router.push(`/workspaces/${formData.workspace_id}/board`);
    } catch (error: unknown) {
      if (axios.isAxiosError<ApiErrorBody>(error)) {
        setError(error.response?.data?.detail || error.message || 'Failed to create task');
      } else if (error instanceof Error) {
        setError(error.message);
      } else {
        setError('Failed to create task');
      }
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  if (workspaces.length === 0 && !error) {
    return (
      <Card>
        <CardContent className="py-12 text-center">
          <p className="text-muted-foreground mb-4">
            No workspaces available. Please register a workspace first.
          </p>
          <Button type="button" onClick={() => router.push('/workspaces')}>
            Go To Workspace Management
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Create New Task</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Error Alert */}
          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
              {error}
            </div>
          )}

          {/* Workspace */}
          {lockedWorkspaceId !== undefined ? (
            <div className="space-y-1">
              <Label>Workspace</Label>
              <p className="text-sm px-3 py-2 bg-slate-50 border rounded-md text-muted-foreground">
                {workspaces.find((w) => w.workspace_id === lockedWorkspaceId)?.display_name
                  ?? `Workspace ${lockedWorkspaceId}`}
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              <Label htmlFor="workspace">
                Workspace <span className="text-red-500">*</span>
              </Label>
              <Select
                value={formData.workspace_id}
                onValueChange={(value) => {
                  setFormData({ ...formData, workspace_id: value });
                  localStorage.setItem('lastWorkspaceId', value);
                  fetchSuggestedTitle(value);
                }}
              >
                <SelectTrigger className={errors.workspace_id ? 'border-red-500' : ''}>
                  <SelectValue placeholder="Select a workspace" />
                </SelectTrigger>
                <SelectContent>
                  {workspaces.map((ws) => (
                    <SelectItem
                      key={ws.workspace_id}
                      value={ws.workspace_id.toString()}
                    >
                      {ws.display_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {errors.workspace_id && (
                <p className="text-sm text-red-500">{errors.workspace_id}</p>
              )}
            </div>
          )}

          {/* Title */}
          <div className="space-y-2">
            <Label htmlFor="title">
              Title <span className="text-red-500">*</span>
            </Label>
            <Input
              id="title"
              value={formData.title}
              onChange={(e) => {
                setTitleManuallyEdited(e.target.value !== '');
                setFormData({ ...formData, title: e.target.value });
              }}
              placeholder="e.g., Fix authentication bug"
              className={errors.title ? 'border-red-500' : ''}
            />
            {errors.title && (
              <p className="text-sm text-red-500">{errors.title}</p>
            )}
          </div>

          {/* Prompt */}
          <div className="space-y-2">
            <Label htmlFor="prompt">
              Prompt <span className="text-red-500">*</span>
            </Label>
            <Textarea
              id="prompt"
              value={formData.prompt}
              onChange={(e) =>
                setFormData({ ...formData, prompt: e.target.value })
              }
              placeholder="Describe the task in detail..."
              rows={6}
              className={errors.prompt ? 'border-red-500' : ''}
            />
            {errors.prompt && (
              <p className="text-sm text-red-500">{errors.prompt}</p>
            )}
          </div>

          {/* Backend */}
          <div className="space-y-2">
            <Label>Backend</Label>
            <div className="flex gap-4">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="backend"
                  value={BackendType.CLAUDE_CODE}
                  checked={formData.backend === BackendType.CLAUDE_CODE}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      backend: e.target.value as BackendType,
                    })
                  }
                  className="w-4 h-4"
                />
                <span>Claude Code</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="backend"
                  value={BackendType.CODEX_CLI}
                  checked={formData.backend === BackendType.CODEX_CLI}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      backend: e.target.value as BackendType,
                    })
                  }
                  className="w-4 h-4"
                />
                <span>Codex CLI</span>
              </label>
            </div>
          </div>

          {/* Submit Button */}
          <div className="flex gap-3">
            <Button type="submit" disabled={loading}>
              {loading ? 'Creating...' : 'Create Task'}
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() =>
                router.push(formData.workspace_id ? `/workspaces/${formData.workspace_id}/board` : '/')
              }
            >
              Cancel
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
