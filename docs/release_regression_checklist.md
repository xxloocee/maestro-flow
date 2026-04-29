# 发布前回归检查清单

## 1. 目的

本文档定义 Maestro Flow 在开源发布前的最小回归检查项。

目标不是覆盖所有实现细节，而是确保下面这条对外主路径没有被改坏：

1. 用户可以安装并运行 CLI
2. 用户可以跑通 mock requirement 流程
3. 用户可以跑通 mock spec 流程
4. 用户可以查看运行结果与门禁结果
5. 用户可以安装 Codex 默认技能集

## 2. 建议执行时机

在以下场景执行：

- 发布前
- 修改编排器后
- 修改 CLI 命令行为后
- 修改 README、文档主路径或宿主集成后
- 修改 Codex 集成后

## 3. 最小手工回归项

### 3.1 Mock requirement run

命令：

```bash
python -m maestro_flow.cli run --mock --requirement "release smoke test requirement"
```

检查点：

- 命令成功执行
- 输出中包含 `run_id`
- 输出中包含 `run_dir`
- 输出中包含 `summary`

产物检查：

- `.maestro/runs/<run_id>/summary.md`
- `.maestro/runs/<run_id>/run_state.json`
- `.maestro/runs/<run_id>/policy_report.json`

### 3.2 Mock spec init

命令：

```bash
python -m maestro_flow.cli spec init --name "release-smoke-spec"
```

检查点：

- 命令成功执行
- `.maestro/specs/` 下生成新的 markdown 文件

### 3.3 Mock spec run

命令：

```bash
python -m maestro_flow.cli spec run --file <spec_path> --mock --skip-gates
```

检查点：

- 命令成功执行
- 输出中包含 `run_id`
- 生成新的 `summary.md`

### 3.4 CI gate evaluate

命令：

```bash
python -m maestro_flow.cli ci evaluate --run-id <run_id>
```

检查点：

- 命令成功执行
- 输出中包含：
  - `run_status`
  - `reviewer_verdict`
  - `gate`

### 3.5 Codex install dry-run

命令：

```bash
python -m maestro_flow.cli install --target codex --scope project --dry-run
```

检查点：

- 命令成功执行
- 安装计划中包含：
  - `maestro-spec`
  - `maestro-run`

## 4. 自动化回归项

当前建议通过测试文件覆盖以下冒烟场景：

- mock requirement run 产物存在性
- mock spec init 生成 spec 文件
- mock spec run 产物存在性
- Codex 安装 dry-run 包含默认技能集

对应测试文件：

- `tests/test_release_smoke.py`

## 5. 通过标准

一次发布前最小回归可视为通过，当且仅当：

- 手工回归项全部通过
- 自动化 smoke tests 通过
- README、支持矩阵、Codex 路线文档与当前行为一致

## 6. 备注

当前清单刻意不把“真实 provider 运行”设为强制项。

原因是：

- provider 可用性受外部环境影响较大
- 当前 MVP 更需要优先保障默认主路径和本地可复现行为

后续如果真实 provider 稳定性要求进一步提升，可以补一组独立的 provider release checks。
