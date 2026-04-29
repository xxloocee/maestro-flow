# P0 + P1 实施说明

本文档记录第一阶段优化：

- P0：状态机、重试机制、错误码、可追溯产物
- P1：DAG 调度与并行阶段执行

## 变更内容

1. 工作流从线性串行切换为 DAG 调度。
2. 新增运行状态机，落盘到 `.maestro/runs/<run_id>/run_state.json`。
3. 新增阶段级重试（`workflow.max_retries`）。
4. 新增阶段错误码与运行级错误码。
5. 新增并行执行能力（`workflow.parallel_workers`）。

## 当前 DAG

1. `pm`
2. `architect` 依赖 `pm`
3. `dev` 依赖 `architect`
4. `tester` 依赖 `dev`
5. `debugger` 依赖 `dev`
6. `reviewer` 依赖 `architect`、`dev`、`tester`、`debugger`

其中 `tester` 与 `debugger` 可并行执行。

## 运行产物

每次运行会生成：

- `run_state.json`：状态机快照
- `stage_<name>.json`：阶段输出
- `summary.md`：阶段状态、评审结论、质量门禁汇总

## 配置示例

`agents/agents.yaml`：

```yaml
workflow:
  max_retries: 1
  parallel_workers: 3
```

## 后续阶段（已规划）

1. P2：CI 门禁评估 + PR 自动评论。
2. P3：失败后自动回滚，支持 `rolled_back` 终态。
3. P4：知识库注入、提示词版本化、策略门禁。
4. P5：策略插件化与 PR 策略明细展示。
5. P6：执行闭环（自动改代码、自动测试、自动修复）。
