from typing import AsyncIterator, Optional
from .base import BackendAdapter
import json


class CodexAdapter(BackendAdapter):
    """Adapter for Codex CLI"""

    def build_command(self, prompt: str) -> list[str]:
        """
        Build Codex CLI command.

        Format: codex exec --json --sandbox danger-full-access --cd <workspace> "<prompt>"
        """
        return [
            "codex",
            "exec",
            "--json",  # Output JSONL events
            "--sandbox", "danger-full-access",  # Allow full filesystem access
            "--cd", self.workspace_path,  # Set working directory
            "--skip-git-repo-check",  # Allow running outside git repo
            prompt
        ]

    async def execute(self, prompt: str) -> AsyncIterator[str]:
        """
        Execute Codex CLI and yield log lines.

        Codex outputs JSONL format with events like:
        - {"type": "turn.started", ...}
        - {"type": "message.text", "text": "..."}
        - {"type": "tool.use", ...}
        - {"type": "turn.completed", ...}
        """
        cmd = self.build_command(prompt)

        log_lines = []
        exit_code = 0

        async for line, code in self.run_subprocess(cmd):
            if line.strip():
                # Try to parse JSONL and extract readable content
                formatted_line = self._format_jsonl_line(line)
                if formatted_line:
                    log_lines.append(formatted_line)
                    yield formatted_line
            if code != 0:
                exit_code = code

        # Yield exit code info
        yield f"\n[Process exited with code {exit_code}]\n"

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
        130 = user interrupt
        Other = system error
        """
        if return_code == 0:
            return (True, None)
        elif return_code == 130:
            return (False, "CANCELLED")
        elif return_code == 1:
            # Default to CODE error for M1
            return (False, "CODE")
        else:
            return (False, "NETWORK")
