# Codex 任务说明：stock-research 目录分层迁移

> Phase 1b scope override: the current Git repository root is the future `stock-research` root, even if its temporary local folder name is `migration`. Keep the empty target skeleton at this repository root and keep migration materials under `_migration/`. Do not move, copy, delete, or modify projects in the parent directory during this phase.

You are working in the `stock-research` repository.

Goal:
Reorganize the repository from a flat project layout into a functional layered layout. This is a migration task, not a business logic refactor.

Current root layout:

```text
stock-research/
    alpha_agent_system/
    build-daily-cache/
    market_pattern_labeler/
    market-data-hub/
    shared_data/
    stock-pattern-search/
```

Target root layout:

```text
stock-research/
    platform/
        data/
            market-data-hub/
            research-data-core/
        ml/
            research-ml-core/

    research/
        pattern/
            stock-pattern-search/
            market_pattern_labeler/
        cycle/
            cycle-equity-research/

    automation/
        alpha_agent_system/

    storage/
        shared_data/

    _migration/
    ops/
    docs/
```

Important rules:

1. Do not change business logic unless necessary to fix paths/imports.
2. Keep existing Python package import names unchanged.
3. Do not rename `alpha_agent_system` or `market_pattern_labeler` packages.
4. Do not extract ML code from `stock-pattern-search` in this task.
5. Do not add large data files to git.
6. Treat `shared_data` as local data storage; move it carefully and do not commit data files.
7. `build-daily-cache` has been integrated into `market-data-hub`. Remove it only after confirming no references remain.
8. After each move, update path references and run validation.
9. Write migration notes into `_migration/logs/`.
10. Keep the migration incremental and easy to review.

Required outputs:

1. `_migration/README.md`
2. `_migration/move_map.yaml`
3. `_migration/validation_plan.md`
4. `_migration/scripts/check_old_paths.sh`
5. `_migration/scripts/check_layout.sh`
6. Updated repository layout
7. New placeholder projects:
   - `platform/data/research-data-core`
   - `platform/ml/research-ml-core`
   - `research/cycle/cycle-equity-research`
8. Updated README files where necessary
9. Validation logs for each phase

Validation:

- Run `rg` to find stale old paths.
- Run `python -m compileall .` inside each Python project.
- Run `pytest -q` when tests exist.
- Record failures honestly in `_migration/logs/`.
- Do not hide failing tests.

Suggested implementation order:

1. Inventory the legacy workspace and write `_migration/logs/000_inventory.md`.
2. Create target directory skeleton.
3. Move `market-data-hub` to `platform/data/market-data-hub`.
4. Move `shared_data` to `storage/shared_data` if safe.
5. Remove `build-daily-cache` after stale reference check.
6. Move `stock-pattern-search` and `market_pattern_labeler` to `research/pattern/`.
7. Move `alpha_agent_system` to `automation/`.
8. Create `research-data-core` skeleton.
9. Create `research-ml-core` skeleton.
10. Create `cycle-equity-research` skeleton with `configs/instruments/CF.yaml`.

Do not bundle unrelated refactors into this migration.
