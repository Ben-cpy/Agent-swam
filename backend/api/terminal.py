import asyncio
import json
import logging
from typing import Optional

import asyncssh
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from database import async_session_maker
from models import Run, Task, Workspace, WorkspaceType

router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/api/tasks/{task_id}/terminal")
async def task_terminal(websocket: WebSocket, task_id: int):
    """
    Connect to the tmux session for a task via SSH.
    Uses system SSH config (respects ~/.ssh/config and SSH agent).
    Workspace must be ssh or ssh_container type.
    """
    await websocket.accept()

    try:
        async with async_session_maker() as db:
            task_result = await db.execute(select(Task).where(Task.id == task_id))
            task = task_result.scalar_one_or_none()
            if not task:
                await websocket.send_text(f"Error: Task {task_id} not found.\r\n")
                await websocket.close(code=1008)
                return

            workspace_result = await db.execute(
                select(Workspace).where(Workspace.workspace_id == task.workspace_id)
            )
            workspace = workspace_result.scalar_one_or_none()
            if not workspace:
                await websocket.send_text(f"Error: Workspace for task {task_id} not found.\r\n")
                await websocket.close(code=1008)
                return

            if workspace.workspace_type not in (WorkspaceType.SSH, WorkspaceType.SSH_CONTAINER):
                await websocket.send_text(
                    f"Error: Workspace type '{workspace.workspace_type.value}' does not support terminal access. "
                    "Only ssh and ssh_container workspaces are supported.\r\n"
                )
                await websocket.close(code=1008)
                return

            ssh_host = workspace.host
            if not ssh_host:
                await websocket.send_text("Error: Workspace has no SSH host configured.\r\n")
                await websocket.close(code=1008)
                return

            # Retrieve the tmux session name from the latest run
            tmux_session: Optional[str] = None
            if task.run_id:
                run_result = await db.execute(select(Run).where(Run.run_id == task.run_id))
                run = run_result.scalar_one_or_none()
                if run:
                    tmux_session = run.tmux_session

            if not tmux_session:
                # Fallback to the conventional name
                tmux_session = f"aitask-{task_id}"

            ssh_user = workspace.ssh_user or None
            ssh_port = workspace.port or 22

    except Exception as exc:
        logger.error("Error loading task %s for terminal: %s", task_id, exc, exc_info=True)
        await websocket.send_text(f"Error: {exc}\r\n")
        await websocket.close(code=1011)
        return

    # Establish SSH connection using system SSH agent / known_hosts
    try:
        connect_kwargs = dict(
            host=ssh_host,
            port=ssh_port,
            known_hosts=None,  # Trust system known_hosts via agent
        )
        if ssh_user:
            connect_kwargs["username"] = ssh_user

        async with asyncssh.connect(**connect_kwargs) as conn:
            # Send current tmux pane content as history
            try:
                capture_result = await conn.run(
                    f"tmux capture-pane -t {asyncssh.quote(tmux_session)} -p -e 2>/dev/null || echo 'NO_SESSION'"
                )
                captured = capture_result.stdout or ""
                if captured.strip() != "NO_SESSION" and captured.strip():
                    await websocket.send_text(captured)
            except Exception as exc:
                logger.debug("Could not capture tmux pane for session %s: %s", tmux_session, exc)

            # Attach to the tmux session with a PTY
            try:
                async with conn.create_process(
                    f"tmux attach-session -t {asyncssh.quote(tmux_session)}",
                    term_type="xterm-256color",
                    term_size=(80, 24),
                ) as process:

                    async def forward_to_browser():
                        """Relay bytes from the remote PTY to the WebSocket client."""
                        try:
                            async for chunk in process.stdout:
                                data = chunk.encode() if isinstance(chunk, str) else chunk
                                await websocket.send_bytes(data)
                        except Exception as exc:
                            logger.debug("forward_to_browser ended: %s", exc)

                    async def forward_to_tmux():
                        """Relay keystrokes / resize events from the WebSocket to the remote PTY."""
                        try:
                            while True:
                                message = await websocket.receive()
                                if "text" in message and message["text"]:
                                    text = message["text"]
                                    # Check for resize JSON
                                    try:
                                        parsed = json.loads(text)
                                        if parsed.get("type") == "resize":
                                            cols = int(parsed.get("cols", 80))
                                            rows = int(parsed.get("rows", 24))
                                            # Resize the tmux window
                                            await conn.run(
                                                f"tmux resize-window -t {asyncssh.quote(tmux_session)} "
                                                f"-x {cols} -y {rows}"
                                            )
                                            # Also resize the PTY
                                            process.change_terminal_size(cols, rows)
                                            continue
                                    except (json.JSONDecodeError, ValueError):
                                        pass
                                    process.stdin.write(text)
                                elif "bytes" in message and message["bytes"]:
                                    process.stdin.write(message["bytes"].decode(errors="replace"))
                        except WebSocketDisconnect:
                            logger.debug("WebSocket disconnected for task %s terminal", task_id)
                        except Exception as exc:
                            logger.debug("forward_to_tmux ended: %s", exc)

                    await asyncio.gather(forward_to_browser(), forward_to_tmux())

            except asyncssh.ProcessError as exc:
                msg = f"tmux attach-session failed (session may not exist): {exc}\r\n"
                logger.warning("Task %s terminal: %s", task_id, msg)
                await websocket.send_text(msg)
            except Exception as exc:
                msg = f"Terminal process error: {exc}\r\n"
                logger.error("Task %s terminal process error: %s", task_id, exc, exc_info=True)
                await websocket.send_text(msg)

    except asyncssh.Error as exc:
        msg = f"SSH connection error: {exc}\r\n"
        logger.error("SSH error for task %s terminal: %s", task_id, exc, exc_info=True)
        try:
            await websocket.send_text(msg)
        except Exception:
            pass
    except WebSocketDisconnect:
        logger.info("Client disconnected from task %s terminal", task_id)
    except Exception as exc:
        logger.error("Unexpected error in task %s terminal: %s", task_id, exc, exc_info=True)
        try:
            await websocket.send_text(f"Unexpected error: {exc}\r\n")
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
