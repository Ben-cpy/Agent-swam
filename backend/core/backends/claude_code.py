from typing import AsyncIterator, Optional, Callable, Awaitable, Union
from .base import BackendAdapter
import os


class ClaudeCodeAdapter(BackendAdapter):
    """Adapter for Claude Code CLI"""

    def build_command(self, prompt: str) -> list[str]:
        """
        Build Claude Code command with streaming JSON output.

        Format: claude -p --output-format stream-json --dangerously-skip-permissions <prompt>
        """
        # Unset CLAUDECODE env var to allow execution (prevents nested session error)
        # This will be handled in execution environment

        return [
            "claude",
            "-p",  # Project mode
            "--output-format", "stream-json",
            "--dangerously-skip-permissions",
            prompt
        ]

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
        - etc.
        """
        cmd = self.build_command(prompt)

        # Temporarily unset CLAUDECODE env var for subprocess
        env = os.environ.copy()
        if "CLAUDECODE" in env:
            del env["CLAUDECODE"]

        exit_code = 0

        async for line, code in self.run_subprocess(cmd, env=env, should_terminate=should_terminate):
            if line:
                yield line
            if code != 0:
                exit_code = code

        # Yield exit code info
        yield f"\n[Process exited with code {exit_code}]\n"

    def parse_exit_code(self, return_code: int) -> tuple[bool, Optional[str]]:
        """
        Parse exit code from Claude Code.

        0 = success
        1 = general error (could be CODE, TOOL, or UNKNOWN)
        130 = user interrupt (SIGINT), mapped by executor to CANCELLED status
        Other = network or system error
        """
        if return_code == 0:
            return (True, None)
        elif return_code == 130:
            return (False, None)
        elif return_code == 1:
            # Need to analyze logs to determine exact error class
            # For M1, default to TOOL
            return (False, "TOOL")
        else:
            return (False, "NETWORK")
