# Phase 5b/7b - 迁移 stock-pattern-search 并抽取最小 research-ml-core

## 基本信息

- 迁移日期：2026-07-10
- 来源仓库：https://github.com/mutouretu/stock-pattern-search
- 来源分支与 commit：`main@806078b`
- 应用目标：`research/pattern/stock-pattern-search/`
- 通用核心目标：`platform/ml/research-ml-core/`

父目录的 `../stock-pattern-search` 工作树存在未提交的 `scripts/run_type_n_cached_range.py` 修改。为避免覆盖或夹带用户修改，本次从 GitHub 克隆干净的 `main@806078b` 到临时目录，再使用 `rsync` 导入；父目录旧项目未修改。

## 导入范围与排除项

保留了 stock-pattern-search 的 `src/`、`scripts/`、`configs/`、测试、Type-N pipeline、reviewer、其他策略空间和文档。导入时排除了：

- `.git/`、`.venv/`、`venv/`
- `__pycache__/`、`.pytest_cache/`、`.mypy_cache/`、`.ruff_cache/`、`.DS_Store`
- 顶层 `outputs/`、`data/`、`reports/`
- `*.parquet`、`*.csv`、`*.sqlite`、`*.duckdb`
- `*.pkl`、`*.pickle`、`*.joblib`、`*.onnx`、`*.pt`、`*.pth`

未复制嵌套 Git 仓库、虚拟环境、数据、模型或运行产物。Python import、脚本、Type-N 逻辑、reviewer、配置和业务行为均未改。唯一应用侧修改是 README 路径说明：统一仓库的规范数据位置为 `storage/shared_data/`，从项目目录访问是 `../../../storage/shared_data/`；旧 `../shared_data` 表述暂时保留以兼容旧 checkout 和软链接。

## research-ml-core 抽取

创建了可独立安装的 `research-ml-core` 0.1.0，package 为 `research_ml_core`，包含：

- features：收益率、lag、rolling、z-score、波动率、winsorize、normalize
- labels：forward return、二分类和回归目标
- split：walk-forward、rolling-window、expanding-window
- models：scikit-learn adapter，以及延迟导入的 LightGBM/XGBoost adapter
- training：最小 trainer
- evaluation：分类、回归和 IC 指标
- backtest：收益、年化、波动率、Sharpe、最大回撤
- protocols：样本元数据、sample id 和数值特征选择

没有抽取 Type-N、reviewer、new-high、Type-V、W-bottom、watchlist、策略配置或输出逻辑。为降低迁移风险，本阶段未替换 stock-pattern-search 的既有 import；新核心不反向依赖 stock-pattern-search。因此状态记录为 `partially_extracted`，后续消费者切换需独立回归。

## 验证结果

### research-ml-core

- `python3 -m compileall .`：通过。
- `.venv/bin/python -m pip install -e ".[dev]"`：通过。
- `.venv/bin/python -m pytest -q`：`5 passed`。
- 首次测试有 2 个严格浮点相等断言失败；改为 `pytest.approx` 后通过，生产代码未因此修改。

### stock-pattern-search

- `python3 -m compileall .`：通过。
- `.venv/bin/python -m pip install -r requirements.txt`：通过。
- `.venv/bin/python -m pip install -e ../../../platform/ml/research-ml-core`：通过。
- `.venv/bin/python -m pytest -q`：`56 passed, 7 warnings`。warnings 均为 LightGBM estimator 的 feature-name 提示。
- `.venv/bin/python scripts/run_type_n_task.py --help`：通过。
- `.venv/bin/python -c 'import research_ml_core; print(research_ml_core.__version__)'`：输出 `0.1.0`。

`storage/shared_data/raw/daily/` 下存在可用 parquet daily cache。完整 Type-N inference 依赖按本阶段规则排除的模型产物，因此没有伪造“一天/top 5”推理成功，也没有在仓库内生成输出。现有测试已覆盖 Type-N task orchestration 和核心 pipeline 行为。

## Git 安全检查

- 两个项目内均无嵌套 `.git/`。
- 本地 `.venv/`、`__pycache__/` 和 `.pytest_cache/` 均被 ignore，不会提交。
- 导入树中未发现被纳入迁移的数据或模型文件。
- `storage/shared_data/` 保持 ignore，未加入 Git。
- 临时 CLI help 写入 `/tmp/stock-pattern-search-type-n-help.txt`，仓库内未产生 smoke 输出。

## 遗留问题与结论

1. stock-pattern-search 的旧默认 `../shared_data` 尚未统一切换；本阶段仅补充文档说明。
2. research-ml-core 尚未成为 stock-pattern-search 的运行时依赖；逐个替换和等价回归留给后续任务。
3. 完整 Type-N inference 需要另行确定模型产物的存储和加载策略。
4. `research-data-core` 与 `cycle-equity-research` 未创建，符合本阶段禁止事项。

Phase 5b 的物理迁移与 Phase 7b 的最小 ML core 创建均已完成，可以进入下一独立迁移阶段；在切换 core 消费者前应先定义兼容测试和模型产物策略。
