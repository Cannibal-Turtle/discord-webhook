#!/usr/bin/env bash
set -euo pipefail

if (( $# < 2 )); then
  echo "Usage: $0 <commit-message> <path> [path ...]" >&2
  exit 2
fi

commit_message="$1"
shift
paths=("$@")

remote="${GIT_STATE_REMOTE:-origin}"
branch="${GIT_STATE_BRANCH:-${GITHUB_REF_NAME:-}}"
if [[ -z "$branch" || "$branch" == "merge" ]]; then
  branch="$(git branch --show-current)"
fi
branch="${branch:-main}"

max_attempts="${GIT_STATE_PUSH_RETRIES:-5}"
retry_delay="${GIT_STATE_PUSH_RETRY_DELAY:-3}"

git config user.name "${GIT_COMMIT_USER_NAME:-github-actions[bot]}"
git config user.email "${GIT_COMMIT_USER_EMAIL:-github-actions[bot]@users.noreply.github.com}"

git add -- "${paths[@]}"
if git diff --cached --quiet; then
  echo "No new changes to commit for: ${paths[*]}"
else
  git commit -m "$commit_message"
fi

for (( attempt=1; attempt<=max_attempts; attempt++ )); do
  echo "State push attempt ${attempt}/${max_attempts}..."

  git fetch "$remote" "$branch"
  if ! git rebase --autostash "$remote/$branch"; then
    echo "Rebase failed; aborting so state is not pushed incorrectly." >&2
    git rebase --abort || true
    exit 1
  fi

  ahead="$(git rev-list --count "$remote/$branch..HEAD")"
  if [[ "$ahead" == "0" ]]; then
    echo "State is already present on $remote/$branch."
    exit 0
  fi

  if git push "$remote" "HEAD:$branch"; then
    echo "State push succeeded."
    exit 0
  fi

  if (( attempt < max_attempts )); then
    echo "Remote changed before the push; retrying in ${retry_delay}s..."
    sleep "$retry_delay"
  fi
done

echo "State push failed after ${max_attempts} attempts." >&2
exit 1
