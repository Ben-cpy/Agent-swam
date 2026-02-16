from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse
from database import get_db
from models import Run, Task, TaskStatus
import asyncio
import json
from datetime import datetime

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("/{run_id}/stream")
async def stream_logs(
    run_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Stream logs for a run via Server-Sent Events (SSE).

    For completed runs, sends the full log immediately.
    For running tasks, streams logs as they arrive (polls database).
    """
    # Verify run exists
    result = await db.execute(
        select(Run).where(Run.run_id == run_id)
    )
    run = result.scalar_one_or_none()

    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    async def event_generator():
        last_sent_length = 0

        while True:
            # Fetch latest run data
            result = await db.execute(
                select(Run).where(Run.run_id == run_id)
            )
            current_run = result.scalar_one_or_none()

            if not current_run:
                break

            # Send new log data
            if current_run.log_blob:
                current_log = current_run.log_blob or ""

                # Send only new content
                if len(current_log) > last_sent_length:
                    new_content = current_log[last_sent_length:]
                    last_sent_length = len(current_log)

                    yield {
                        "event": "log",
                        "data": json.dumps({
                            "run_id": run_id,
                            "timestamp": datetime.utcnow().isoformat(),
                            "content": new_content
                        })
                    }

            # Check if run is complete
            if current_run.ended_at:
                # Send completion event
                yield {
                    "event": "complete",
                    "data": json.dumps({
                        "run_id": run_id,
                        "exit_code": current_run.exit_code,
                        "ended_at": current_run.ended_at.isoformat() if current_run.ended_at else None
                    })
                }
                break

            # Check if task is still running
            result = await db.execute(
                select(Task).where(Task.run_id == run_id)
            )
            task = result.scalar_one_or_none()

            if task and task.status not in [TaskStatus.RUNNING, TaskStatus.TODO]:
                # Task finished, send final data and close
                break

            # Wait before polling again
            await asyncio.sleep(1)

    return EventSourceResponse(event_generator())


@router.get("/{run_id}")
async def get_logs(
    run_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get complete logs for a run (non-streaming).
    Useful for fetching historical logs.
    """
    result = await db.execute(
        select(Run).where(Run.run_id == run_id)
    )
    run = result.scalar_one_or_none()

    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    return {
        "run_id": run.run_id,
        "task_id": run.task_id,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "ended_at": run.ended_at.isoformat() if run.ended_at else None,
        "exit_code": run.exit_code,
        "log_blob": run.log_blob or ""
    }
