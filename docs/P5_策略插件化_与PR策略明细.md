# P5 实施说明：策略插件化与 PR 策略明细

P5 目标：让策略门禁可扩展、可定制、可审查。

- 可扩展：支持通过插件新增策略规则。
- 可定制：支持对单条规则做启停、阻断级别和文案覆盖。
- 可审查：在 PR 评论中直接展示策略门禁结果与阻断失败明细。

## 1. 配置扩展

位置：`agents/agents.yaml`

新增字段：

```yaml
policy:
  plugin_entrypoints: []
  rules: {}
```

### plugin_entrypoints

规则插件入口列表，支持两种格式：
- `module.submodule:function`
- `path/to/plugin.py:function`

### rules

按 `policy_id` 对规则做覆盖：
- `enabled`：是否启用
- `blocking`：是否阻断
- `message`：覆盖默认文案

示例：

```yaml
policy:
  plugin_entrypoints:
    - policies/no_todo.py:run
  rules:
    DEV_VERIFY_COMMAND_REQUIRED:
      enabled: false
    PLUGIN_NO_TODO:
      blocking: false
      message: 自定义 TODO 检查不阻断发布
```

仓库内置示例插件：
- `policies/no_todo.py`：扫描阶段输出中的 `TODO/FIXME`，命中则阻断失败。

## 2. 插件协议

实现位置：`src/maestro_flow/policy_gate.py`

插件函数调用方式：
- 优先尝试关键字参数：`run(stage_outputs=..., config=..., repo_root=...)`
- 不兼容时回退为位置参数：`run(stage_outputs, config)`

返回值支持：
- `dict`
- `list[dict]`
- `PolicyResult`
- `list[PolicyResult]`

`dict` 最小字段：
- `policy_id`
- `status`

可选字段：
- `blocking`（默认 `true`）
- `message`

## 3. 失败处理

- 插件加载失败：生成 `PLUGIN_LOAD::<entrypoint>` 规则结果，状态 `fail`，阻断发布。
- 插件执行失败：生成 `PLUGIN_EXEC::<entrypoint>` 规则结果，状态 `fail`，阻断发布。

这样可以保证策略系统异常不会被静默忽略。

## 4. PR 评论增强

实现位置：
- `src/maestro_flow/ci_ops.py`
- `src/maestro_flow/cli.py`

增强内容：
1. `ci comment` 自动读取 `policy_report.json`。
2. 评论新增“策略门禁”区块，展示每条策略状态。
3. 评论顶部新增“阻断摘要”，优先展示阻断型策略失败项。
4. `ci evaluate` 会输出门禁失败原因码，便于自动化系统按错误类型处理。

## 5. 测试覆盖

新增/更新：
- `tests/test_policy_gate.py`
  - 规则覆盖可禁用内置规则
  - 文件路径插件可执行
  - 插件异常可转换为阻断失败
- `tests/test_ci_ops.py`
  - 评论包含策略门禁和阻断失败策略区块

## 6. 已知限制

1. 当前仅支持 Python 插件，不支持远程插件仓库。
2. 插件沙箱隔离未实现，默认与主进程同权限运行。
3. 规则执行顺序为“内置规则 -> 插件规则”，暂不支持自定义优先级。
