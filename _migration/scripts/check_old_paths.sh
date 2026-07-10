#!/usr/bin/env bash
set -u

# Inventory only. Matches are expected during Phase 1 and never make this script fail.
pattern='build-daily-cache|build_daily_cache|daily-cache|daily_cache|market-data-hub|market_data_hub|stock-pattern-search|stock_pattern_search|market_pattern_labeler|alpha_agent_system|shared_data'

if ! command -v rg >/dev/null 2>&1; then
  printf 'ERROR: ripgrep (rg) is required.\n' >&2
  exit 2
fi

printf 'Searching for legacy path/name references (matches are informational):\n'
rg --line-number --hidden \
  --glob '!**/.git/**' \
  --glob '!**/.venv/**' \
  --glob '!**/__pycache__/**' \
  --glob '!shared_data/**' \
  --glob '!_migration/logs/000_inventory.md' \
  "$pattern" . || true

printf 'Legacy reference inventory completed.\n'
