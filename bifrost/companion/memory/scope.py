import hashlib
import os
import subprocess


def _get_git_remote_url() -> str | None:
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return None


def _is_git_repo() -> bool:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def get_project_hash() -> str:
    try:
        cwd = os.getcwd()
    except OSError:
        return "unknown"

    if _is_git_repo():
        url = _get_git_remote_url()
        if url:
            return hashlib.sha256(url.encode()).hexdigest()[:8]

    return hashlib.sha256(cwd.encode()).hexdigest()[:8]
