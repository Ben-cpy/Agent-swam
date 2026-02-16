import WorkspaceManager from '@/components/WorkspaceManager';

export default function WorkspacesPage() {
  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Workspace Management</h1>
        <p className="text-muted-foreground mt-1">
          Register local, SSH remote, and SSH container workspaces.
        </p>
      </div>
      <WorkspaceManager />
    </div>
  );
}
