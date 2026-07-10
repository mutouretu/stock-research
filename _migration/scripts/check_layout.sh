#!/usr/bin/env bash
set -u

# Phase 1b only: verify the new repository-root skeleton, not migrated projects.
required_directories=(
  "platform"
  "platform/data"
  "platform/ml"
  "research"
  "research/pattern"
  "research/cycle"
  "automation"
  "storage"
  "ops"
  "ops/jobs"
  "ops/scripts"
  "docs"
  "_migration"
  "_migration/logs"
  "_migration/scripts"
)

missing=0
for directory in "${required_directories[@]}"; do
  if [[ -d "$directory" ]]; then
    printf 'OK      %s\n' "$directory"
  else
    printf 'MISSING %s\n' "$directory"
    missing=1
  fi
done

if (( missing )); then
  printf 'Phase 1b layout check failed.\n' >&2
  exit 1
fi

printf 'Phase 1b layout check passed.\n'
