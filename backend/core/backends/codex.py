from typing import AsyncIterator, Optional, Callable, Awaitable, Union
from .base import BackendAdapter
from .cli_resolver import resolve_cli
import json


class CodexAdapter(BackendAdapter):
    """Adapter for Codex CLI"""

    def build_command(self, prompt: str) -> list[str]:
        """
        Build Codex CLI command.

        Format: codex exec --json --sandbox danger-full-access --cd <workspace> "<prompt>"
        """
        return [
            resolve_cli("codex"),
            "exec",
            "--json",  # Output JSONL events
            "--sandbox", "danger-full-access",  # Allow full filesystem access
            "--cd", self.workspace_path,  # Set working directory
            "--skip-git-repo-check",  # Allow running outside git repo
            prompt
        ]

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

        async for line, code in self.run_subprocess(cmd, should_terminate=should_terminate):
            if line.strip():
                self._try_extract_from_jsonl(line)
                # Try to parse JSONL and extract readable content
                formatted_line = self._format_jsonl_line(line)
                if formatted_line:
                    yield formatted_line
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

    def _format_jsonl_line(self, line: str) -> Optional[str]:
        """
        Format JSONL line into readable log output.

        Returns:
            Formatted string or None if line should be skipped
        """
        try:
            event = json.loads(line)
            event_type = event.get("type", "")

            if event_type == "message.text":
                return f"[Agent] {event.get('text', '')}\n"
            elif event_type == "tool.use":
                tool_name = event.get("name", "unknown")
                return f"[Tool] {tool_name}\n"
            elif event_type == "turn.started":
                return "[Turn started]\n"
            elif event_type == "turn.completed":
                return "[Turn completed]\n"
            elif event_type == "error":
                return f"[ERROR] {event.get('message', 'Unknown error')}\n"
            else:
                # Include raw event for debugging
                return f"[{event_type}] {line}"
        except json.JSONDecodeError:
            # Not valid JSON, return as-is
            return line
        except Exception as e:
            return f"[Parse error: {e}] {line}"

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
