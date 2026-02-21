from typing import AsyncIterator, Optional, Callable, Awaitable, Union
from .base import BackendAdapter
from .cli_resolver import apply_windows_env_overrides, build_windows_env_overrides, resolve_cli
import json


class CodexAdapter(BackendAdapter):
    """Adapter for Codex CLI"""

    def __init__(
        self,
        workspace_path: str,
        model: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
    ):
        super().__init__(workspace_path)
        self.model = model
        self.reasoning_effort = reasoning_effort

    def build_command(self, prompt: str) -> list[str]:
        """
        Build Codex CLI command.

        Format: codex exec --json --sandbox danger-full-access --cd <workspace>
                --ask-for-approval never
                [--model <model>] [--reasoning-effort <effort>] -

        Prompt content is provided via stdin to avoid command-line length limits.
        """
        cmd = [
            resolve_cli("codex"),
            "exec",
            "--json",  # Output JSONL events
            "--ask-for-approval", "never",  # Non-interactive backend flow must not wait for approvals
            "--sandbox", "danger-full-access",  # Allow full filesystem access
            "--cd", self.workspace_path,  # Set working directory
            "--skip-git-repo-check",  # Allow running outside git repo
        ]
        windows_shell_env = build_windows_env_overrides(cli_name="codex")
        for key in ("COMSPEC", "SHELL"):
            value = windows_shell_env.get(key)
            if value:
                # Pass shell hints into Codex tool subprocess env.
                cmd += ["-c", f"shell_environment_policy.set.{key}={json.dumps(value)}"]
        if self.model:
            cmd += ["--model", self.model]
        if self.reasoning_effort:
            cmd += ["--reasoning-effort", self.reasoning_effort]
        cmd.append("-")
        return cmd

    async def execute(
        self,
        prompt: str,
        should_terminate: Optional[Callable[[], Union[bool, Awaitable[bool]]]] = None,
    ) -> AsyncIterator[str]:
        """
        Execute Codex CLI and yield log lines.

        Codex outputs JSONL format with events like:
        - {"type": "turn.started", ...}
        - {"type": "message.text", "text": "..."}
        - {"type": "tool.use", ...}
        - {"type": "turn.completed", "usage": {...}}
        """
        try:
            cmd = self.build_command(prompt)
        except FileNotFoundError as e:
            yield f"[ERROR] {e}\n"
            yield "\n[Process exited with code 127]\n"
            return

        exit_code = 0
        env = apply_windows_env_overrides(cli_name="codex")

        async for line, code in self.run_subprocess(
            cmd,
            env=env,
            stdin_data=prompt,
            should_terminate=should_terminate,
            cli_name="codex",
        ):
            if line:
                self._try_extract_from_jsonl(line)
                yield line
            if code != 0:
                exit_code = code

        # Yield exit code info
        yield f"\n[Process exited with code {exit_code}]\n"

    def _try_extract_from_jsonl(self, line: str):
        """Extract usage data and detect quota errors from JSONL events."""
        try:
            event = json.loads(line.strip())
        except json.JSONDecodeError:
            return

        event_type = event.get("type", "")

        # Extract usage from turn.completed
        if event_type == "turn.completed" and "usage" in event:
            usage = event["usage"]
            self._usage_data = {
                "input_tokens": usage.get("input_tokens"),
                "output_tokens": usage.get("output_tokens"),
                "total_tokens": usage.get("total_tokens"),
            }

        # Detect quota errors from error events
        if event_type == "error":
            msg = event.get("message", "").lower()
            code_val = event.get("code", "")
            code_str = str(code_val).lower() if code_val else ""
            quota_signals = [
                "rate limit", "rate_limit", "quota", "insufficient",
                "billing", "too many requests", "429"
            ]
            if any(kw in msg for kw in quota_signals) or any(kw in code_str for kw in quota_signals):
                self._is_quota_error = True


    def parse_exit_code(self, return_code: int) -> tuple[bool, Optional[str]]:
        """
        Parse exit code from Codex CLI.

        0 = success
        1 = general error
        130 = user interrupt, mapped by executor to FAILED status
        Other = system error
        """
        if return_code == 0:
            return (True, None)
        elif return_code == 130:
            return (False, None)
        elif return_code == 127:
            return (False, "TOOL")
        elif return_code == 1:
            if self._is_quota_error:
                return (False, "QUOTA")
            return (False, "CODE")
        else:
            return (False, "NETWORK")
