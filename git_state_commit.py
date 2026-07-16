import os
import subprocess
import time
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


def _positive_int_env(name: str, default: int) -> int:
    try:
        value = int(str(os.getenv(name, default)).strip())
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _current_branch(repo_dir: Path) -> str:
    branch = str(os.getenv("GIT_STATE_BRANCH", "")).strip()
    if branch:
        return branch

    branch = str(os.getenv("GITHUB_REF_NAME", "")).strip()
    if branch and branch != "merge":
        return branch

    proc = _run_git(repo_dir, "branch", "--show-current")
    branch = (proc.stdout or "").strip()
    return branch or "main"


def _push_with_retry(repo_dir: Path) -> bool:
    remote = str(os.getenv("GIT_STATE_REMOTE", "origin")).strip() or "origin"
    branch = _current_branch(repo_dir)
    max_attempts = _positive_int_env("GIT_STATE_PUSH_RETRIES", 5)
    retry_delay = _positive_int_env("GIT_STATE_PUSH_RETRY_DELAY", 3)

    for attempt in range(1, max_attempts + 1):
        print(f"State push attempt {attempt}/{max_attempts}...")

        fetch = _run_git(repo_dir, "fetch", remote, branch)
        if fetch.returncode != 0:
            print(f"⚠️ Git fetch failed on attempt {attempt}.")
        else:
            rebase = _run_git(repo_dir, "rebase", "--autostash", f"{remote}/{branch}")
            if rebase.returncode != 0:
                print("⚠️ Git rebase failed; aborting to avoid an unsafe state push.")
                _run_git(repo_dir, "rebase", "--abort")
                return False

            ahead = _run_git(repo_dir, "rev-list", "--count", f"{remote}/{branch}..HEAD")
            if ahead.returncode == 0 and (ahead.stdout or "").strip() == "0":
                print(f"✅ State is already present on {remote}/{branch}.")
                return True

            push = _run_git(repo_dir, "push", remote, f"HEAD:{branch}")
            if push.returncode == 0:
                print(f"✅ State push succeeded on attempt {attempt}.")
                return True

            print("⚠️ Remote changed before the push completed.")

        if attempt < max_attempts:
            time.sleep(retry_delay)

    print(f"⚠️ Git push failed after {max_attempts} attempts.")
    return False


def commit_paths_if_changed(paths, message: str | None = None) -> bool:
    """Commit and push changed state/history files with push-race retries.

    This remains best-effort so an announcement does not crash merely because
    Git is unavailable. Set GIT_STATE_AUTO_COMMIT=0 when a workflow has its own
    final commit step; that avoids two independent commit mechanisms.
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

        _run_git(repo_dir, "add", "--", *rel_paths, check=True)
        diff = _run_git(repo_dir, "diff", "--cached", "--quiet")
        if diff.returncode == 0:
            print(f"ℹ️ No new Git changes to commit for {', '.join(rel_paths)}.")
        elif diff.returncode == 1:
            commit = _run_git(repo_dir, "commit", "-m", commit_message)
            if commit.returncode != 0:
                print("⚠️ Git commit failed; state file was saved locally but not committed.")
                return False
        else:
            print(f"⚠️ Could not check staged diff for {', '.join(rel_paths)}; skipped Git state commit.")
            return False

        if not _push_with_retry(repo_dir):
            print("⚠️ State commit remains local because all push attempts failed.")
            return False

        print(f"✅ Committed and pushed {', '.join(rel_paths)}.")
        return True

    except Exception as exc:
        print(f"⚠️ Git state commit skipped: {exc}")
        return False


def commit_state_update(path: str, message: str | None = None) -> bool:
    return commit_paths_if_changed([path], message)
