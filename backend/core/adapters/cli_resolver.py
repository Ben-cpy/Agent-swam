import os
import shutil
from typing import List


def _candidate_names(cli_name: str) -> List[str]:
    if os.name == "nt":
        return [
            f"{cli_name}.cmd",
            f"{cli_name}.exe",
            f"{cli_name}.bat",
            cli_name,
        ]
    return [cli_name]


def resolve_cli(cli_name: str) -> str:
    """
    Resolve CLI executable path across platforms.
    On Windows, prefer .cmd because create_subprocess_exec cannot run PowerShell aliases.
    """
    candidates = _candidate_names(cli_name)

    # First try PATH lookup.
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved

    # Then try npm global bin explicitly (common on Windows).
    appdata = os.environ.get("APPDATA")
    if appdata:
        npm_bin = os.path.join(appdata, "npm")
        for candidate in candidates:
            path = os.path.join(npm_bin, candidate)
            if os.path.isfile(path):
                return path

    candidate_display = ", ".join(candidates)
    raise FileNotFoundError(
        f"{cli_name} CLI not found. Tried: {candidate_display}. "
        f"Please ensure it is installed and available in PATH."
    )
