# 已验证组合

## 1. 目的

本文档记录 Maestro Flow 当前已经验证过的宿主环境与 provider 组合。

这份文档的作用不是声明“支持矩阵”，而是声明：

`哪些组合已经实际验证过，哪些组合当前只是代码层支持。`

支持边界请看：

- `docs/support_matrix.md`

真实项目样本请看：

- `docs/real_world_regression_samples.md`

## 2. 验证状态定义

- `已验证`：已经在真实或明确的目标场景中跑通过
- `已冒烟验证`：已经完成本地安装 / mock / dry-run / smoke test 验证
- `代码支持`：代码中已接入，但尚未纳入当前验证结论

## 3. 宿主环境

| 宿主 | 当前状态 | 说明 |
| --- | --- | --- |
| `CLI` | 已验证 | 当前默认主路径和发布前冒烟均以 CLI 为基准 |
| `OpenCode` | 已验证 | 已做真实项目实战验证，当前最推荐 |
| `Codex` | 已冒烟验证 | 已验证 skills 安装和默认主路径入口；桌面端与 IDE 扩展共用此配置 |
| `Claude` | 代码支持 | 已提供 slash command 模板 |
| `Cursor` | 代码支持 | 已提供 slash command 模板 |
| `Antigravity` | 代码支持 | 已提供 slash command 模板 |

## 4. Provider

| Provider | 当前状态 | 说明 |
| --- | --- | --- |
| `openrouter` | 已验证 | 已用于实际项目场景验证 |
| `openai` | 已冒烟验证 | 当前默认推荐 provider 路径之一 |
| `custom` | 代码支持 | 适用于 OpenAI-compatible 自定义端点 |
| `deepseek` | 代码支持 | 已内置 provider profile |
| `moonshot` | 代码支持 | 已内置 provider profile |
| `qwen` | 代码支持 | 已内置 provider profile |
| `siliconflow` | 代码支持 | 已内置 provider profile |
| `volcengine` | 代码支持 | 已内置 provider profile |

## 5. Codex 默认主路径验证

当前已验证以下 Codex skills 已进入安装产物：

- `maestro-spec`
- `maestro-run`

当前这表示：

- Codex 默认主路径已经具备基础闭环
- 但高级能力入口尚未作为当前验证重点

## 6. 更新原则

当出现以下情况时，应更新本文档：

- 新宿主完成实际验证
- 新 provider 完成实际验证
- 某个原本已验证的组合出现回退
- README 或支持矩阵中的推荐路径发生变化

## 7. 当前结论

截至当前版本，最稳妥的对外说法是：

- `CLI`：已验证
- `OpenCode + openrouter`：已验证，当前最推荐
- `Codex`：已冒烟验证，默认主路径可用并推荐尝试
- 其他 provider / 宿主：代码支持，但应继续补验证记录

当前已收录的真实项目样本：

- `xxloocee/lunargleamloo-blog`
