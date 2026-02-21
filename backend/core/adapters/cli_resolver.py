import os
import shutil
import shlex
import subprocess
from typing import Dict, List, Optional


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
    seen_paths: set[str] = set()

    def _normalize(path: str) -> str:
        return os.path.normcase(os.path.normpath(path))

    def _append_shell(name: str, path: Optional[str]) -> bool:
        if not path:
            return False
        expanded = os.path.expandvars(os.path.expanduser(path.strip().strip('"')))
        if not os.path.isfile(expanded):
            return False
        key = _normalize(expanded)
        if key in seen_paths:
            return False
        seen_paths.add(key)
        shells.append((name, expanded))
        return True

    def _which(*names: str) -> Optional[str]:
        for name in names:
            resolved = shutil.which(name)
            if resolved:
                return resolved
        return None

    def _candidate_git_bash_paths() -> List[str]:
        candidates: List[str] = []

        # Allow explicit override for non-standard installs.
        for env_key in ("AI_SLAVE_GIT_BASH", "GIT_BASH_PATH"):
            value = os.environ.get(env_key)
            if value:
                candidates.append(value)

        program_roots = [
            os.environ.get("ProgramW6432"),
            os.environ.get("ProgramFiles"),
            os.environ.get("ProgramFiles(x86)"),
            os.environ.get("LocalAppData"),
        ]
        for root in filter(None, program_roots):
            candidates.append(os.path.join(root, "Git", "bin", "bash.exe"))
            candidates.append(os.path.join(root, "Git", "usr", "bin", "bash.exe"))

        local_appdata = os.environ.get("LocalAppData")
        if local_appdata:
            candidates.append(os.path.join(local_appdata, "Programs", "Git", "bin", "bash.exe"))
            candidates.append(os.path.join(local_appdata, "Programs", "Git", "usr", "bin", "bash.exe"))

        return candidates

    for candidate in _candidate_git_bash_paths():
        if _append_shell("git-bash", candidate):
            break
    else:
        bash_path = _which("bash.exe", "bash")
        _append_shell("git-bash", bash_path)

    _append_shell("cmd", _which("cmd.exe", "cmd"))

    _append_shell("powershell", _which("pwsh.exe", "pwsh", "powershell.exe", "powershell"))

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
    shell_argv = [cli_name, *args]
    direct_argv = [direct_cmd[0], *args] if direct_cmd else shell_argv

    for shell_name, shell_path in resolve_windows_shell_priority():
        if shell_name == "git-bash":
            variants.append((shell_name, [shell_path, "-c", shlex.join(shell_argv)]))
        elif shell_name == "cmd":
            variants.append((shell_name, [shell_path, "/d", "/s", "/c", subprocess.list2cmdline(direct_argv)]))
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
                    _to_powershell_command(direct_argv),
                ],
            ))

    variants.append(("direct", direct_cmd))
    return variants


def build_windows_env_overrides(cli_name: Optional[str] = None) -> Dict[str, str]:
    """
    Build Windows-specific environment overrides to stabilize shell behavior.
    """
    if os.name != "nt":
        return {}

    shells = resolve_windows_shell_priority()
    shell_map: Dict[str, str] = {name: path for name, path in shells}
    overrides: Dict[str, str] = {}

    cmd_path = shell_map.get("cmd")
    if cmd_path:
        overrides["COMSPEC"] = cmd_path

    git_bash_path = shell_map.get("git-bash")
    if git_bash_path:
        overrides["SHELL"] = git_bash_path
        if cli_name == "claude":
            # Claude Code supports forcing a concrete shell via env var.
            overrides["CLAUDE_CODE_SHELL"] = git_bash_path

    return overrides


def apply_windows_env_overrides(
    base_env: Optional[dict] = None,
    cli_name: Optional[str] = None,
) -> Optional[dict]:
    """
    Merge Windows shell overrides into an environment dict.
    """
    if os.name != "nt":
        return base_env

    env = (base_env or os.environ.copy()).copy()
    env.update(build_windows_env_overrides(cli_name=cli_name))
    return env
