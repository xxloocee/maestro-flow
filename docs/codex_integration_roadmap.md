# Codex 适配增强路线

## 1. 文档目的

本文档用于定义 Maestro Flow 在 Codex 宿主下的适配增强路线。

目标不是把 Maestro Flow 做成一个依赖 Codex 才能工作的产品，而是：

`在保持 CLI 本体独立性的前提下，让 Codex 用户获得足够顺滑、足够清楚、足够稳定的接入体验。`

本文档与以下文档配套使用：

- `docs/MVP_definition.md`
- `docs/support_matrix.md`

## 2. 当前现状

当前仓库中当前只保留一类 Codex 相关接入：

1. `codex` skills
   - 当前已提供：
     - `maestro-spec`
     - `maestro-run`

Codex CLI、桌面端与 IDE 扩展共享同一套技能配置，不再单独维护 `vscode-codex` 目标。

当前这套接入说明了两件事：

- Codex 已经不是“完全空白支持”
- 但 Codex 适配仍停留在默认主路径接入层，离“完整深度支持”还有明显差距

## 3. 当前主要问题

结合现有仓库状态，Codex 适配的核心问题主要有四类。

### 3.1 接入深度不够

问题在于：

- 缺少 sync-back 等进阶能力入口
- 缺少更细的宿主内交互能力
- 缺少对高级工作流的系统化入口

这会导致 Codex 用户只能覆盖流程的一部分，无法形成完整闭环。

### 3.2 文档与模板存在编码和可读性问题

此前已发现：

- `integrations/codex/skills/maestro-spec/SKILL.md`

存在明显乱码问题。

这类问题的影响很直接：

- 用户第一次安装后就会觉得不成熟
- 宿主内提示信息不可读
- 发布后容易被误判为“不支持”而不是“支持但体验差”

该问题已优先处理完成，但仍应继续保持新接入文件的编码一致性。

### 3.3 支持路径不完整

当前 CLI 的默认主路径是：

1. `run --mock`
2. `run --requirement`
3. `spec init`
4. `spec run`
5. 查看 `summary.md` / `run_state.json`

此前 Codex 适配主要覆盖的是 `spec` 思路，没有把这条默认主路径完整映射进去。

结果就是：

- CLI 的产品叙事是一条主线
- Codex 的使用路径是另一条偏碎片化的路径

这会让用户理解成本上升，也会加重维护成本。

### 3.4 缺少稳定性声明

当前还没有对外明确说明：

- Codex 当前稳定支持什么
- Codex 当前不稳定支持什么
- Codex 当前推荐怎么用

这会导致预期管理失焦。

## 4. 目标定义

Codex 适配的目标应当分两层定义。

### 4.1 第一阶段目标

让 Codex 用户可以顺滑完成 CLI 的默认主路径。

也就是至少做到：

1. 能安装
2. 能触发 requirement/spec 流程
3. 能拿到清楚的运行结果位置
4. 能理解下一步该怎么做

### 4.2 第二阶段目标

在默认主路径稳定后，再逐步补高级能力入口。

包括：

- execution loop
- isolated execution
- sync-back
- review/report shortcut

第二阶段不是先决条件，不应阻塞开源首发。

## 5. 路线拆分

### P0：先修可用性问题

这是最应该立刻处理的一层。

包括：

1. 修复 Codex skill 文档乱码
2. 检查 skill 名称、提示词、确认文案是否统一
3. 确保安装后用户看到的说明是可读的
4. 明确宿主内置 slash commands 与自定义 skills 的边界

这一步不扩能力，只修“第一眼是否可信”。

当前状态：已完成。

### P1：补齐默认主路径技能集

建议把 Codex skill 套件至少收敛为：

1. `maestro-spec`
   - 面向“先出 Spec，再确认执行”

2. `maestro-run`
   - 面向 requirement 直接执行

这一步的目标不是覆盖所有 CLI 命令，而是把默认主路径映射完整。

当前状态：已完成。

### P2：统一 Codex 与 CLI 叙事

这一步要解决“CLI 是一套产品叙事，Codex 是另一套使用路径”的问题。

建议统一以下内容：

- README 中对 Codex 的定位
- skill 的命名
- requirement 路径和 spec 路径的推荐顺序
- 运行结束后统一提示查看 `summary.md` / `run_state.json`

最终目标是：

`无论用户从 CLI 进入，还是从 Codex 进入，理解到的是同一条主路径。`

### P3：再补高级能力入口

在前两层完成后，再考虑是否增加以下 Codex 入口：

- `maestro-execution-loop`
- `maestro-sync-back-plan`
- `maestro-sync-back-apply`

这些能力有价值，但不应先于默认主路径打磨。

## 6. 当前不建议优先做的事

在 Codex 适配增强阶段，以下事项不建议优先投入：

- 把产品整体改造成 Codex plugin-first 形态
- 为 Codex 单独做偏离 CLI 的独立流程
- 一开始就覆盖全部高级命令
- 先做复杂自动化，而不先修基础可读性和可用性

原因很简单：

当前的核心问题不是“Codex 功能太少”，而是“Codex 入口不够完整，体验不够稳定，口径不够统一”。

## 7. 推荐实施顺序

建议按以下顺序推进：

1. 修复 Codex 相关乱码与可读性问题
2. 新增 `maestro-run` skill
3. 在 README 与支持矩阵中同步更新 Codex 能力说明
4. 继续做真实宿主冒烟验证
5. 再评估是否需要补高级能力入口

## 8. 完成标准

Codex 适配增强可以视为达标，当且仅当满足以下条件：

- Codex 安装产物全部可读，无乱码
- Codex 用户可以完成 requirement 路径和 spec 路径
- 运行完成后，用户知道去哪里看结果
- README、支持矩阵、skills 说明的说法一致
- 对外可以把 Codex 从“基础可用”提升到“可用且推荐尝试”

## 9. 总结

Codex 适配的核心方向，不是先做更复杂的功能，而是：

`先修可读性，再补完整入口，再统一产品叙事，最后才补高级能力。`

这条路线更稳，也更符合当前 Maestro Flow 作为独立开源 CLI 工具的定位。
