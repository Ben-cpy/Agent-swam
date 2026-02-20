import os
import shutil
import shlex
import subprocess
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


def resolve_windows_shell_priority() -> List[tuple[str, str]]:
    """
    Resolve available Windows shells in preferred order:
    git-bash > cmd > powershell.
    """
    if os.name != "nt":
        return []

    shells: List[tuple[str, str]] = []

    git_bash_candidates = [
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
    ]
    for candidate in git_bash_candidates:
        if os.path.isfile(candidate):
            shells.append(("git-bash", candidate))
            break
    else:
        bash_path = shutil.which("bash")
        if bash_path:
            shells.append(("git-bash", bash_path))

    cmd_path = shutil.which("cmd.exe") or shutil.which("cmd")
    if cmd_path:
        shells.append(("cmd", cmd_path))

    ps_path = shutil.which("powershell.exe") or shutil.which("powershell")
    if ps_path:
        shells.append(("powershell", ps_path))

    return shells


def _to_powershell_command(argv: List[str]) -> str:
    quoted = [
        "'" + arg.replace("'", "''") + "'"
        for arg in argv
    ]
    return f"& {quoted[0]} {' '.join(quoted[1:])}".strip()


def build_windows_command_variants(cli_name: str, args: List[str], direct_cmd: List[str]) -> List[tuple[str, List[str]]]:
    """
    Build execution variants with shell fallback and direct exec as last resort.
    """
    variants: List[tuple[str, List[str]]] = []
    raw_argv = [cli_name, *args]

    for shell_name, shell_path in resolve_windows_shell_priority():
        if shell_name == "git-bash":
            variants.append((shell_name, [shell_path, "-lc", shlex.join(raw_argv)]))
        elif shell_name == "cmd":
            variants.append((shell_name, [shell_path, "/d", "/s", "/c", subprocess.list2cmdline(raw_argv)]))
        elif shell_name == "powershell":
            variants.append((
                shell_name,
                [
                    shell_path,
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    _to_powershell_command(raw_argv),
                ],
            ))

    variants.append(("direct", direct_cmd))
    return variants
