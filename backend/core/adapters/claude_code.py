from typing import AsyncIterator, Optional, Callable, Awaitable, Union
from .base import BackendAdapter
from .cli_resolver import apply_windows_env_overrides, resolve_cli
import json
import os


class ClaudeCodeAdapter(BackendAdapter):
    """Adapter for Claude Code CLI"""

    def __init__(
        self,
        workspace_path: str,
        model: Optional[str] = None,
        permission_mode: Optional[str] = None,
        extra_env: Optional[dict] = None,
    ):
        super().__init__(workspace_path, extra_env=extra_env)
        self.model = model
        self.permission_mode = permission_mode

    def build_command(self, prompt: str) -> list[str]:
        """
        Build Claude Code command with streaming JSON output.

        Format: claude -p --output-format stream-json --input-format text
                [--dangerously-skip-permissions | --permission-mode <mode>] [--model <model>]

        Prompt content is provided via stdin to avoid command-line length limits.
        """
        cmd = [
            resolve_cli("claude"),
            "-p",  # Project mode
            "--output-format", "stream-json",
            "--input-format", "text",
        ]
        mode = self.permission_mode
        if not mode or mode == "bypassPermissions":
            cmd.append("--dangerously-skip-permissions")
        else:
            cmd += ["--permission-mode", mode]
        if self.model:
            cmd += ["--model", self.model]
        return cmd

    async def execute(
        self,
        prompt: str,
        should_terminate: Optional[Callable[[], Union[bool, Awaitable[bool]]]] = None,
    ) -> AsyncIterator[str]:
        """
        Execute Claude Code and yield log lines.

        Claude Code outputs stream-json format with events like:
        - {"type": "text", "text": "..."}
        - {"type": "tool_use", "name": "...", ...}
        - {"type": "result", "cost_usd": ..., "total_cost_usd": ...}
        - {"type": "error", "error": {"type": "rate_limit_error", ...}}
        """
        try:
            cmd = self.build_command(prompt)
        except FileNotFoundError as e:
            yield f"[ERROR] {e}\n"
            yield "\n[Process exited with code 127]\n"
            return

        # Temporarily unset CLAUDECODE env var for subprocess
        env = os.environ.copy()
        if "CLAUDECODE" in env:
            del env["CLAUDECODE"]
        env = apply_windows_env_overrides(env, cli_name="claude")
        if self.extra_env:
            env.update(self.extra_env)

        exit_code = 0

        async for line, code in self.run_subprocess(
            cmd,
            env=env,
            stdin_data=prompt,
            should_terminate=should_terminate,
            cli_name="claude",
        ):
            if line:
                self._try_parse_stream_json(line)
                yield line
            if code != 0:
                exit_code = code

        # Yield exit code info
        yield f"\n[Process exited with code {exit_code}]\n"

    def _try_parse_stream_json(self, line: str):
        """Parse a stream-json line for usage data and quota errors."""
        stripped = line.strip()
        if not stripped:
            return
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            self._scan_for_quota_keywords(stripped)
            return

        event_type = event.get("type", "")

        # Extract usage from the final "result" event
        if event_type == "result":
            self._usage_data = {
                "cost_usd": event.get("cost_usd"),
                "total_cost_usd": event.get("total_cost_usd"),
                "duration_ms": event.get("duration_ms"),
                "duration_api_ms": event.get("duration_api_ms"),
                "num_turns": event.get("num_turns"),
            }

        # Detect quota/rate-limit errors from structured error events
        if event_type == "error":
            error_obj = event.get("error", {})
            error_type = error_obj.get("type", "") if isinstance(error_obj, dict) else ""
            error_msg = error_obj.get("message", "") if isinstance(error_obj, dict) else str(error_obj)
            if any(kw in error_type for kw in ["rate_limit", "overloaded", "billing"]):
                self._is_quota_error = True
            elif any(kw in error_msg.lower() for kw in [
                "rate limit", "quota", "insufficient credit", "billing",
                "usage limit", "overloaded"
            ]):
                self._is_quota_error = True

    def _scan_for_quota_keywords(self, text: str):
        """Fallback plain-text scan for quota error keywords."""
        lower = text.lower()
        quota_keywords = [
            "rate limit", "rate_limit", "quota exceeded",
            "insufficient credit", "billing error", "usage limit",
            "overloaded", "too many requests"
        ]
        if any(kw in lower for kw in quota_keywords):
            self._is_quota_error = True

    def parse_exit_code(self, return_code: int) -> tuple[bool, Optional[str]]:
        """
        Parse exit code from Claude Code.

        0 = success
        1 = general error (could be CODE, TOOL, or UNKNOWN)
        130 = user interrupt (SIGINT), mapped by executor to FAILED status
        Other = network or system error
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
            return (False, "TOOL")
        else:
            return (False, "NETWORK")
