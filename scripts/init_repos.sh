#!/usr/bin/env bash
set -euo pipefail

# init_repos.sh
# Helper to create local `dev/` and `uat/` scaffolds from the current workspace.
# Usage:
#   ./scripts/init_repos.sh --create-only
#   ./scripts/init_repos.sh --create-and-commit

ACTION="create-and-commit"
if [[ "${1:-}" == "--create-only" ]]; then
  ACTION="create-only"
fi

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
DEV_DIR="$ROOT_DIR/dev"
UAT_DIR="$ROOT_DIR/uat"

echo "Creating scaffold dirs:"
mkdir -p "$DEV_DIR" "$UAT_DIR"

echo "Copying project files into dev/ and uat/ (excluding .git)"
# copy files excluding the dev and uat directories themselves and .git
rsync -a --exclude '.git' --exclude 'dev' --exclude 'uat' --exclude 'node_modules' "$ROOT_DIR/" "$DEV_DIR/"
rsync -a --exclude '.git' --exclude 'dev' --exclude 'uat' --exclude 'node_modules' "$ROOT_DIR/" "$UAT_DIR/"

if [[ "$ACTION" == "create-and-commit" ]]; then
  echo "Initializing git repositories and creating initial commits"
  pushd "$DEV_DIR" > /dev/null
  rm -rf .git || true
  git init
  git checkout -b dev || git switch -c dev
  git add .
  git commit -m "Initial scaffold for dev" || true
  popd > /dev/null

  pushd "$UAT_DIR" > /dev/null
  rm -rf .git || true
  git init
  git checkout -b uat || git switch -c uat
  git add .
  git commit -m "Initial scaffold for uat" || true
  popd > /dev/null

  echo "Created local git repos. To push to remote, run:"
  echo "  cd dev && git remote add origin <git-url> && git push -u origin dev"
  echo "  cd uat && git remote add origin <git-url> && git push -u origin uat"
else
  echo "Scaffolds created in: $DEV_DIR and $UAT_DIR (no git commits made)"
  echo "Run './scripts/init_repos.sh --create-and-commit' to init & commit locally"
fi

echo "Done."
