from typing import AsyncIterator, Optional, Callable, Awaitable, Union
from .base import BackendAdapter
from .cli_resolver import apply_windows_env_overrides, resolve_cli
import re


class CopilotAdapter(BackendAdapter):
    """Adapter for GitHub Copilot CLI"""

    def __init__(
        self,
        workspace_path: str,
        model: Optional[str] = None,
    ):
        super().__init__(workspace_path)
        self.model = model

    def build_command(self, prompt: str) -> list[str]:
        """
        Build GitHub Copilot CLI command.

        Format: copilot -p "<prompt>" --allow-all --no-color [--model <model>]
        """
        cmd = [
            resolve_cli("copilot"),
            "-p", prompt,
            "--allow-all",
            "--no-color",
            "--no-alt-screen",  # Disable alt-screen so stdout is captured
        ]
        if self.model:
            cmd += ["--model", self.model]
        return cmd

    async def execute(
        self,
        prompt: str,
        should_terminate: Optional[Callable[[], Union[bool, Awaitable[bool]]]] = None,
    ) -> AsyncIterator[str]:
        """
        Execute GitHub Copilot CLI and yield log lines.

        Copilot outputs plain text — each line is yielded as-is.
        """
        try:
            cmd = self.build_command(prompt)
        except FileNotFoundError as e:
            yield f"[ERROR] {e}\n"
            yield "\n[Process exited with code 127]\n"
            return

        exit_code = 0
        env = apply_windows_env_overrides(cli_name="copilot")

        async for line, code in self.run_subprocess(
            cmd,
            env=env,
            should_terminate=should_terminate,
            cli_name="copilot",
        ):
            if line:
                self._scan_for_quota_keywords(line)
                yield line
            if code != 0:
                exit_code = code

        yield f"\n[Process exited with code {exit_code}]\n"

    def _scan_for_quota_keywords(self, text: str):
        """Scan for quota/rate-limit error keywords in plain-text output."""
        lower = text.lower()
        quota_phrases = [
            "rate limit",
            "rate_limit",
            "quota exceeded",
            "insufficient credit",
            "billing error",
            "usage limit",
            "overloaded",
            "too many requests",
        ]
        has_429_signal = bool(
            re.search(r"\b(?:http|status|error|code)\s*[:=-]?\s*429\b", lower)
            or re.search(r"\b429\b.*\b(?:too many requests|rate limit|quota)\b", lower)
        )
        if any(kw in lower for kw in quota_phrases) or has_429_signal:
            self._is_quota_error = True

    def parse_exit_code(self, return_code: int) -> tuple[bool, Optional[str]]:
        """
        Parse exit code from GitHub Copilot CLI.

        0 = success
        1 = general error
        130 = user interrupt
        127 = CLI not found
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
