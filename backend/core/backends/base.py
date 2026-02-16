from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional, List, Tuple, Callable, Awaitable, Union
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
    async def execute(
        self,
        prompt: str,
        should_terminate: Optional[Callable[[], Union[bool, Awaitable[bool]]]] = None,
    ) -> AsyncIterator[str]:
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

    async def run_subprocess(
        self,
        cmd: List[str],
        env: Optional[dict] = None,
        should_terminate: Optional[Callable[[], Union[bool, Awaitable[bool]]]] = None,
    ) -> AsyncIterator[Tuple[str, int]]:
        """
        Common subprocess runner that yields log lines and final exit code.

        Yields:
            Tuple[str, int]: (log_line, exit_code) - exit_code is 0 until process completes
        """
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=self.workspace_path,
            env=env,
        )

        async def _should_terminate() -> bool:
            if should_terminate is None:
                return False
            result = should_terminate()
            if asyncio.iscoroutine(result):
                result = await result
            return bool(result)

        # Stream output lines with periodic cancellation checks
        while True:
            if await _should_terminate():
                if process.returncode is None:
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=3)
                    except asyncio.TimeoutError:
                        process.kill()
                        await process.wait()
                yield ("", 130)
                return

            try:
                line = await asyncio.wait_for(process.stdout.readline(), timeout=0.5)
            except asyncio.TimeoutError:
                if process.returncode is not None:
                    break
                continue

            if not line:
                if process.returncode is not None:
                    break
                continue
            yield (line.decode('utf-8', errors='replace'), 0)

        # Wait for process to complete
        exit_code = await process.wait()
        yield ("", exit_code)  # Final yield with exit code
