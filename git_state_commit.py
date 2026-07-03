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


def commit_state_update(path: str, message: str = "ci: update state_rss.json") -> bool:
    """Commit and push a changed state file without making the bot fail.

    This is intentionally best-effort. The bot should not repost/crash just
    because Git is unavailable locally or push credentials are missing.

    Set GIT_STATE_AUTO_COMMIT=0 to disable this helper.
    """
    if str(os.getenv("GIT_STATE_AUTO_COMMIT", "1")).strip().lower() in _FALSEY:
        print("ℹ️ GIT_STATE_AUTO_COMMIT=0; skipped Git state commit.")
        return False

    repo_dir = Path(__file__).resolve().parent
    if not (repo_dir / ".git").exists():
        print("ℹ️ No .git directory found; skipped Git state commit.")
        return False

    raw_path = Path(path)
    target = raw_path if raw_path.is_absolute() else repo_dir / raw_path
    try:
        rel_path = str(target.resolve().relative_to(repo_dir.resolve()))
    except ValueError:
        rel_path = str(raw_path)

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

        _run_git(repo_dir, "add", "--", rel_path, check=True)
        diff = _run_git(repo_dir, "diff", "--cached", "--quiet")
        if diff.returncode == 0:
            print(f"ℹ️ No Git changes to commit for {rel_path}.")
            return False
        if diff.returncode != 1:
            print(f"⚠️ Could not check staged diff for {rel_path}; skipped Git state commit.")
            return False

        commit = _run_git(repo_dir, "commit", "-m", message)
        if commit.returncode != 0:
            print("⚠️ Git commit failed; state file was saved locally but not committed.")
            return False

        push = _run_git(repo_dir, "push")
        if push.returncode != 0:
            print("⚠️ Git push failed; state file was committed locally but not pushed.")
            return False

        print(f"✅ Committed and pushed {rel_path}.")
        return True

    except Exception as exc:
        print(f"⚠️ Git state commit skipped: {exc}")
        return False
