import TaskForm from '@/components/TaskForm';

interface NewTaskPageProps {
  searchParams: Promise<{ workspace_id?: string }>;
}

export default async function NewTaskPage({ searchParams }: NewTaskPageProps) {
  const params = await searchParams;
  return (
    <div className="max-w-2xl mx-auto">
      <div className="mb-6">
        <h1 className="text-3xl font-bold">New Task</h1>
        <p className="text-muted-foreground mt-1">
          Create a new AI task to execute
        </p>
      </div>
      <TaskForm defaultWorkspaceId={params.workspace_id} />
    </div>
  );
}
