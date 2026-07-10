# Phase 3：迁移 shared_data 到 storage 层

迁移日期：2026-07-10

## 1. 路径与迁移方式

- 迁移前真实路径：`../shared_data`
- 迁移后真实路径：`storage/shared_data`
- 迁移方式：同文件系统 `mv`，不是 `cp`
- 新仓库本地临时根目录：`migration/`

目标路径迁移前不存在，`storage/` 中只有用于保留目录的根级 `.gitkeep`，因此没有覆盖或合并既有数据。

## 2. 迁移前检查

| 项目 | 结果 |
|---|---:|
| `du -sh ../shared_data` | 24 GiB |
| `du -sk ../shared_data` | 25,164,336 KiB |
| 文件数 | 159,262 |
| 目录数 | 41 |
| 可用磁盘空间 | 约 1.2 TiB |
| staged 文件 | 0 |
| Git 已跟踪 shared_data/数据文件 | 0 |

迁移前一级/二级结构：

```text
../shared_data
../shared_data/labels
../shared_data/raw
../shared_data/raw/daily
../shared_data/us
../shared_data/us/raw
```

## 3. 兼容软链接

移动完成后在旧工作区根目录创建：

```text
../shared_data -> migration/storage/shared_data
```

验证：

- `test -L ../shared_data`：通过。
- `readlink ../shared_data`：`migration/storage/shared_data`。
- `test -d ../shared_data`：通过，链接可解析为目录。
- `du -shL ../shared_data`：24 GiB。

macOS 上不跟随链接的 `du -sh ../shared_data` 显示链接自身为 0B；使用 `-L` 后确认它指向完整的 24 GiB 数据。

最终切换本地目录名时，需要根据 `stock-research-old` 与新 `stock-research` 的实际相对位置重新核对或重建该软链接。

## 4. 迁移后完整性

| 项目 | 迁移前 | 迁移后 | 结论 |
|---|---:|---:|---|
| KiB | 25,164,336 | 25,164,336 | 一致 |
| `du -sh` | 24 GiB | 24 GiB | 一致 |
| 文件数 | 159,262 | 159,262 | 一致 |
| 目录数 | 41 | 41 | 一致 |

迁移后一级/二级结构：

```text
storage/shared_data
storage/shared_data/labels
storage/shared_data/raw
storage/shared_data/raw/daily
storage/shared_data/us
storage/shared_data/us/raw
```

由于是同一文件系统内的目录重命名，操作没有复制第二份 24 GiB 数据。

## 5. parquet 抽样读取

使用 market-data-hub 的本地忽略虚拟环境（pandas + pyarrow）抽读 5 个小型 US per-symbol parquet：

| 文件 | shape | 前几个字段 |
|---|---:|---|
| `CBRE.parquet` | `(5550, 15)` | `trade_date, open, high, low, close, vol, volume, adj_close, ts_code, symbol` |
| `XP.parquet` | `(1647, 15)` | 同上 |
| `BYD.parquet` | `(6664, 15)` | 同上 |
| `SUI.parquet` | `(6664, 15)` | 同上 |
| `ROIV.parquet` | `(1397, 15)` | 同上 |

5 个文件全部可读取，没有执行 24 GiB 全量扫描。

## 6. Git 安全检查

Phase 3 前 `.gitignore` 已忽略：

- `storage/shared_data/`
- `shared_data/`
- `*.parquet`
- `*.feather`
- `*.duckdb`
- `*.sqlite`

本阶段补充：

- `*.csv`
- `*.pkl`
- `*.pickle`

结果：

- `git ls-files storage/shared_data`：0 个文件。
- `git status --short` 没有列出 `storage/shared_data` 或任何数据文件。
- 新仓库中没有 staged 数据文件。
- `.env` 和凭据仍被忽略，且没有复制到新数据目录或 Git。

本阶段允许提交的内容仅为本日志、move map、validation plan 和 `.gitignore` 更新。

## 7. 遗留问题

1. 兼容软链接目标包含临时目录名 `migration`；最终仓库改名时必须复核。
2. market-data-hub README/默认 CLI 中仍有 `../shared_data` 历史路径。由于本阶段禁止修改 hub 业务代码，运行新仓库 hub 时应显式传入 `storage/shared_data` 下的目标路径，后续再做独立路径配置收口。
3. 旧项目继续通过父目录 `../shared_data` 软链接访问数据；迁移各项目时应逐一切换为新分层路径并做回归。
4. `build-daily-cache` 的独有工具、凭据和约 299 MiB 历史资产仍未处置，Phase 4 继续阻塞。

## 8. 后续阶段判断

**可以进入 Phase 5：迁移 `stock-pattern-search` 和 `market_pattern_labeler`。**

依据：数据已完整移动，新路径受 Git ignore 保护，旧路径兼容软链接可用，parquet 抽样读取成功。Phase 5 应在移动两个 pattern 项目后更新其数据路径并验证读取。

Phase 4 不因本次 shared_data 迁移而自动解锁；仍不得删除 `build-daily-cache`。
