import asyncio
import base64
import json
import logging
import os
import shlex
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.adapters import ClaudeCodeAdapter, CodexAdapter, CopilotAdapter
from core.ssh_utils import build_ssh_connection_args, extract_remote_path, run_ssh_command
from models import ErrorClass, Run, Runner, Task, TaskStatus, Workspace, WorkspaceType

logger = logging.getLogger(__name__)

# Module-level singleton for cancellation signals shared across all TaskExecutor instances
_cancelled_task_ids: set[int] = set()


class TaskExecutor:
    """Executes tasks using the appropriate backend adapter."""

    def __init__(self, db_session_maker):
        self.db_session_maker = db_session_maker

    async def _detect_current_branch(self, workspace_path: str) -> str:
        cmd = ["git", "-C", workspace_path, "rev-parse", "--abbrev-ref", "HEAD"]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            raise RuntimeError(f"Failed to detect branch: {stderr.decode(errors='replace').strip()}")
        branch = stdout.decode(errors="replace").strip()
        if not branch:
            raise RuntimeError("Failed to detect branch: empty output")
        return branch

    async def _branch_exists(self, workspace_path: str, branch_name: str) -> bool:
        """Check if a git branch exists in the given workspace."""
        process = await asyncio.create_subprocess_exec(
            "git", "-C", workspace_path, "rev-parse", "--verify", branch_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await process.communicate()
        return process.returncode == 0

    async def _is_valid_git_worktree(self, worktree_path: str) -> bool:
        if not os.path.isdir(worktree_path):
            return False
        git_marker = os.path.join(worktree_path, ".git")
        if not os.path.exists(git_marker):
            return False
        process = await asyncio.create_subprocess_exec(
            "git", "-C", worktree_path, "rev-parse", "--is-inside-work-tree",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await process.communicate()
        return process.returncode == 0

    def _pick_recovery_worktree_path(self, path: str) -> str:
        candidate = f"{path}-recovered"
        idx = 1
        while os.path.exists(candidate):
            candidate = f"{path}-recovered-{idx}"
            idx += 1
        return candidate

    async def _create_worktree(self, task_id: int, workspace_path: str, base_branch: str, target_path: Optional[str] = None) -> str:
        """Create or reuse a git worktree for a task."""
        worktree_path = target_path or f"{workspace_path}-task-{task_id}"
        worktree_branch = f"task-{task_id}"

        # Existing path: reuse only if it's a valid git worktree.
        if os.path.isdir(worktree_path):
            if await self._is_valid_git_worktree(worktree_path):
                logger.info(
                    "Worktree directory already exists at %s for task %s, reusing",
                    worktree_path,
                    task_id,
                )
                return worktree_path

            try:
                is_empty_dir = len(os.listdir(worktree_path)) == 0
            except OSError:
                is_empty_dir = False

            if is_empty_dir:
                os.rmdir(worktree_path)
                logger.warning(
                    "Removed empty invalid worktree directory %s for task %s",
                    worktree_path,
                    task_id,
                )
            else:
                fallback_path = self._pick_recovery_worktree_path(worktree_path)
                logger.warning(
                    "Path %s is not a valid worktree for task %s; using fallback path %s",
                    worktree_path,
                    task_id,
                    fallback_path,
                )
                worktree_path = fallback_path
        elif os.path.exists(worktree_path):
            fallback_path = self._pick_recovery_worktree_path(worktree_path)
            logger.warning(
                "Path %s is not a directory for task %s; using fallback path %s",
                worktree_path,
                task_id,
                fallback_path,
            )
            worktree_path = fallback_path

        if await self._branch_exists(workspace_path, worktree_branch):
            cmd = ["git", "-C", workspace_path, "worktree", "add", worktree_path, worktree_branch]
            logger.info(
                "Branch %s already exists; checking it out into %s for task %s",
                worktree_branch,
                worktree_path,
                task_id,
            )
        else:
            cmd = [
                "git", "-C", workspace_path,
                "worktree", "add",
                "-b", worktree_branch,
                worktree_path,
                base_branch,
            ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _stdout, stderr = await process.communicate()
        if process.returncode != 0:
            raise RuntimeError(f"Failed to create worktree: {stderr.decode(errors='replace').strip()}")
        logger.info(
            "Created worktree for task %s at %s",
            task_id,
            worktree_path,
        )
        return worktree_path

    # ------------------------------------------------------------------
    # Remote worktree helpers for SSH workspaces
    # ------------------------------------------------------------------

    async def _detect_remote_branch(
        self,
        ssh_args: list[str],
        remote_path: str,
        workspace_type: WorkspaceType,
        container_name: Optional[str],
    ) -> str:
        """Detect current git branch on the remote host."""
        if workspace_type == WorkspaceType.SSH_CONTAINER:
            cmd = f"docker exec -w {shlex.quote(remote_path)} {shlex.quote(container_name or '')} git rev-parse --abbrev-ref HEAD"
        else:
            cmd = f"git -C {shlex.quote(remote_path)} rev-parse --abbrev-ref HEAD"
        result = await run_ssh_command(ssh_args, cmd, timeout=15.0)
        return result or "main"

    async def _create_remote_worktree(
        self,
        ssh_args: list[str],
        task_id: int,
        remote_path: str,
        base_branch: str,
        workspace_type: WorkspaceType,
        container_name: Optional[str],
    ) -> str:
        """Create (or reuse) a git worktree on the remote host. Returns the remote worktree path."""
        worktree_branch = f"task-{task_id}"
        worktree_remote_path = f"{remote_path}-task-{task_id}"

        # Helper to build docker-wrapped or plain git commands
        def git_cmd(subcmd: str) -> str:
            if workspace_type == WorkspaceType.SSH_CONTAINER:
                return f"docker exec {shlex.quote(container_name or '')} git -C {shlex.quote(remote_path)} {subcmd}"
            return f"git -C {shlex.quote(remote_path)} {subcmd}"

        # Check if the worktree already exists (has a .git marker)
        if workspace_type == WorkspaceType.SSH_CONTAINER:
            wt_exists_cmd = (
                f"docker exec {shlex.quote(container_name or '')} "
                f"test -e {shlex.quote(worktree_remote_path + '/.git')} && echo EXISTS || echo NOT"
            )
        else:
            wt_exists_cmd = f"test -e {shlex.quote(worktree_remote_path + '/.git')} && echo EXISTS || echo NOT"

        wt_check = await run_ssh_command(ssh_args, wt_exists_cmd, timeout=10.0)
        if wt_check and "EXISTS" in wt_check:
            logger.info("Remote worktree at %s already exists, reusing for task %s", worktree_remote_path, task_id)
            return worktree_remote_path

        # Check if the branch already exists
        branch_check = await run_ssh_command(
            ssh_args,
            git_cmd(f"rev-parse --verify {shlex.quote(worktree_branch)}"),
            timeout=10.0,
        )
        branch_exists = branch_check is not None

        if branch_exists:
            add_subcmd = f"worktree add {shlex.quote(worktree_remote_path)} {shlex.quote(worktree_branch)}"
        else:
            add_subcmd = (
                f"worktree add -b {shlex.quote(worktree_branch)} "
                f"{shlex.quote(worktree_remote_path)} {shlex.quote(base_branch)}"
            )

        proc = await asyncio.create_subprocess_exec(
            "ssh", *ssh_args, git_cmd(add_subcmd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        if proc.returncode != 0:
            err = stderr.decode(errors="replace").strip()
            raise RuntimeError(f"Failed to create remote worktree: {err}")

        logger.info("Created remote worktree for task %s at %s", task_id, worktree_remote_path)
        return worktree_remote_path

    # ------------------------------------------------------------------
    # Main execution entry points
    # ------------------------------------------------------------------

    async def execute_task(self, task_id: int, db: Optional[AsyncSession] = None) -> bool:
        if db is None:
            async with self.db_session_maker() as session:
                return await self._execute_task_with_db(task_id, session)
        return await self._execute_task_with_db(task_id, db)

    async def _execute_task_with_db(self, task_id: int, db: AsyncSession) -> bool:
        task_result = await db.execute(select(Task).where(Task.id == task_id))
        task = task_result.scalar_one_or_none()
        if not task:
            logger.error("Task %s not found", task_id)
            return False

        if task.status != TaskStatus.TODO:
            logger.warning("Task %s is not in TODO status: %s", task_id, task.status)
            return False

        workspace_result = await db.execute(
            select(Workspace).where(Workspace.workspace_id == task.workspace_id)
        )
        workspace = workspace_result.scalar_one_or_none()
        if not workspace:
            logger.error("Workspace %s not found", task.workspace_id)
            return False

        is_ssh_workspace = workspace.workspace_type in (WorkspaceType.SSH, WorkspaceType.SSH_CONTAINER)

        runner_result = await db.execute(
            select(Runner).where(Runner.runner_id == workspace.runner_id)
        )
        runner = runner_result.scalar_one_or_none()
        if not runner:
            logger.error("Runner %s not found", workspace.runner_id)
            return False

        if is_ssh_workspace:
            return await self._start_ssh_task(task, workspace, runner, db)

        # Local workspace: detect branch and create worktree
        return await self._start_local_task(task, workspace, runner, db)

    async def _start_ssh_task(self, task: Task, workspace: Workspace, runner: Runner, db: AsyncSession) -> bool:
        """Prepare and launch an SSH workspace task."""
        task_id = task.id
        ssh_host = workspace.host
        if not ssh_host:
            task.status = TaskStatus.FAILED
            task.updated_at = datetime.now(timezone.utc)
            await db.commit()
            logger.error("SSH workspace %s has no host configured", workspace.workspace_id)
            return False

        ssh_port = workspace.port
        ssh_user = workspace.ssh_user
        container_name = workspace.container_name
        login_shell = getattr(workspace, "login_shell", "bash") or "bash"
        workspace_type = workspace.workspace_type

        ssh_args = build_ssh_connection_args(ssh_host, ssh_port, ssh_user)
        remote_path = extract_remote_path(workspace.path, workspace_type)

        # Detect base branch on remote
        if not task.branch_name:
            try:
                base_branch = await self._detect_remote_branch(
                    ssh_args, remote_path, workspace_type, container_name
                )
                task.branch_name = base_branch
                logger.info("Auto-detected remote base branch '%s' for task %s", base_branch, task_id)
            except Exception as exc:
                task.branch_name = "main"
                logger.warning("Failed to detect remote branch for task %s, fallback to 'main': %s", task_id, exc)
            task.updated_at = datetime.now(timezone.utc)
            await db.commit()

        base_branch = task.branch_name or "main"

        # Create git worktree on the remote host
        try:
            worktree_remote_path = await self._create_remote_worktree(
                ssh_args=ssh_args,
                task_id=task_id,
                remote_path=remote_path,
                base_branch=base_branch,
                workspace_type=workspace_type,
                container_name=container_name,
            )
            if task.worktree_path != worktree_remote_path:
                task.worktree_path = worktree_remote_path
                task.updated_at = datetime.now(timezone.utc)
                await db.commit()
        except Exception as exc:
            task.status = TaskStatus.FAILED
            task.updated_at = datetime.now(timezone.utc)
            await db.commit()
            logger.error("Task %s failed: could not create remote worktree: %s", task_id, exc)
            return False

        tmux_session_name = f"aitask-{task_id}"
        run = Run(
            task_id=task.id,
            runner_id=runner.runner_id,
            backend=task.backend.value,
            started_at=datetime.now(timezone.utc),
            tmux_session=tmux_session_name,
        )
        db.add(run)
        await db.flush()

        task.status = TaskStatus.RUNNING
        task.run_id = run.run_id
        task.updated_at = datetime.now(timezone.utc)
        run_id = run.run_id
        backend_value = task.backend.value
        prompt_text = task.prompt
        model_name = task.model
        permission_mode = task.permission_mode
        worktree_remote_path = task.worktree_path or remote_path
        task_pk = task.id
        await db.commit()

        logger.info(
            "Starting SSH task %s on host %s (port=%s) in tmux session %s, worktree=%s, model=%s",
            task_id,
            ssh_host,
            ssh_port,
            tmux_session_name,
            worktree_remote_path,
            model_name,
        )

        asyncio.create_task(
            self._run_ssh_task(
                task_id=task_pk,
                run_id=run_id,
                ssh_host=ssh_host,
                ssh_port=ssh_port,
                ssh_user=ssh_user,
                container_name=container_name,
                workspace_type=workspace_type,
                remote_path=worktree_remote_path,
                backend=backend_value,
                prompt=prompt_text,
                model=model_name,
                tmux_session=tmux_session_name,
                permission_mode=permission_mode,
                login_shell=login_shell,
            )
        )
        return True

    async def _start_local_task(self, task: Task, workspace: Workspace, runner: Runner, db: AsyncSession) -> bool:
        """Prepare and launch a local workspace task."""
        task_id = task.id

        if not task.branch_name:
            try:
                task.branch_name = await self._detect_current_branch(workspace.path)
                logger.info("Auto-detected base branch '%s' for task %s", task.branch_name, task_id)
            except Exception as exc:
                task.branch_name = "main"
                logger.warning(
                    "Failed to auto-detect base branch for task %s, fallback to 'main': %s",
                    task_id,
                    exc,
                )
            task.updated_at = datetime.now(timezone.utc)
            await db.commit()

        try:
            desired_path = task.worktree_path
            worktree_path = await self._create_worktree(
                task_id,
                workspace.path,
                task.branch_name,
                target_path=desired_path,
            )
            if task.worktree_path != worktree_path:
                task.worktree_path = worktree_path
                task.updated_at = datetime.now(timezone.utc)
                await db.commit()
        except Exception as exc:
            task.status = TaskStatus.FAILED
            task.updated_at = datetime.now(timezone.utc)
            await db.commit()
            logger.error("Task %s failed before execution due to worktree error: %s", task_id, exc)
            return False

        run = Run(
            task_id=task.id,
            runner_id=runner.runner_id,
            backend=task.backend.value,
            started_at=datetime.now(timezone.utc),
        )
        db.add(run)
        await db.flush()

        task.status = TaskStatus.RUNNING
        task.run_id = run.run_id
        task.updated_at = datetime.now(timezone.utc)
        task_backend = task.backend
        backend_value = task.backend.value
        task_worktree_path = task.worktree_path
        run_id = run.run_id
        task_pk = task.id
        prompt_text = task.prompt
        model_name = task.model
        permission_mode = task.permission_mode
        effective_workspace_path = task_worktree_path or workspace.path
        await db.commit()

        logger.info(
            "Starting task %s with backend %s in worktree %s",
            task_id,
            task_backend,
            task_worktree_path,
        )

        asyncio.create_task(
            self._run_task(
                task_id=task_pk,
                run_id=run_id,
                workspace_path=effective_workspace_path,
                backend=backend_value,
                prompt=prompt_text,
                model=model_name,
                permission_mode=permission_mode,
            )
        )
        return True

    async def _run_task(
        self,
        task_id: int,
        run_id: int,
        workspace_path: str,
        backend: str,
        prompt: str,
        model: Optional[str] = None,
        permission_mode: Optional[str] = None,
    ):
        try:
            if backend == "claude_code":
                adapter = ClaudeCodeAdapter(workspace_path, model=model, permission_mode=permission_mode)
            elif backend == "codex_cli":
                adapter = CodexAdapter(workspace_path, model=model)
            elif backend == "copilot_cli":
                adapter = CopilotAdapter(workspace_path, model=model)
            else:
                raise ValueError(f"Unknown backend: {backend}")

            log_lines = []
            exit_code = None
            last_flush_time = asyncio.get_event_loop().time()
            flushed_blob_len = 0

            async def _flush_logs_to_db():
                nonlocal last_flush_time, flushed_blob_len
                current_blob = "".join(log_lines)
                if len(current_blob) <= flushed_blob_len:
                    return
                try:
                    async with self.db_session_maker() as flush_db:
                        run_res = await flush_db.execute(select(Run).where(Run.run_id == run_id))
                        run_obj = run_res.scalar_one_or_none()
                        if run_obj and not run_obj.ended_at:
                            run_obj.log_blob = current_blob
                            await flush_db.commit()
                    flushed_blob_len = len(current_blob)
                except Exception as flush_exc:
                    logger.warning("Failed to flush logs for run %s: %s", run_id, flush_exc)
                last_flush_time = asyncio.get_event_loop().time()

            async for line in adapter.execute(
                prompt,
                should_terminate=lambda: self._is_task_marked_cancelled(task_id),
            ):
                log_lines.append(line)
                if "[Process exited with code" in line:
                    try:
                        exit_code = int(line.split("code ")[1].split("]")[0])
                    except Exception:
                        pass

                now = asyncio.get_event_loop().time()
                if now - last_flush_time >= 2.0:
                    await _flush_logs_to_db()

            if exit_code is None:
                exit_code = 1

            success, error_class_str = adapter.parse_exit_code(exit_code)
            was_cancelled = exit_code == 130 or self._is_task_marked_cancelled(task_id)

            await self._persist_execution_result(
                task_id=task_id,
                run_id=run_id,
                exit_code=exit_code,
                success=success,
                error_class_str=error_class_str,
                log_blob="".join(log_lines),
                was_cancelled=was_cancelled,
                usage_data=adapter.usage_data,
                is_quota_error=adapter.is_quota_error,
            )
        except Exception as exc:
            logger.error("Error executing task %s: %s", task_id, exc, exc_info=True)
            await self._persist_internal_error(task_id, run_id, str(exc))
        finally:
            _cancelled_task_ids.discard(task_id)

    async def _run_ssh_task(
        self,
        task_id: int,
        run_id: int,
        ssh_host: str,
        ssh_port: Optional[int],
        ssh_user: Optional[str],
        container_name: Optional[str],
        workspace_type: WorkspaceType,
        remote_path: str,
        backend: str,
        prompt: str,
        tmux_session: str,
        model: Optional[str] = None,
        permission_mode: Optional[str] = None,
        login_shell: str = "bash",
    ):
        """Run a task on a remote SSH host using tmux for session persistence.

        - remote_path: the actual remote worktree directory to execute in.
        - For SSH_CONTAINER workspaces, commands are wrapped with docker exec.
        - Shell quoting is avoided by base64-encoding the script and writing it to a temp file.
        """
        log_file = f"/tmp/{tmux_session}.log"
        script_file = f"/tmp/{tmux_session}.sh"
        try:
            ssh_args = build_ssh_connection_args(ssh_host, ssh_port, ssh_user)

            # Build the AI CLI commands for the remote Linux shell.
            # Strategy: base64-encode the prompt so it's safe to embed anywhere, then decode
            # it into a shell variable $PROMPT. All AI commands reference "$PROMPT".
            # The entire script is base64-encoded when transferred, so no shell escaping needed
            # for the script content itself.
            prompt_b64 = base64.b64encode(prompt.encode()).decode()
            # prompt_b64 contains only [A-Za-z0-9+/=] – safe to embed in any quoting context

            # Use a unique variable name to avoid conflicts with shell builtins.
            # In zsh, $PROMPT is the prompt string (overwritten by .zshrc), so we must NOT
            # use $PROMPT as our variable — we use $_AITASK_PROMPT instead.
            _var = "_AITASK_PROMPT"

            if backend == "claude_code":
                if permission_mode and permission_mode != "bypassPermissions":
                    perm_flag = f"--permission-mode {permission_mode}"
                elif permission_mode == "bypassPermissions":
                    # --dangerously-skip-permissions is blocked when running as root (common in
                    # containers). Use --permission-mode dontAsk as equivalent for automation.
                    perm_flag = "--permission-mode dontAsk"
                else:
                    # Default for SSH tasks: dontAsk avoids interactive prompts and works as root
                    perm_flag = "--permission-mode dontAsk"
                ai_cmd = f'claude -p --output-format stream-json {perm_flag} "${_var}"'
            elif backend == "codex_cli":
                # Always pass --model to prevent codex from attempting to refresh model list
                # (which times out when no model is pre-selected).
                # Use --dangerously-bypass-approvals-and-sandbox for non-interactive execution;
                # this is the correct flag in codex >=0.100 (replaces --ask-for-approval never).
                _effective_model = model or "gpt-5.1-codex"
                ai_cmd = (
                    f'printf "%s" "${_var}" | '
                    f"codex exec --json --dangerously-bypass-approvals-and-sandbox "
                    f"-m {shlex.quote(_effective_model)} "
                    f"-C {shlex.quote(remote_path)} -"
                )
            elif backend == "copilot_cli":
                ai_cmd = f'copilot --allow-all --no-color --no-alt-screen -p "${_var}"'
            else:
                raise ValueError(f"Unknown backend: {backend}")

            # Validate login_shell to a known safe value
            _shell = login_shell if login_shell in ("bash", "zsh", "sh") else "bash"

            # NVM loader + proxy loader used by all paths.
            # Source ~/proxy.sh if it exists so outbound requests work on machines
            # that require a proxy (common in corporate/lab environments).
            _nvm_preamble = (
                "source /root/.nvm/nvm.sh 2>/dev/null; "
                "source ~/.nvm/nvm.sh 2>/dev/null; "
                "[ -f ~/proxy.sh ] && source ~/proxy.sh 2>/dev/null; "
            )

            # Build the full command that runs inside the target environment.
            #
            # Key design: for zsh we must decode _AITASK_PROMPT INSIDE the zsh -c body
            # (after zsh startup files run), not before. If we set the var before `zsh --login`,
            # .zshrc prompt-setting code may indirectly reset it. Embedding the b64 decode at
            # the start of the -c body is safe because prompt_b64 is [A-Za-z0-9+/=] only.
            #
            # For bash/sh: decode in the preamble, then source rc file (order doesn't matter
            # because bash's $PROMPT is not special and won't be overwritten by .bashrc).
            # zsh startup file note:
            # `zsh --login -c 'cmd'` is a login but NON-interactive shell.
            # Zsh only sources .zshrc for interactive shells, so proxy/PATH set in .zshrc
            # would NOT be loaded. Fix: explicitly source ~/.zshrc inside the -c body.
            # Order: .zshenv + .zprofile (via --login) → .zshrc (explicit) → decode → run.

            if workspace_type == WorkspaceType.SSH_CONTAINER:
                if _shell == "zsh":
                    _zsh_body = (
                        f"source ~/.zshrc 2>/dev/null; "
                        f"{_var}=$(echo {prompt_b64} | base64 -d); "
                        f"{_nvm_preamble}"
                        f"cd {shlex.quote(remote_path)} && {ai_cmd}"
                    )
                    exec_cmd = (
                        f"docker exec -w {shlex.quote(remote_path)} "
                        f"{shlex.quote(container_name or '')} "
                        f"zsh --login -c {shlex.quote(_zsh_body)}"
                    )
                else:
                    # Bash path inside container: decode + source bashrc, then run.
                    # Escape $ → \$ and " → \" so outer bash doesn't expand them before
                    # passing the string to the inner docker exec bash -c.
                    bash_preamble = (
                        f"{_nvm_preamble}"
                        f"source ~/.bashrc 2>/dev/null; "
                        f"{_var}=$(echo {prompt_b64} | base64 -d); "
                    )
                    inner_cmd = f"{bash_preamble}cd {shlex.quote(remote_path)} && {ai_cmd}"
                    inner_cmd_escaped = inner_cmd.replace("$", r"\$").replace('"', '\\"')
                    exec_cmd = (
                        f"docker exec -w {shlex.quote(remote_path)} "
                        f"{shlex.quote(container_name or '')} "
                        f'bash -c "{inner_cmd_escaped}"'
                    )
            elif _shell == "zsh":
                # Regular SSH + zsh: explicitly source .zshrc for proxy/PATH (non-interactive)
                _zsh_body = (
                    f"source ~/.zshrc 2>/dev/null; "
                    f"{_var}=$(echo {prompt_b64} | base64 -d); "
                    f"{_nvm_preamble}"
                    f"cd {shlex.quote(remote_path)} && {ai_cmd}"
                )
                exec_cmd = f"zsh --login -c {shlex.quote(_zsh_body)}"
            else:
                # Default bash path: source ~/.bashrc first, then decode prompt
                shell_preamble = (
                    f"{_nvm_preamble}"
                    f"source ~/.bashrc 2>/dev/null; "
                    f"{_var}=$(echo {prompt_b64} | base64 -d); "
                )
                exec_cmd = f"{shell_preamble}cd {shlex.quote(remote_path)} && {ai_cmd}"

            # Write the script to the remote host using base64 to avoid quoting issues.
            # Use direct redirect (>) instead of tee to avoid stdio block-buffering on the log file.
            # tee uses 4-8KB block buffering for file writes, causing tail -f to see no output
            # until the buffer fills. Direct redirect lets the OS write syscalls go straight through.
            script_content = (
                f"#!/bin/bash\n"
                f"({exec_cmd}) > {shlex.quote(log_file)} 2>&1\n"
                f"echo EXIT_CODE:$? >> {shlex.quote(log_file)}\n"
            )
            encoded_script = base64.b64encode(script_content.encode()).decode()

            # Two-step remote command: decode+write script, then launch via tmux
            # base64 output is safe to single-quote (only [A-Za-z0-9+/=])
            setup_and_launch = (
                f"printf '%s' '{encoded_script}' | base64 -d > {shlex.quote(script_file)} && "
                f"chmod +x {shlex.quote(script_file)} && "
                f"tmux new-session -d -s {shlex.quote(tmux_session)} bash {shlex.quote(script_file)}"
            )

            launch_proc = await asyncio.create_subprocess_exec(
                "ssh", *ssh_args, setup_and_launch,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _stdout, stderr = await launch_proc.communicate()
            if launch_proc.returncode != 0:
                err_msg = stderr.decode(errors="replace").strip()
                raise RuntimeError(f"Failed to start SSH tmux session: {err_msg}")

            logger.info("SSH tmux session %s started on %s:%s", tmux_session, ssh_host, ssh_port)

            # Stream the log file from the remote host.
            # Use tail -F (capital F) which retries if the file doesn't exist yet,
            # avoiding the race condition where the tmux session hasn't created the file yet.
            tail_proc = await asyncio.create_subprocess_exec(
                "ssh", *ssh_args, f"tail -F {shlex.quote(log_file)}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            log_lines = []
            exit_code = None
            last_flush_time = asyncio.get_event_loop().time()
            flushed_blob_len = 0

            async def _flush_ssh_logs_to_db():
                nonlocal last_flush_time, flushed_blob_len
                current_blob = "".join(log_lines)
                if len(current_blob) <= flushed_blob_len:
                    return
                try:
                    async with self.db_session_maker() as flush_db:
                        run_res = await flush_db.execute(select(Run).where(Run.run_id == run_id))
                        run_obj = run_res.scalar_one_or_none()
                        if run_obj and not run_obj.ended_at:
                            run_obj.log_blob = current_blob
                            await flush_db.commit()
                    flushed_blob_len = len(current_blob)
                except Exception as flush_exc:
                    logger.warning("Failed to flush SSH logs for run %s: %s", run_id, flush_exc)
                last_flush_time = asyncio.get_event_loop().time()

            assert tail_proc.stdout is not None
            async for raw_line in tail_proc.stdout:
                line = raw_line.decode(errors="replace")
                log_lines.append(line)

                if self._is_task_marked_cancelled(task_id):
                    tail_proc.terminate()
                    # Kill tmux session on remote
                    await asyncio.create_subprocess_exec(
                        "ssh", *ssh_args,
                        f"tmux kill-session -t {shlex.quote(tmux_session)} 2>/dev/null || true",
                    )
                    break

                if line.startswith("EXIT_CODE:"):
                    try:
                        exit_code = int(line.strip().split("EXIT_CODE:")[1])
                    except Exception:
                        exit_code = 1
                    tail_proc.terminate()
                    break

                now = asyncio.get_event_loop().time()
                if now - last_flush_time >= 2.0:
                    await _flush_ssh_logs_to_db()

            if exit_code is None:
                exit_code = 1

            success = exit_code == 0
            error_class_str = None if success else "UNKNOWN"
            was_cancelled = self._is_task_marked_cancelled(task_id)

            await self._persist_execution_result(
                task_id=task_id,
                run_id=run_id,
                exit_code=exit_code,
                success=success and not was_cancelled,
                error_class_str=error_class_str,
                log_blob="".join(log_lines),
                was_cancelled=was_cancelled,
            )
        except Exception as exc:
            logger.error("Error executing SSH task %s: %s", task_id, exc, exc_info=True)
            await self._persist_internal_error(task_id, run_id, str(exc))
        finally:
            _cancelled_task_ids.discard(task_id)
            # Clean up temporary log and script files on remote host
            try:
                ssh_args = build_ssh_connection_args(ssh_host, ssh_port, ssh_user)
                await asyncio.create_subprocess_exec(
                    "ssh", *ssh_args,
                    f"rm -f {shlex.quote(log_file)} {shlex.quote(script_file)}",
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
            except Exception:
                pass

    async def _persist_execution_result(
        self,
        task_id: int,
        run_id: int,
        exit_code: int,
        success: bool,
        error_class_str: Optional[str],
        log_blob: str,
        was_cancelled: bool,
        usage_data: Optional[dict] = None,
        is_quota_error: bool = False,
    ):
        async with self.db_session_maker() as db:
            task_result = await db.execute(select(Task).where(Task.id == task_id))
            task = task_result.scalar_one_or_none()
            run_result = await db.execute(select(Run).where(Run.run_id == run_id))
            run = run_result.scalar_one_or_none()
            if not task or not run:
                logger.error("Task/run not found while persisting result (task=%s, run=%s)", task_id, run_id)
                return

            run.ended_at = datetime.now(timezone.utc)
            if usage_data:
                run.usage_json = json.dumps(usage_data)

            if was_cancelled:
                run.exit_code = 130
                run.error_class = ErrorClass.UNKNOWN
                task.status = TaskStatus.FAILED
            elif is_quota_error and not success:
                run.exit_code = exit_code
                run.error_class = ErrorClass.QUOTA
                task.status = TaskStatus.FAILED
            else:
                run.exit_code = exit_code
                if success:
                    task.status = TaskStatus.TO_BE_REVIEW
                    run.error_class = None
                else:
                    task.status = TaskStatus.FAILED
                    if error_class_str and error_class_str in ErrorClass.__members__:
                        run.error_class = ErrorClass[error_class_str]
                    else:
                        run.error_class = ErrorClass.UNKNOWN

            if log_blob:
                run.log_blob = log_blob

            task.updated_at = datetime.now(timezone.utc)
            await db.commit()
            logger.info("Task %s completed with status %s", task_id, task.status)

    async def _persist_internal_error(self, task_id: int, run_id: int, error_msg: str):
        async with self.db_session_maker() as db:
            task_result = await db.execute(select(Task).where(Task.id == task_id))
            task = task_result.scalar_one_or_none()
            run_result = await db.execute(select(Run).where(Run.run_id == run_id))
            run = run_result.scalar_one_or_none()
            if not task or not run:
                return

            was_cancelled = self._is_task_marked_cancelled(task_id)
            run.ended_at = datetime.now(timezone.utc)
            run.exit_code = 130 if was_cancelled else -1
            run.error_class = ErrorClass.UNKNOWN
            run.log_blob = f"Internal error: {error_msg}"

            task.status = TaskStatus.FAILED
            task.updated_at = datetime.now(timezone.utc)
            await db.commit()

    def _is_task_marked_cancelled(self, task_id: int) -> bool:
        return task_id in _cancelled_task_ids

    async def cancel_task(self, task_id: int, db: Optional[AsyncSession] = None) -> bool:
        if db is None:
            async with self.db_session_maker() as session:
                return await self._cancel_task_with_db(task_id, session)
        return await self._cancel_task_with_db(task_id, db)

    async def _cancel_task_with_db(self, task_id: int, db: AsyncSession) -> bool:
        result = await db.execute(select(Task).where(Task.id == task_id))
        task = result.scalar_one_or_none()
        if not task:
            return False

        if task.status not in [TaskStatus.TODO, TaskStatus.RUNNING]:
            return False

        was_running = task.status == TaskStatus.RUNNING
        task.status = TaskStatus.FAILED
        task.updated_at = datetime.now(timezone.utc)

        if was_running:
            _cancelled_task_ids.add(task.id)

        if task.run_id:
            result = await db.execute(select(Run).where(Run.run_id == task.run_id))
            run = result.scalar_one_or_none()
            if run:
                run.ended_at = datetime.now(timezone.utc)
                run.exit_code = 130
                run.error_class = ErrorClass.UNKNOWN

        await db.commit()
        logger.info("Task %s cancelled (mapped to FAILED)", task_id)
        return True
