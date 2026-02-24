"""Shared SSH utility helpers used across executor, workspaces, and tasks APIs."""
import asyncio
import logging
from typing import Optional

from models import WorkspaceType

logger = logging.getLogger(__name__)


def build_ssh_connection_args(host: str, port: Optional[int], user: Optional[str]) -> list[str]:
    """Return SSH args list (excluding the remote command) for subprocess.exec calls.

    Example output: ["-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-p", "6020", "warou@wang"]
    """
    args = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-o", "StrictHostKeyChecking=no"]
    if port and port != 22:
        args.extend(["-p", str(port)])
    target = host
    if user:
        target = f"{user}@{target}"
    args.append(target)
    return args


def extract_remote_path(canonical_path: str, workspace_type: WorkspaceType) -> str:
    """Extract the actual filesystem path on the remote from a canonical SSH workspace path.

    - SSH:           ssh://user@host:port/remote/path          → /remote/path
    - SSH_CONTAINER: ssh://user@host:port/container/name:/remote/path → /remote/path
    """
    from urllib.parse import urlparse
    parsed = urlparse(canonical_path)
    if workspace_type == WorkspaceType.SSH:
        return parsed.path
    elif workspace_type == WorkspaceType.SSH_CONTAINER:
        path_part = parsed.path
        if ":" in path_part:
            return path_part.split(":", 1)[1]
        return path_part
    return canonical_path


async def run_ssh_command(
    ssh_args: list[str],
    cmd: str,
    timeout: float = 10.0,
) -> Optional[str]:
    """Run a single command via SSH, returning stdout text or None on any failure."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ssh", *ssh_args, cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        if proc.returncode != 0:
            return None
        return stdout.decode(errors="replace").strip()
    except Exception as exc:
        logger.debug("SSH command failed (%s): %s", ssh_args[-1], exc)
        return None
