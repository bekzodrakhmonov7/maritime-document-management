#!/usr/bin/env bash
# Install the project's git hooks. Run once per clone:
#   ./scripts/install-hooks.sh
# This sets core.hooksPath to .githooks (so the committed pre-commit
# hook is used) and makes the hook executable.

set -euo pipefail

root="$(git rev-parse --show-toplevel)"
hooks_dir="$root/.githooks"

if [ ! -d "$hooks_dir" ]; then
  echo "error: $hooks_dir not found" >&2
  exit 1
fi

git config core.hooksPath "$hooks_dir"
chmod +x "$hooks_dir/pre-commit"

echo "Installed git hooks (core.hooksPath=$hooks_dir)."
echo "The pre-commit hook will block files matching .gitignore and any .env files."
