#!/usr/bin/env bash
set -u

# Phase 1 only: verify the target directory skeleton, not migrated projects.
required_directories=(
  "migration"
  "migration/logs"
  "migration/scripts"
  "migration/platform"
  "migration/platform/data"
  "migration/platform/ml"
  "migration/research"
  "migration/research/pattern"
  "migration/research/cycle"
  "migration/automation"
  "migration/storage"
  "migration/ops"
  "migration/ops/jobs"
  "migration/ops/scripts"
  "migration/docs"
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
  printf 'Phase 1 layout check failed.\n' >&2
  exit 1
fi

printf 'Phase 1 layout check passed.\n'
