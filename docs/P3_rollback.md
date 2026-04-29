# P3 回滚策略

P3 为失败运行增加自动回滚能力。

## 触发条件

满足以下条件时尝试回滚：

1. 运行状态变为 `failed`
2. `rollback.enabled = true`
3. 运行参数 `execute_rollback = true`（CLI 默认开启）

## 配置

在 `agents/agents.yaml` 中：

```yaml
rollback:
  enabled: true
  mode: command
  commands:
    - python -c "print('rollback placeholder')"
  stop_on_error: true
```

## 支持模式

当前仅支持：
- `command`：按顺序执行配置的 shell 命令。

## 终态

运行终态包含：
- `succeeded`
- `failed`
- `rolled_back`
- `rollback_failed`

## 产物

当触发回滚时，会生成：
- `run_state.json` 中的 `rollback` 区块
- `rollback_report.json`
- `rollback_step_<n>.log`（每条命令一份日志）
