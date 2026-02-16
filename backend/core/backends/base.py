from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, Any, Optional, List, Tuple
import asyncio


class BackendAdapter(ABC):
    """Abstract base class for AI backend adapters"""

    def __init__(self, workspace_path: str):
        self.workspace_path = workspace_path

    @abstractmethod
    def build_command(self, prompt: str) -> List[str]:
        """Build the CLI command to execute"""
        pass

    @abstractmethod
    async def execute(self, prompt: str) -> AsyncIterator[str]:
        """
        Execute the prompt and yield log lines as they arrive.

        Yields:
            str: Log lines from the execution
        """
        pass

    @abstractmethod
    def parse_exit_code(self, return_code: int) -> Tuple[bool, Optional[str]]:
        """
        Parse the exit code and determine success/error class.

        Returns:
            tuple: (success: bool, error_class: Optional[str])
        """
        pass

    async def run_subprocess(self, cmd: List[str]) -> AsyncIterator[Tuple[str, int]]:
        """
        Common subprocess runner that yields log lines and final exit code.

        Yields:
            Tuple[str, int]: (log_line, exit_code) - exit_code is 0 until process completes
        """
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=self.workspace_path
        )

        # Stream output lines
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            yield (line.decode('utf-8', errors='replace'), 0)

        # Wait for process to complete
        exit_code = await process.wait()
        yield ("", exit_code)  # Final yield with exit code
