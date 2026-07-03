import os
import subprocess
from pathlib import Path

_FALSEY = {"0", "false", "no", "n", "off"}


def _run_git(repo_dir: Path, *args: str, check: bool = False) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    proc = subprocess.run(
        ["git", *args],
        cwd=str(repo_dir),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
    )
    output = (proc.stdout or "").strip()
    if output:
        print(output)
    if check and proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, proc.args, output=proc.stdout)
    return proc


def _disabled() -> bool:
    return str(os.getenv("GIT_STATE_AUTO_COMMIT", "1")).strip().lower() in _FALSEY


def _repo_dir() -> Path:
    return Path(__file__).resolve().parent


def _as_list(paths) -> list[str]:
    if isinstance(paths, (str, os.PathLike)):
        return [str(paths)]
    return [str(path) for path in paths]


def _relative_path(repo_dir: Path, path: str) -> str:
    raw_path = Path(path)
    target = raw_path if raw_path.is_absolute() else repo_dir / raw_path
    try:
        return str(target.resolve().relative_to(repo_dir.resolve()))
    except ValueError:
        return str(raw_path)


def _default_message(rel_paths: list[str]) -> str:
    if len(rel_paths) == 1:
        basename = Path(rel_paths[0]).name
        if basename == "state_rss.json":
            return "ci: update state_rss.json"
        return f"Auto-update: {basename}"
    return "Auto-update: state files"


def commit_paths_if_changed(paths, message: str | None = None) -> bool:
    """Commit and push changed state/history files without making the bot fail.

    This is intentionally best-effort. The announcement should not crash just
    because Git is unavailable locally or push credentials are missing.

    Set GIT_STATE_AUTO_COMMIT=0 to disable this helper.
    """
    if _disabled():
        print("ℹ️ GIT_STATE_AUTO_COMMIT=0; skipped Git state commit.")
        return False

    repo_dir = _repo_dir()
    if not (repo_dir / ".git").exists():
        print("ℹ️ No .git directory found; skipped Git state commit.")
        return False

    rel_paths = [_relative_path(repo_dir, path) for path in _as_list(paths)]
    if not rel_paths:
        print("ℹ️ No state paths provided; skipped Git state commit.")
        return False

    commit_message = message or _default_message(rel_paths)

    try:
        inside = _run_git(repo_dir, "rev-parse", "--is-inside-work-tree")
        if inside.returncode != 0:
            print("ℹ️ Not inside a Git work tree; skipped Git state commit.")
            return False

        _run_git(repo_dir, "config", "user.name", os.getenv("GIT_COMMIT_USER_NAME", "github-actions[bot]"))
        _run_git(repo_dir, "config", "user.email", os.getenv("GIT_COMMIT_USER_EMAIL", "github-actions[bot]@users.noreply.github.com"))

        pull = _run_git(repo_dir, "pull", "--rebase", "--autostash")
        if pull.returncode != 0:
            print("⚠️ Git pull failed; will still try to commit local state.")

        _run_git(repo_dir, "add", "--", *rel_paths, check=True)
        diff = _run_git(repo_dir, "diff", "--cached", "--quiet")
        if diff.returncode == 0:
            print(f"ℹ️ No Git changes to commit for {', '.join(rel_paths)}.")
            return False
        if diff.returncode != 1:
            print(f"⚠️ Could not check staged diff for {', '.join(rel_paths)}; skipped Git state commit.")
            return False

        commit = _run_git(repo_dir, "commit", "-m", commit_message)
        if commit.returncode != 0:
            print("⚠️ Git commit failed; state file was saved locally but not committed.")
            return False

        push = _run_git(repo_dir, "push")
        if push.returncode != 0:
            print("⚠️ Git push failed; state file was committed locally but not pushed.")
            return False

        print(f"✅ Committed and pushed {', '.join(rel_paths)}.")
        return True

    except Exception as exc:
        print(f"⚠️ Git state commit skipped: {exc}")
        return False


def commit_state_update(path: str, message: str | None = None) -> bool:
    return commit_paths_if_changed([path], message)
